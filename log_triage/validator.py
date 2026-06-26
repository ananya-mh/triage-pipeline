"""JSON parsing, repair, and schema validation."""

import json
import re
from log_triage.schema import validate_event


def repair_json(raw: str) -> str:
    """Attempt to fix common LLM JSON output issues."""
    text = raw.strip()

    text = re.sub(r"^```(?:json)?\s*\n?", "", text)
    text = re.sub(r"\n?```\s*$", "", text)

    match = re.search(r"\[.*\]", text, re.DOTALL)
    if match:
        text = match.group(0)

    text = re.sub(r",\s*([}\]])", r"\1", text)

    return text.strip()


def parse_response(raw: str) -> list[dict]:
    """Parse raw model response into a list of event dicts."""
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        repaired = repair_json(raw)
        try:
            parsed = json.loads(repaired)
        except json.JSONDecodeError:
            return []

    if isinstance(parsed, dict):
        parsed = [parsed]
    if not isinstance(parsed, list):
        return []
    return parsed


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
