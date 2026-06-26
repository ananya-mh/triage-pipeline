"""Entry point and orchestrator for the log triage pipeline."""

import argparse
import json
import os
import sys
import time

from log_triage import config
from log_triage.ingestion import get_log_chunks
from log_triage.prompt import call_gemini
from log_triage.validator import extract_and_validate


def process_chunk(chunk: str, verbose: bool = False) -> list[dict]:
    """Process a single log chunk through the model and validator."""
    for attempt in range(config.MAX_RETRIES + 1):
        try:
            use_fallback = attempt == config.MAX_RETRIES
            raw = call_gemini(chunk, use_fallback=use_fallback)
            if verbose:
                print(f"[verbose] Raw response:\n{raw}\n{'─' * 40}")
            events = extract_and_validate(raw)
            if events or attempt == config.MAX_RETRIES:
                return events
        except Exception as e:
            print(f"[warning] Chunk attempt {attempt + 1} failed: {e}")
        if attempt < config.MAX_RETRIES:
            time.sleep(config.RETRY_DELAY)
    return []


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
                 dry_run: bool = False) -> None:
    """Run the triage pipeline on a log file."""
    chunks = get_log_chunks(input_path)
    if not chunks:
        print("No log content to process after filtering.")
        return

    print(f"Processing {len(chunks)} chunk(s)...")
    all_events = []
    for i, chunk in enumerate(chunks, 1):
        print(f"  Chunk {i}/{len(chunks)}...", end=" ", flush=True)
        events = process_chunk(chunk, verbose=verbose)
        print(f"{len(events)} event(s)")
        all_events.extend(events)

    all_events = deduplicate_events(all_events)

    print(f"\nFound {len(all_events)} anomalies.")

    if not dry_run:
        tmp_path = output_path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(all_events, f, indent=2)
        os.replace(tmp_path, output_path)
        print(f"Output written to {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Log Triage Pipeline")
    parser.add_argument("--input", required=True, help="Path to the input log file")
    parser.add_argument("--output", default=config.OUTPUT_PATH, help="Path for JSON output")
    parser.add_argument("--verbose", action="store_true", help="Print raw model responses")
    parser.add_argument("--dry-run", action="store_true", help="Process without writing output")
    args = parser.parse_args()

    try:
        run_pipeline(
            input_path=args.input,
            output_path=args.output,
            verbose=args.verbose,
            dry_run=args.dry_run,
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
