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

# Max chunks sent to the model before falling back to keyword prioritization.
# Under this budget, Gemma triages the full noise-reduced stream (it owns
# anomaly detection). Above it, keyword filtering kicks in to stay affordable,
# and the dropped lines are logged — never silently discarded.
MAX_CHUNKS = int(os.getenv("MAX_CHUNKS", "15"))

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
