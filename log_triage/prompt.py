"""System prompt constants and Gemini call wrapper."""

import google.generativeai as genai
from log_triage import config

genai.configure(api_key=config.GEMINI_API_KEY)

SYSTEM_PROMPT = """\
You are a production log triage assistant. Analyze the log lines below and identify anomalies.

Return ONLY a raw JSON array. No preamble, no markdown fences, no explanation.

Each anomaly object must have exactly these fields:
- "service_name": string — the service or component that produced the log line
- "timestamp": string — ISO 8601 timestamp extracted from the log line
- "error_severity": one of "INFO", "WARNING", "ERROR", "FATAL"
- "suggested_remediation": string — specific, actionable remediation (not generic advice)
- "source_line": string — the exact raw log line that triggered this detection

If no anomalies are found, return an empty array: []

Rules:
- Only flag genuine anomalies: errors, crashes, failures, resource exhaustion, security events.
- Do NOT flag routine info, startup messages, or heartbeats.
- The source_line must be copied verbatim from the input.
- Timestamps must be in ISO 8601 format. If the original format differs, convert it.
"""

FALLBACK_PROMPT = """\
Analyze these server logs. Return a JSON array of anomalies found.

Each object needs: service_name (string), timestamp (ISO 8601), error_severity (INFO/WARNING/ERROR/FATAL), suggested_remediation (actionable fix), source_line (exact log line).

Return [] if no anomalies. Return ONLY the JSON array, nothing else.
"""

_model = genai.GenerativeModel(config.MODEL_NAME)


def call_gemini(chunk: str, use_fallback: bool = False) -> str:
    """Send a log chunk to Gemini and return the raw response text."""
    prompt = FALLBACK_PROMPT if use_fallback else SYSTEM_PROMPT
    response = _model.generate_content(
        f"{prompt}\n\n--- LOG CHUNK ---\n{chunk}\n--- END ---"
    )
    return response.text
