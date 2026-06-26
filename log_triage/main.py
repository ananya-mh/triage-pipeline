"""Entry point and orchestrator for the log triage pipeline."""

import argparse
import json
import os
import sys
from collections import Counter

from log_triage import config
from log_triage.ingestion import get_log_chunks
from log_triage.prompt import call_gemini, sample_candidates
from log_triage.validator import (
    extract_and_validate, parse_response, validate_events, is_grounded,
)
from log_triage.scorer import score_events
from log_triage.alerter import dispatch_all


def process_chunk(chunk: str, n_samples: int = 1, vote_k: int = 1,
                  verbose: bool = False) -> list[dict]:
    """Best-of-N self-consistency over a single chunk.

    Draws `n_samples` model responses, keeps only schema-valid AND grounded
    events (source_line verbatim in the chunk), then keeps events that appear
    in at least `vote_k` of the samples. A hallucinated event fails grounding
    or fails to repeat across samples, so voting filters it out. With
    n_samples=1, vote_k=1 this degrades to a single grounded pass.
    """
    temperature = 0.7 if n_samples > 1 else 0.0
    raws: list[str] = []
    for i in range(n_samples):
        try:
            raws.append(call_gemini(chunk, temperature=temperature))
        except Exception as e:
            print(f"[warning] sample {i + 1}/{n_samples} failed: {e}")

    # If every sample failed, try once more with the simpler fallback prompt.
    if not raws:
        try:
            raws.append(call_gemini(chunk, use_fallback=True, temperature=0.0))
        except Exception as e:
            print(f"[warning] fallback attempt failed: {e}")
            return []

    votes: Counter = Counter()
    representative: dict = {}
    for raw in raws:
        if verbose:
            print(f"[verbose] Raw response:\n{raw}\n{'─' * 40}")
        seen_this_sample = set()
        for event in extract_and_validate(raw, chunk=chunk):
            key = (event.get("timestamp", ""), event.get("source_line", ""))
            if key in seen_this_sample:
                continue
            seen_this_sample.add(key)
            votes[key] += 1
            representative.setdefault(key, event)

    # Can't require more votes than we have samples that came back.
    effective_k = min(vote_k, len(raws))
    return [representative[key] for key, count in votes.items()
            if count >= effective_k]


def deduplicate_events(events: list[dict]) -> list[dict]:
    """Remove duplicate events based on (timestamp, source_line) tuples."""
    seen = set()
    unique = []
    for event in events:
        key = (event.get("timestamp", ""), event.get("source_line", ""))
        if key not in seen:
            seen.add(key)
            unique.append(event)
    return unique


def run_pipeline(input_path: str, output_path: str, verbose: bool = False,
                 dry_run: bool = False, n_samples: int = 1,
                 vote_k: int = 1) -> None:
    """Run the triage pipeline on a log file."""
    chunks = get_log_chunks(input_path)
    if not chunks:
        print("No log content to process after filtering.")
        return

    if n_samples > 1:
        print(f"Best-of-N enabled: {n_samples} samples/chunk, keep events "
              f"seen in >={vote_k}.")
    print(f"Processing {len(chunks)} chunk(s)...")
    all_events = []
    for i, chunk in enumerate(chunks, 1):
        print(f"  Chunk {i}/{len(chunks)}...", end=" ", flush=True)
        events = process_chunk(chunk, n_samples=n_samples, vote_k=vote_k,
                               verbose=verbose)
        print(f"{len(events)} event(s)")
        all_events.extend(events)

    all_events = deduplicate_events(all_events)
    score_events(all_events)  # adds severity_score + alert_route in place

    print(f"\nFound {len(all_events)} anomalies.")

    if not dry_run:
        tmp_path = output_path + ".tmp"
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(all_events, f, indent=2)
        os.replace(tmp_path, output_path)
        print(f"Output written to {output_path}")

        summary = dispatch_all(all_events)
        print(f"Routed -> immediate: {summary['immediate']}, "
              f"queue: {summary['queue']}, silent: {summary['silent']}")


def _collect_stats(raws: list[str], chunk: str, vote_k: int) -> dict:
    """Tally, over a set of raw responses for one chunk:
      emitted    - schema-valid events the model produced (counts repeats)
      ungrounded - of those, how many cited a source_line NOT in the chunk
      final      - grounded events surviving the >=vote_k self-consistency vote
    """
    votes: Counter = Counter()
    emitted = 0
    ungrounded = 0
    for raw in raws:
        seen = set()
        for event in validate_events(parse_response(raw)):
            emitted += 1
            if not is_grounded(event, chunk):
                ungrounded += 1
                continue
            key = (event.get("timestamp", ""), event.get("source_line", ""))
            if key in seen:
                continue
            seen.add(key)
            votes[key] += 1
    effective_k = min(vote_k, len(raws))
    final = sum(1 for count in votes.values() if count >= effective_k)
    return {"emitted": emitted, "ungrounded": ungrounded, "final": final}


def run_compare(input_path: str, n: int = 3, vote_k: int = 2,
                verbose: bool = False) -> None:
    """Baseline (N=1) vs best-of-N on the SAME samples; print a before/after.

    Draws N samples once per chunk; baseline reuses only the first sample,
    best-of-N uses all N -> a fair, no-extra-cost comparison.
    """
    chunks = get_log_chunks(input_path)
    if not chunks:
        print("No log content to process after filtering.")
        return

    base = {"emitted": 0, "ungrounded": 0, "final": 0}
    bestn = {"emitted": 0, "ungrounded": 0, "final": 0}

    print(f"Comparing N=1 vs N={n} (k={vote_k}) over {len(chunks)} chunk(s)...")
    for i, chunk in enumerate(chunks, 1):
        print(f"  Chunk {i}/{len(chunks)}...", end=" ", flush=True)
        raws: list[str] = []
        for j in range(n):
            try:
                raws.append(call_gemini(chunk, temperature=0.7))
            except Exception as e:
                print(f"[warning] sample {j + 1} failed: {e}")
        if not raws:
            print("no responses")
            continue
        b = _collect_stats(raws[:1], chunk, vote_k=1)
        m = _collect_stats(raws, chunk, vote_k=vote_k)
        for acc, stats in ((base, b), (bestn, m)):
            for key in acc:
                acc[key] += stats[key]
        print(f"baseline {b['final']} / best-of-N {m['final']}")

    def rate(d):
        return (100.0 * d["ungrounded"] / d["emitted"]) if d["emitted"] else 0.0

    header_n = f"N={n} k={vote_k}"
    print("\n" + "=" * 58)
    print(f"{'metric':30}{'N=1':>12}{header_n:>16}")
    print("-" * 58)
    print(f"{'events model emitted':30}{base['emitted']:>12}{bestn['emitted']:>16}")
    print(f"{'ungrounded (hallucinated)':30}"
          f"{base['ungrounded']:>12}{bestn['ungrounded']:>16}")
    print(f"{'  as % of emitted':30}{rate(base):>11.1f}%{rate(bestn):>15.1f}%")
    print(f"{'final accepted events':30}{base['final']:>12}{bestn['final']:>16}")
    print("=" * 58)
    print("Grounding rejects hallucinated citations in BOTH columns; best-of-N")
    print("voting additionally drops grounded-but-inconsistent one-off events.")


def main():
    parser = argparse.ArgumentParser(description="Log Triage Pipeline")
    parser.add_argument("--input", required=True, help="Path to the input log file")
    parser.add_argument("--output", default=config.OUTPUT_PATH, help="Path for JSON output")
    parser.add_argument("--verbose", action="store_true", help="Print raw model responses")
    parser.add_argument("--dry-run", action="store_true", help="Process without writing output")
    parser.add_argument("--samples", type=int, default=1,
                        help="Best-of-N: model samples per chunk (default 1)")
    parser.add_argument("--vote-k", type=int, default=1,
                        help="Keep events seen in >= this many samples (default 1)")
    parser.add_argument("--compare", action="store_true",
                        help="Print a baseline vs best-of-N before/after table")
    args = parser.parse_args()

    try:
        if args.compare:
            run_compare(
                args.input,
                n=args.samples if args.samples > 1 else 3,
                vote_k=args.vote_k if args.vote_k > 1 else 2,
                verbose=args.verbose,
            )
            return
        run_pipeline(
            input_path=args.input,
            output_path=args.output,
            verbose=args.verbose,
            dry_run=args.dry_run,
            n_samples=args.samples,
            vote_k=args.vote_k,
        )
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nInterrupted.")
        sys.exit(130)
    except Exception as e:
        print(f"Fatal error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
