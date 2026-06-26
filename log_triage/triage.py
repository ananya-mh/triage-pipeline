#!/usr/bin/env python3
"""
Track 2 - single request to Gemma (Google AI Studio / Gemini API).

Sends ONE raw log dump to a Gemma model and gets back a strict JSON object:
  { service_name, timestamp, error_severity, suggested_remediation }

Run:
  export GEMINI_API_KEY="paste api key"
  python3 triage.py
  python3 triage.py path/to/other_logs.txt   # optional: different file
"""

import json
import os
import sys
import urllib.request
import urllib.error

# --- config -----------------------------------------------------------------
API_KEY = os.environ.get("GEMINI_API_KEY")
MODEL = "gemma-4-31b-it"          # try gemma-4-26b-a4b-it if rate-limited
LOG_FILE = sys.argv[1] if len(sys.argv) > 1 else "sample_production_logs.txt"

ENDPOINT = (
    f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"
)

REQUIRED_KEYS = ["service_name", "timestamp", "error_severity", "suggested_remediation"]

# --- the prompt --------------------------------------------------------------
# NOTE: Gemma has NO system role on this API, so ALL instructions live in the
# single user turn. We ask for raw JSON only and parse defensively below.
INSTRUCTIONS = """You are a log triage engine for production Linux systems.

You are given a raw text dump of system logs. Most lines are BENIGN NOISE and
must be ignored, including:
  - routine "session opened/closed for user ..." lines
  - repeated sshd "authentication failure" lines from brute-force scanners
  - normal "ftpd ... connection from ..." lines
  - kernel boot / hardware probe messages

Find the SINGLE most severe anomalous, failed, or fatal event in the log.

Respond with ONE JSON object and NOTHING else (no prose, no markdown fences).
Use EXACTLY these keys:
  - "service_name": the daemon/process that produced the line (e.g. "logrotate", "klogind", "sshd")
  - "timestamp": the timestamp exactly as it appears on that log line
  - "error_severity": one of "INFO", "WARNING", "ERROR", "CRITICAL"
  - "suggested_remediation": one concise, actionable sentence

LOGS:
"""

# Gemma-4 is a heavy chain-of-thought model: given only instructions it will
# "think out loud" in markdown and often never emit clean JSON. We force the
# issue with an assistant PREFILL -- we seed a model turn that already opens
# the object with "{", so the model can only continue *inside* the JSON.
# The "{" is stripped from the response, so we prepend it back before parsing.
PREFILL = "{"


def build_payload(log_text: str) -> dict:
    return {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": INSTRUCTIONS + log_text}],
            },
            {
                "role": "model",
                "parts": [{"text": PREFILL}],
            },
        ],
        # sampling knobs Gemma honors. Low temp + seed = reproducible JSON.
        "generationConfig": {
            "temperature": 0,
            "topP": 0.95,
            "topK": 40,
            "maxOutputTokens": 2048,
            "seed": 42,
        },
    }


def call_gemma(payload: dict) -> str:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        ENDPOINT,
        data=data,
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": API_KEY,
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    # dig the text out of the Gemini-API response envelope
    return body["candidates"][0]["content"]["parts"][0]["text"]


def extract_json(text: str) -> dict:
    """Strip markdown fences if present, then parse the first JSON object."""
    t = text.strip()
    if t.startswith("```"):
        t = t.strip("`")
        t = t[t.find("{"):]
    start, end = t.find("{"), t.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"No JSON object found in model output:\n{text}")
    return json.loads(t[start : end + 1])


def main() -> int:
    if not API_KEY:
        print("ERROR: set GEMINI_API_KEY first:\n"
              '  export GEMINI_API_KEY="your-key"', file=sys.stderr)
        return 1
    if not os.path.exists(LOG_FILE):
        print(f"ERROR: log file not found: {LOG_FILE}", file=sys.stderr)
        return 1

    with open(LOG_FILE, "r", encoding="utf-8", errors="replace") as f:
        log_text = f.read()

    print(f"-> sending {len(log_text)} chars from {LOG_FILE} to {MODEL} ...\n")

    try:
        # prepend the prefilled "{" the model continued from
        raw = PREFILL + call_gemma(build_payload(log_text))
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code} error:\n{e.read().decode('utf-8', 'replace')}",
              file=sys.stderr)
        return 1

    print("=== RAW MODEL OUTPUT ===")
    print(raw)

    obj = extract_json(raw)
    missing = [k for k in REQUIRED_KEYS if k not in obj]
    if missing:
        print(f"\nWARNING: missing required keys: {missing}", file=sys.stderr)

    print("\n=== VALIDATED JSON (webhook-ready) ===")
    print(json.dumps(obj, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
