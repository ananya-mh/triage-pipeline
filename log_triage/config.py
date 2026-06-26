"""Threshold configs, webhook URLs, retry settings."""

import os
from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
# Gemma 4 is the project's target model (matches the original triage.py).
# Override via MODEL_NAME env var, e.g. "gemma-4-26b-a4b-it" if rate-limited.
MODEL_NAME = os.getenv("MODEL_NAME", "gemma-4-31b-it")

CHUNK_SIZE = 80
CHUNK_OVERLAP = 10

MAX_RETRIES = 2
RETRY_DELAY = 1

OUTPUT_PATH = "output/triage_output.json"

CRITICAL_SERVICES = [
    "sshd",
    "kernel",
    "systemd",
    "namenode",
    "datanode",
    "resourcemanager",
    "journalnode",
    "zkfc",
]

SEVERITY_THRESHOLDS = {
    "immediate": 80,
    "queue": 40,
}

WEBHOOK_IMMEDIATE = ""
QUEUE_FILE = "output/queued_alerts.jsonl"
SILENT_LOG = "output/silent_log.jsonl"

DEFAULT_TIMEOUT = 30
