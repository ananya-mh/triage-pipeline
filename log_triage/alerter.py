"""Webhook dispatcher (Slack, PagerDuty, generic).

Routes scored events by their alert_route:
  - immediate -> POST to the configured webhook (falls back to the queue file
                 if no webhook is set or the POST fails)
  - queue     -> append to the queued-alerts JSONL
  - silent    -> append to the silent-log JSONL (kept for audit, not paged)
"""

import json
import os

import requests

from log_triage import config


def _append_jsonl(path: str, event: dict) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(event) + "\n")


def _post_webhook(event: dict) -> bool:
    """POST to the immediate webhook. Returns True on success, False otherwise."""
    if not config.WEBHOOK_IMMEDIATE:
        return False
    try:
        resp = requests.post(
            config.WEBHOOK_IMMEDIATE, json=event, timeout=config.DEFAULT_TIMEOUT
        )
        return resp.ok
    except requests.RequestException:
        return False


def dispatch(event: dict) -> str:
    """Dispatch one event per its alert_route. Returns the channel used."""
    route = event.get("alert_route", "silent")

    if route == "immediate":
        if _post_webhook(event):
            return "immediate"
        _append_jsonl(config.QUEUE_FILE, event)  # webhook unavailable -> queue
        return "queue"

    if route == "queue":
        _append_jsonl(config.QUEUE_FILE, event)
        return "queue"

    _append_jsonl(config.SILENT_LOG, event)
    return "silent"


def dispatch_all(events: list[dict]) -> dict:
    """Dispatch every event and return a {channel: count} summary."""
    summary = {"immediate": 0, "queue": 0, "silent": 0}
    for event in events:
        channel = dispatch(event)
        summary[channel] = summary.get(channel, 0) + 1
    return summary
