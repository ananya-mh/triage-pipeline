# triage-pipeline

A Python utility that consumes raw production system logs, routes them through Google's Gemini API, and outputs validated JSON anomaly reports.

## Log Filtering (`ingestion.py`)

The filtering module reduces raw log files to only the lines relevant for anomaly detection, minimizing tokens sent to the LLM.

### How it works

The pipeline runs in two stages:

1. **Noise removal (`prefilter`)** — Drops lines matching known noise patterns and collapses consecutive duplicates (normalized by stripping timestamps and PIDs so lines differing only by those fields are treated as dupes).

2. **Context-aware keyword filter (`context_aware_filter`)** — Scans for lines containing priority keywords (e.g. `failure`, `error`, `fatal`, `timeout`, `denied`), keeps those lines plus surrounding context lines (default 3 above and below), and returns everything in original chronological order. If no priority lines are found, all lines pass through unchanged.

### Noise profiles

Noise patterns are organized into profiles that can be combined:

| Profile | Drops |
|---------|-------|
| `common` | Blank lines, heartbeats, healthchecks, separator lines |
| `linux` | Session opened/closed, check pass, ftpd connections, cupsd, syslogd restart |
| `hdfs` | PacketResponder terminating, Receiving block, NameSystem.allocateBlock |

The selected profile is always combined with `common`. Default profile is `linux`.

### Usage

```bash
# Default: Linux_2k.log with linux profile
python ingestion.py

# Custom file
python ingestion.py path/to/logfile.log

# Custom file with hdfs profile
python ingestion.py path/to/hdfs.log hdfs
```

Output is written to `output/filtered_logs.txt`.

### Running tests

```bash
python -m pytest tests/test_ingestion.py -v
```
