"""Shared JSON schema contract and severity enums."""

from enum import Enum
import jsonschema


class ErrorSeverity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    FATAL = "FATAL"


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
