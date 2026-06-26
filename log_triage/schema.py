"""Shared JSON schema contract and severity enums."""

from enum import Enum
import jsonschema


class ErrorSeverity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    FATAL = "FATAL"


# Severity the model emits for a clean chunk with no anomaly. Deliberately NOT
# part of ErrorSeverity / ANOMALY_SCHEMA: "no anomaly" is the ABSENCE of an
# event, not an event with severity NONE, so it must never appear as a row in
# the output. validator.extract_and_validate recognizes and drops it.
NO_ANOMALY_SEVERITY = "NONE"


class AlertRoute(str, Enum):
    SILENT = "silent"
    QUEUE = "queue"
    IMMEDIATE = "immediate"


ANOMALY_SCHEMA = {
    "type": "object",
    "properties": {
        "service_name": {"type": "string"},
        "timestamp": {"type": "string"},
        "error_severity": {
            "type": "string",
            "enum": [s.value for s in ErrorSeverity],
        },
        "severity_score": {"type": "integer", "minimum": 0, "maximum": 100},
        "suggested_remediation": {"type": "string"},
        "source_line": {"type": "string"},
        "alert_route": {
            "type": "string",
            "enum": [r.value for r in AlertRoute],
        },
    },
    "required": [
        "service_name",
        "timestamp",
        "error_severity",
        "suggested_remediation",
        "source_line",
    ],
    "additionalProperties": False,
}


def validate_event(event: dict) -> tuple[bool, list[str]]:
    """Returns (is_valid, list_of_error_messages)."""
    validator = jsonschema.Draft7Validator(ANOMALY_SCHEMA)
    errors = list(validator.iter_errors(event))
    if errors:
        return False, [e.message for e in errors]
    return True, []
