"""JSON parsing, repair, and schema validation."""

import json
import re
from log_triage.schema import validate_event


_DECODER = json.JSONDecoder()


def repair_json(raw: str) -> str:
    """Cheap first-pass repair: strip markdown fences and trailing commas."""
    text = raw.strip()
    text = re.sub(r"^```(?:json)?\s*\n?", "", text)
    text = re.sub(r"\n?```\s*$", "", text)
    text = re.sub(r",\s*([}\]])", r"\1", text)
    return text.strip()


def _scan_json_arrays(text: str) -> list:
    """Find every parseable JSON array-of-objects in `text`, in order.

    Chain-of-thought models (notably Gemma) wrap their final JSON in pages of
    markdown reasoning that contains stray brackets ("[20882]", "[1]"). A
    greedy regex grabs from the first such bracket and fails to parse. Instead
    we walk every '[' and let json's decoder try to parse a value there; only
    arrays whose elements are all objects are kept. The model's real answer is
    the LAST one.
    """
    found = []
    idx, n = 0, len(text)
    while idx < n:
        start = text.find("[", idx)
        if start == -1:
            break
        try:
            obj, end = _DECODER.raw_decode(text, start)
        except json.JSONDecodeError:
            idx = start + 1
            continue
        if isinstance(obj, list) and all(isinstance(e, dict) for e in obj):
            found.append(obj)
        idx = max(end, start + 1)
    return found


def parse_response(raw: str) -> list[dict]:
    """Parse a raw model response into a list of event dicts.

    Robust to CoT models that emit prose before the JSON: try a clean parse,
    then a fence/comma repair, then scan for the LAST valid JSON array.
    """
    text = raw.strip()
    for candidate in (text, repair_json(text)):
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return [parsed]
            if isinstance(parsed, list):
                return parsed
        except json.JSONDecodeError:
            pass

    arrays = _scan_json_arrays(text)
    if arrays:
        return arrays[-1]  # the model's final answer, after any reasoning
    return []


def validate_events(events: list[dict]) -> list[dict]:
    """Filter events to only those passing schema validation."""
    valid = []
    for event in events:
        is_valid, _ = validate_event(event)
        if is_valid:
            valid.append(event)
    return valid


def is_grounded(event: dict, chunk: str) -> bool:
    """Anti-hallucination check: the cited source_line must appear VERBATIM in
    the chunk the model was given. A fabricated source_line fails this, which
    is the core reward signal for best-of-N voting (and future RLVR).
    """
    source = (event.get("source_line") or "").strip()
    return bool(source) and source in chunk


def filter_grounded(events: list[dict], chunk: str) -> list[dict]:
    """Keep only events whose source_line is verbatim-present in the chunk."""
    return [e for e in events if is_grounded(e, chunk)]


def extract_and_validate(raw: str, chunk: str | None = None) -> list[dict]:
    """Full pipeline: parse raw response, repair if needed, schema-validate,
    and (when the source chunk is supplied) drop hallucinated/ungrounded events.
    """
    events = parse_response(raw)
    valid = validate_events(events)
    if chunk is not None:
        valid = filter_grounded(valid, chunk)
    return valid
