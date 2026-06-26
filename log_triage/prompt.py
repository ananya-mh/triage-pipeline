"""System prompt constants and Gemini call wrapper."""

import google.generativeai as genai
from log_triage import config

genai.configure(api_key=config.GEMINI_API_KEY)

SYSTEM_PROMPT = """\
You are a silent production log triage engine. You work with ANY log format
(Linux syslog, HDFS, Apache, Windows Event Log, Android logcat, OpenSSH, Spark,
Zookeeper, ...). You never ask questions, never explain, never add prose.

OUTPUT CONTRACT
- Respond with ONE raw JSON ARRAY and nothing else. No markdown, no code fences,
  no commentary before or after.
- Each element is one anomaly object. Return [] if the chunk shows only normal,
  healthy operation with no genuine anomaly.
- The output must be parseable by Python's json.loads().

EACH ANOMALY OBJECT — EXACTLY THESE KEYS:
{"service_name": "...", "timestamp": "...", "error_severity": "...", "suggested_remediation": "...", "source_line": "..."}

FIELD RULES
service_name:
- Extract from the log line (e.g. "sshd", "DataNode", "httpd", "kernel").
- Infer from context when implicit ("dfs.DataNode" -> "DataNode"). Use "unknown"
  only if truly indeterminable.

timestamp:
- Copy it VERBATIM from the source_line. Do NOT reformat or convert it.
- Preserve the exact original format (e.g. "081109 203518", "Jun 14 15:16:01",
  "2024-01-15T03:42:11Z"). Verbatim timestamps keep results stable across runs.

error_severity — EXACTLY one of: INFO WARNING ERROR FATAL
- Map non-standard labels: critical/crit/severe/emergency/emerg/alert -> FATAL;
  warn -> WARNING; trace/debug/notice -> INFO.
- If ambiguous, infer from the event:
    crash / data loss / service down / OOM killer        -> FATAL
    degraded / retries / partial failure / block missing -> ERROR
    slow / unusual but non-breaking                      -> WARNING
    informational only                                   -> INFO

suggested_remediation:
- ONE actionable sentence referencing the actual service/host/component.
- Good: "Restart the DataNode on 10.251.43.147 and verify block replication."
- Never vague ("investigate", "check the logs", "contact support").

source_line:
- The exact raw log line that triggered this detection, copied CHARACTER-FOR-
  CHARACTER from the chunk. It MUST appear verbatim in the chunk. Never
  paraphrase, summarize, or invent it. (This is verified downstream.)

WHAT TO FLAG
- Genuine anomalies: errors, crashes, failures, resource exhaustion, security
  events. Ignore routine info, startup/heartbeat/session noise.
- ALWAYS flag security-relevant events even when there is NO error or failure
  keyword: anonymous or unexpected logins, privilege escalation, new sudo/root
  grants, and logins or access from external/unknown IPs. When there is no
  outright failure, use INFO or WARNING severity (do not silently drop them).
- Collapse repeated identical errors into ONE object.
- Treat a multi-line stack trace as ONE event: use the first line's timestamp
  and service, and summarize the root cause in suggested_remediation.
- Non-English lines: analyze the same way; return field values in English.

EXAMPLES (note: JSON array, every object includes a verbatim source_line)
[{"service_name": "DataNode", "timestamp": "081109 203519", "error_severity": "ERROR", "suggested_remediation": "Verify blk_38 replication on 10.251.43.147:50010 and check available disk space", "source_line": "081109 203519 29 WARN dfs.DataNode$DataXceiver: 10.251.43.147:50010:Got exception while serving blk_38 to /10.251.43.147"}, {"service_name": "kernel", "timestamp": "Jun 14 15:16:01", "error_severity": "FATAL", "suggested_remediation": "Increase memory or cap the offending process on this host", "source_line": "Jun 14 15:16:01 combo kernel: Out of memory: Killed process 5678 (java)"}]

[]
"""

FALLBACK_PROMPT = """\
Analyze these server logs. Return ONLY a raw JSON array of anomalies, nothing else.

Each object needs exactly: service_name (string), timestamp (copied VERBATIM from
the line, do not reformat), error_severity (INFO/WARNING/ERROR/FATAL),
suggested_remediation (one specific actionable sentence), source_line (the exact
log line, copied character-for-character from the input).

Flag only genuine errors/failures/security events. Return [] if none.
"""

_model = genai.GenerativeModel(config.MODEL_NAME)

# Assistant-prefill seed: seeding a model turn that opens the array with "[" so
# the model can only continue inside the JSON. NOTE (empirical, Gemma 4): this
# suppresses the chain-of-thought but BACKFIRES -- without the reasoning warm-up
# Gemma loops/repeats the array and degrades key quality ("sourse_line", lowercase
# severities). The CoT version yields cleaner single-array output, and our
# validator scanner already strips the prose. So prefill defaults OFF; kept here
# behind a flag for experimentation (e.g. smaller models / future tuning).
PREFILL = "["

# Generous ceiling: bounds a runaway generation without truncating CoT + JSON.
MAX_OUTPUT_TOKENS = 8192


def call_gemini(chunk: str, use_fallback: bool = False, temperature: float = 0.0,
                use_prefill: bool = False) -> str:
    """Send a log chunk to the model and return the raw response text.

    temperature=0.0 is deterministic (single pass); best-of-N raises it so the
    N draws differ. use_prefill seeds the reply with "[" to force JSON-only
    output -- but it degrades Gemma 4 quality (see PREFILL note), so it is OFF
    by default; the validator's scanner handles the chain-of-thought instead.
    """
    prompt = FALLBACK_PROMPT if use_fallback else SYSTEM_PROMPT
    user_text = f"{prompt}\n\n--- LOG CHUNK ---\n{chunk}\n--- END ---"
    gen_config = genai.types.GenerationConfig(
        temperature=temperature, max_output_tokens=MAX_OUTPUT_TOKENS
    )

    if use_prefill:
        contents = [
            {"role": "user", "parts": [user_text]},
            {"role": "model", "parts": [PREFILL]},
        ]
        response = _model.generate_content(contents, generation_config=gen_config)
        return PREFILL + response.text  # re-attach the seeded "["

    response = _model.generate_content(user_text, generation_config=gen_config)
    return response.text


def sample_candidates(chunk: str, n: int = 4, temperature: float = 0.7,
                      use_fallback: bool = False) -> list[str]:
    """Best-of-N: draw N independent responses for the SAME chunk.

    Returns a list of raw response strings. Diversity comes from temperature>0.
    Selection is NOT done here -- it's the verifier/orchestrator seam (P3/P4):
    parse+validate each candidate, drop events that aren't grounded
    (is_grounded), then keep events appearing in >=k of N samples
    (self-consistency). Hallucinated events rarely repeat -> voting filters them.

    With n=1 this is just call_gemini(); n>1 enables the best-of-N path that
    later becomes ReST/SFT training data (the surviving voted events per chunk).
    """
    return [call_gemini(chunk, use_fallback=use_fallback, temperature=temperature)
            for _ in range(n)]


# is_grounded lives in the validator (validation domain) -- re-exported here so
# the prompt layer's grounding promise and the verifier stay in lock-step.
from .validator import is_grounded  # noqa: E402,F401
