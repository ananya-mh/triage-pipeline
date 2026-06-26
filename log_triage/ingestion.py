"""Log file reading, chunking, and noise pre-filter."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import re
from log_triage import config

# Lines matching these are dropped entirely
NOISE_PROFILES = {
    "common": [
        re.compile(r"^\s*$"),
        re.compile(r"heartbeat", re.IGNORECASE),
        re.compile(r"health.?check", re.IGNORECASE),
        re.compile(r"^-+$"),
    ],
    "linux": [
        re.compile(r"session opened for user", re.IGNORECASE),
        re.compile(r"session closed for user", re.IGNORECASE),
        re.compile(r"check pass; user unknown", re.IGNORECASE),
        re.compile(r"ftpd\[\d+\]: connection from", re.IGNORECASE),
        re.compile(r"cupsd (startup|shutdown) succeeded", re.IGNORECASE),
        re.compile(r"syslogd.*: restart", re.IGNORECASE),
    ],
    "hdfs": [
        re.compile(r"PacketResponder.*for block.*terminating", re.IGNORECASE),
        re.compile(r"Receiving block", re.IGNORECASE),
        re.compile(r"BLOCK\* NameSystem\.allocateBlock", re.IGNORECASE),
    ],
}

# Strips timestamps (e.g. "Jun 14 15:16:01") and PIDs in brackets (e.g. "[19939]")
_NORMALIZE_RE = re.compile(r"^\w{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2}\s*|\[\d+\]")

# Lines matching these get priority in chunks
PRIORITY_KEYWORDS = [
    "failure",
    "failed",
    "error",
    "fatal",
    "alert",
    "abnormally",
    "denied",
    "refused",
    "timeout",
    "timed out",
    "killed",
    "segfault",
    "out of memory",
    "corrupt",
    "panic",
    "unreachable",
    "shutdown",
    "restart",
]


def detect_profile(lines: list[str]) -> str:
    """Auto-detect the noise profile from the first 50 lines."""
    sample = [line.lower() for line in lines[:50]]
    for line in sample:
        if "dfs." in line or "hdfs" in line or "namenode" in line:
            return "hdfs"
    for line in sample:
        if "sshd" in line or "pam_unix" in line or "cron" in line:
            return "linux"
    return "common"


def read_log_file(filepath: str) -> str:
    """Read the entire log file, handling common encodings."""
    for enc in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            with open(filepath, "r", encoding=enc) as f:
                return f.read()
        except (UnicodeDecodeError, UnicodeError):
            continue
    raise ValueError(f"Could not decode file {filepath} with any supported encoding")


def prefilter(lines: list[str], profile: str = "linux") -> list[str]:
    """Remove blank lines, noise patterns, and consecutive duplicates."""
    noise_patterns = NOISE_PROFILES["common"] + NOISE_PROFILES.get(profile, [])
    filtered = []
    prev_normalized = None
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if any(p.search(stripped) for p in noise_patterns):
            continue
        normalized = _NORMALIZE_RE.sub("", stripped)
        if normalized == prev_normalized:
            continue
        filtered.append(stripped)
        prev_normalized = normalized
    return filtered


def context_aware_filter(lines: list[str], context: int = 3) -> list[str]:
    """Keep priority keyword lines plus surrounding context, in original order."""
    if not lines:
        return []

    flagged = set()
    for i, line in enumerate(lines):
        lower = line.lower()
        if any(kw in lower for kw in PRIORITY_KEYWORDS):
            flagged.add(i)

    if not flagged:
        return lines

    keep = set()
    for i in flagged:
        for j in range(max(0, i - context), min(len(lines), i + context + 1)):
            keep.add(j)

    return [lines[i] for i in sorted(keep)]


def chunk_lines(lines: list[str], chunk_size: int = None) -> list[str]:
    """Group lines into chunks with overlap to preserve boundary context."""
    if chunk_size is None:
        chunk_size = config.CHUNK_SIZE
    overlap = config.CHUNK_OVERLAP
    chunks = []
    start = 0
    while start < len(lines):
        end = min(start + chunk_size, len(lines))
        chunks.append("\n".join(lines[start:end]))
        start += chunk_size - overlap
    return chunks


def get_log_chunks(filepath: str) -> list[str]:
    """Read a log file, filter noise, prioritize, and return chunks for the model."""
    raw = read_log_file(filepath)
    lines = raw.splitlines()
    filtered = prefilter(lines)
    if not filtered:
        return []
    relevant = context_aware_filter(filtered)
    return chunk_lines(relevant)


if __name__ == "__main__":
    project_root = os.path.join(os.path.dirname(__file__), "..")
    default_input = os.path.join(project_root, "data", "Linux_2k.log")
    output_dir = os.path.join(project_root, "output")

    input_path = sys.argv[1] if len(sys.argv) > 1 else default_input
    profile = sys.argv[2] if len(sys.argv) > 2 else "linux"
    raw = read_log_file(input_path)
    lines = raw.splitlines()
    total = len(lines)
    filtered = prefilter(lines, profile=profile)
    relevant = context_aware_filter(filtered)
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "filtered_logs.txt")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(relevant))
    print(f"{len(relevant)} of {total} lines kept. Written to {output_path}")
