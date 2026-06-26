"""
chunker.py
==========
Splits pre-filtered log lines into chunks for Gemma.

Receives filtered lines from injection.py.
Splits them into overlapping chunks.
Every chunk is sent to Gemma — no reordering, no skipping.

Usage:
    from chunker import get_chunks
    chunks = get_chunks(filtered_lines)
"""

from typing import Optional

# ── config ────────────────────────────────────────────────────────────────────
CHUNK_OVERLAP   = 10
CHARS_PER_TOKEN = 4
TARGET_TOKENS   = 2000
MAX_TOKENS      = 3500                # universal constant


# ── dynamic chunk size ────────────────────────────────────────────────────────

def dynamic_chunk_size(lines: list[str]) -> int:
    """
    Calculate chunk size from actual line lengths.

    Instead of hardcoding a number, we target TARGET_TOKENS
    per chunk and derive how many lines that is for this file.

    Short lines (~80 chars)  → more lines per chunk
    Long lines (~300 chars)  → fewer lines per chunk
    """
    avg_chars  = sum(len(l) for l in lines) / len(lines)
    avg_tokens = max(1, avg_chars / CHARS_PER_TOKEN)
    target     = int(TARGET_TOKENS / avg_tokens)
    ceiling    = int(MAX_TOKENS    / avg_tokens)
    return max(10, min(target, ceiling))


# ── chunking ──────────────────────────────────────────────────────────────────

def get_chunks(lines: list[str], chunk_size: Optional[int] = None) -> list[dict]:
    """
    Split filtered lines into overlapping chunks.

    - Order preserved — no reordering by severity
    - Every chunk hits Gemma
    - Overlap ensures no error is cut at a boundary

    Args:
        lines:      Pre-filtered lines from injection.py
        chunk_size: Override dynamic size (optional, for testing)

    Returns:
        List of chunk dicts:
            content    - text to send to Gemma
            line_count - number of lines in chunk
            start_line - start index in original lines
            end_line   - end index in original lines
    """
    if not lines:
        print("[chunker] No lines to chunk.")
        return []

    size   = chunk_size or dynamic_chunk_size(lines)
    chunks = []
    start  = 0

    while start < len(lines):
        end   = min(start + size, len(lines))
        batch = lines[start:end]

        chunks.append({
            "content"   : "\n".join(batch),
            "line_count": len(batch),
            "start_line": start,
            "end_line"  : end,
        })

        start += size - CHUNK_OVERLAP

    print(f"[chunker] lines in   : {len(lines)}")
    print(f"[chunker] chunk size : {size} lines (dynamic)")
    print(f"[chunker] overlap    : {CHUNK_OVERLAP} lines")
    print(f"[chunker] chunks out : {len(chunks)}")

    return chunks


# ── standalone test ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python3 chunker.py <filtered_log_file.txt>")
        sys.exit(1)

    with open(sys.argv[1], "r", encoding="utf-8", errors="replace") as f:
        lines = [l.rstrip() for l in f if l.strip()]

    chunks = get_chunks(lines)

    print(f"\n{'='*50}")
    print("  CHUNK PREVIEW — first 2 chunks")
    print(f"{'='*50}")
    for i, c in enumerate(chunks[:2]):
        print(f"\n── Chunk {i+1} "
              f"(lines {c['start_line']}–{c['end_line']}, "
              f"{c['line_count']} lines) ──")
        print(c["content"][:300])
        if len(c["content"]) > 300:
            print("  ...")