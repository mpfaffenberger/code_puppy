"""Hashline engine for file editing.

Each line gets tagged with a 4-char content hash so models can reference
lines by hash instead of reproducing exact text. This eliminates the
fragile "find exact string" pattern and makes edits robust to whitespace
or minor content drift.
"""

import hashlib
from collections import OrderedDict


class HashlineMismatchError(Exception):
    """Raised when a hashline reference doesn't match current file content."""

    def __init__(
        self, line: int, expected_hash: str, actual_hash: str, actual_content: str
    ):
        self.line = line
        self.expected_hash = expected_hash
        self.actual_hash = actual_hash
        self.actual_content = actual_content
        super().__init__(
            f"Line {line}: expected hash '{expected_hash}', "
            f"got '{actual_hash}' for content: {actual_content!r}"
        )


# ---------------------------------------------------------------------------
# Core hashing
# ---------------------------------------------------------------------------


def line_hash(content: str) -> str:
    """Return a 4-char hex hash of *content* using FNV-1a.
    
    FNV-1a (Fowler-Noll-Vo) is chosen for speed and good distribution on short strings.
    The 4-char hex (65536 values) provides strong collision resistance even in
    multi-thousand line files. Paired with line numbers, collisions are near-zero.
    """
    # FNV-1a 32-bit parameters
    FNV_32_PRIME = 0x01000193
    FNV1_32A_INIT = 0x811c9dc5
    
    h = FNV1_32A_INIT
    for byte in content.encode("utf-8"):
        h ^= byte
        h = (h * FNV_32_PRIME) & 0xffffffff
    
    # Take lowest 2 bytes, format as 4-char hex
    return f"{h & 0xffff:04x}"


def compute_file_hashes(content: str) -> dict[int, str]:
    """Return ``{line_number: hash}`` for every line (1-based)."""
    return {i: line_hash(line) for i, line in enumerate(content.splitlines(), start=1)}


# ---------------------------------------------------------------------------
# Formatting & parsing
# ---------------------------------------------------------------------------


def format_hashlines(content: str, start_line: int = 1, max_line_len: int = 2000) -> str:
    """Convert file content to hashline display format.

    Args:
        content: Raw file content.
        start_line: Line number offset (1-based). Use this when formatting
            a partial read so line numbers match the actual file.
        max_line_len: Maximum line length before truncation (default: 2000).

    Example output::

        1:a3f1|function hello() {
        2:f10e|  return "world";
    """
    lines = content.splitlines()
    parts: list[str] = []
    truncated = False
    
    for i, raw in enumerate(lines, start=start_line):
        line_content = raw
        if len(raw) > max_line_len:
            line_content = raw[:max_line_len] + "...[truncated]"
            truncated = True
        h = line_hash(raw)  # Hash the original content, not truncated
        parts.append(f"{i}:{h}|{line_content}")
    
    result = "\n".join(parts)
    if truncated:
        result = f"[Some lines truncated at {max_line_len} chars]\n" + result
    
    return result


def parse_hashline_ref(ref: str) -> tuple[int, str]:
    """Parse ``"42:a3f1"`` → ``(42, "a3f1")``.  Raises *ValueError* on bad format."""
    if ":" not in ref:
        raise ValueError(f"Invalid hashline ref (missing ':'): {ref!r}")
    line_str, hash_str = ref.split(":", maxsplit=1)
    try:
        line_num = int(line_str)
    except ValueError:
        raise ValueError(f"Invalid line number in ref: {ref!r}") from None
    if line_num < 1:
        raise ValueError(f"Line number must be >= 1, got {line_num} in ref: {ref!r}")
    if len(hash_str) != 4:
        raise ValueError(
            f"Hash must be exactly 4 hex chars, got {hash_str!r} in ref: {ref!r}"
        )
    return line_num, hash_str


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate_hashes(
    refs: list[tuple[int, str]],
    current_content: str,
) -> list[str]:
    """Validate each ``(line, hash)`` pair against *current_content*.

    Returns a list of human-readable error messages (empty == all valid).
    """
    file_hashes = compute_file_hashes(current_content)
    lines = current_content.splitlines()
    total_lines = len(file_hashes)
    errors: list[str] = []

    for line_num, expected in refs:
        if line_num > total_lines:
            errors.append(
                f"Line {line_num} out of range (file has {total_lines} lines)"
            )
            continue
        if line_num < 1:
            errors.append(
                f"Line {line_num} is invalid (must be >= 1)"
            )
            continue
        actual = file_hashes[line_num]
        if actual != expected:
            # Get actual content for better error message
            actual_content = lines[line_num - 1] if line_num <= len(lines) else ""
            content_preview = actual_content[:50] + "..." if len(actual_content) > 50 else actual_content
            errors.append(
                f"Hash mismatch at line {line_num}: expected '{expected}' but file has '{actual}' "
                f"(file may have changed since last read). Content: {content_preview!r}"
            )
    return errors


# ---------------------------------------------------------------------------
# LRU cache (stdlib-only, no functools.lru_cache – we cache per file path)
# ---------------------------------------------------------------------------

_CACHE_MAX = 100
_hashline_cache: OrderedDict[str, dict[int, str]] = OrderedDict()


def cache_file_hashes(file_path: str, hashes: dict[int, str]) -> None:
    """Store *hashes* for *file_path*, evicting oldest if over capacity."""
    if file_path in _hashline_cache:
        _hashline_cache.move_to_end(file_path)
    _hashline_cache[file_path] = hashes
    while len(_hashline_cache) > _CACHE_MAX:
        _hashline_cache.popitem(last=False)


def get_cached_hashes(file_path: str) -> dict[int, str] | None:
    """Return cached hashes for *file_path*, or ``None`` if missing."""
    if file_path in _hashline_cache:
        _hashline_cache.move_to_end(file_path)
        return _hashline_cache[file_path]
    return None


def invalidate_cache(file_path: str) -> None:
    """Remove *file_path* from the cache."""
    _hashline_cache.pop(file_path, None)


# ---------------------------------------------------------------------------
# Edit application
# ---------------------------------------------------------------------------


def _resolve_edit_range(edit: dict) -> tuple[int, int, str, str]:
    """Return ``(start_line, end_line, start_hash, end_hash)`` for an edit.
    
    All operations support optional end_ref for range operations.
    """
    start_line, start_hash = parse_hashline_ref(edit["start_ref"])
    operation = edit["operation"]
    
    # Check if this is a range operation (has end_ref)
    if edit.get("end_ref"):
        end_line, end_hash = parse_hashline_ref(edit["end_ref"])
        if end_line < start_line:
            raise ValueError(
                f"end_ref line ({end_line}) < start_ref line ({start_line})"
            )
        return start_line, end_line, start_hash, end_hash
    
    # Single-line operation
    return start_line, start_line, start_hash, start_hash


def _check_overlaps(ranges: list[tuple[int, int, int]]) -> list[str]:
    """Detect overlapping edit ranges.  *ranges* = [(start, end, index), …]."""
    sorted_ranges = sorted(ranges, key=lambda r: (r[0], r[1]))
    errors: list[str] = []
    for i in range(len(sorted_ranges) - 1):
        _, end_a, idx_a = sorted_ranges[i]
        start_b, _, idx_b = sorted_ranges[i + 1]
        if end_a >= start_b:
            errors.append(
                f"Edit {idx_a} (ending line {end_a}) overlaps with "
                f"edit {idx_b} (starting line {start_b})"
            )
    return errors


def apply_hashline_edits(
    file_path: str,
    edits: list[dict],
) -> dict:
    """Apply a batch of hashline-referenced edits to *file_path*.

    Each *edit* dict must contain:

    - ``operation``: ``"replace"`` | ``"insert"`` | ``"delete"``
    - ``start_ref``: e.g. ``"42:a3f1"`` (line:hash reference)
    - ``end_ref``:  optional, for range operations (e.g., delete lines 5-10)
    - ``new_content``: replacement text (required for replace/insert, empty for delete)

    Operations:
    - **replace**: Replace line(s) with new content. With end_ref, replaces a range.
    - **insert**: Insert new content after the line. With end_ref, inserts after end_ref line.
    - **delete**: Delete line(s). With end_ref, deletes the range start_ref to end_ref.

    Returns ``{"success": bool, "content": str, "errors": list[str]}``.
    """
    # 1. Read current file
    try:
        with open(file_path, "r", encoding="utf-8") as fh:
            current_content = fh.read()
    except OSError as exc:
        return {"success": False, "content": "", "errors": [str(exc)]}

    lines = current_content.splitlines()
    errors: list[str] = []

    # 2. Parse & collect all refs for batch validation
    parsed: list[tuple[int, int, dict]] = []  # (start, end, edit)
    all_refs: list[tuple[int, str]] = []

    for i, edit in enumerate(edits):
        valid_ops = ("replace", "insert", "delete")
        op = edit.get("operation", "")
        if op not in valid_ops:
            errors.append(
                f"Edit {i}: unknown operation '{op}'. Must be one of: {', '.join(valid_ops)}"
            )
            continue
        try:
            start, end, s_hash, e_hash = _resolve_edit_range(edit)
        except ValueError as exc:
            errors.append(f"Edit {i}: {exc}")
            continue

        all_refs.append((start, s_hash))
        if end != start:
            all_refs.append((end, e_hash))
        parsed.append((start, end, edit))

    if errors:
        return {"success": False, "content": current_content, "errors": errors}

    # Validate ALL hashes up-front – reject entire batch on any mismatch
    hash_errors = validate_hashes(all_refs, current_content)
    if hash_errors:
        return {"success": False, "content": current_content, "errors": hash_errors}

    # 3. Check for overlapping edits
    ranges_for_overlap = []
    for i, (start, end, edit) in enumerate(parsed):
        if edit["operation"] == "insert" and not edit.get("end_ref"):
            # Single-line inserts don't occupy a range; they go *after* the line
            continue
        ranges_for_overlap.append((start, end, i))

    overlap_errors = _check_overlaps(ranges_for_overlap)
    if overlap_errors:
        return {"success": False, "content": current_content, "errors": overlap_errors}

    # 4. Apply edits in reverse line order so indices stay stable
    sorted_edits = sorted(parsed, key=lambda p: p[0], reverse=True)

    for start, end, edit in sorted_edits:
        op = edit["operation"]
        new_lines = (
            edit.get("new_content", "").splitlines() if edit.get("new_content") else []
        )
        start_idx = start - 1  # 0-based
        end_idx = end  # exclusive upper bound for slice replacement

        if op == "replace":
            # Replace single line or range
            lines[start_idx : end_idx + 1] = new_lines
        elif op == "insert":
            # Insert after start_idx (or after end_idx if range specified)
            insert_pos = end_idx + 1 if end != start else start_idx + 1
            lines[insert_pos:insert_pos] = new_lines
        elif op == "delete":
            # Delete single line or range
            del lines[start_idx : end_idx + 1]

    new_content = "\n".join(lines)
    # Preserve trailing newline if original had one
    if current_content.endswith("\n"):
        new_content += "\n"

    # 5. Invalidate cache & write
    invalidate_cache(file_path)
    with open(file_path, "w", encoding="utf-8") as fh:
        fh.write(new_content)
    cache_file_hashes(file_path, compute_file_hashes(new_content))

    return {"success": True, "content": new_content, "errors": []}
