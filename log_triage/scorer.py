"""Severity scoring engine and alert routing logic.

Maps a validated anomaly to a 0-100 severity_score, then to an alert_route
(silent | queue | immediate) using the thresholds in config. Critical services
get a bump so e.g. an sshd/kernel ERROR outranks a generic one.
"""

from log_triage import config

# Base score per declared severity level.
_SEVERITY_BASE = {"INFO": 10, "WARNING": 40, "ERROR": 70, "FATAL": 95}

# Added when the event's service is in config.CRITICAL_SERVICES.
_CRITICAL_BUMP = 15


def route_for_score(score: int) -> str:
    """Map a severity_score to an alert route via config thresholds."""
    if score >= config.SEVERITY_THRESHOLDS["immediate"]:
        return "immediate"
    if score >= config.SEVERITY_THRESHOLDS["queue"]:
        return "queue"
    return "silent"


def score_event(event: dict) -> dict:
    """Annotate an event with severity_score and alert_route, in place."""
    severity = (event.get("error_severity") or "INFO").upper()
    score = _SEVERITY_BASE.get(severity, 10)

    service = (event.get("service_name") or "").lower()
    if any(crit in service for crit in config.CRITICAL_SERVICES):
        score = min(100, score + _CRITICAL_BUMP)

    event["severity_score"] = score
    event["alert_route"] = route_for_score(score)
    return event


def score_events(events: list[dict]) -> list[dict]:
    """Score a list of events in place and return it."""
    for event in events:
        score_event(event)
    return events
