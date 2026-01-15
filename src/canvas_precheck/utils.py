import os

def time_ago(seconds: int) -> str:
    if seconds < 60: return f"{seconds}s"
    minutes = seconds // 60
    if minutes < 60: return f"{minutes}m"
    hours = minutes // 60
    if hours < 48: return f"{hours}h"
    return f"{hours // 24}d"

import re

def _key(s: str) -> str:
    """
    Normalize a filename for matching (NOT for saving).
    - lowercases
    - trims
    - collapses whitespace
    """
    s = s.strip().lower()
    s = re.sub(r"\s+", " ", s)
    return s

def normalize_filename(filename: str, aliases: dict, expected: list[str]) -> tuple[str, bool, bool]:
    """
    Returns: (normalized_name, was_normalized, is_expected)
    - Uses case/space-insensitive matching against aliases and expected
    - Returns the canonical alias value exactly as provided in config
    """

    # Build lookup maps once per call (cheap at this scale)
    aliases_norm = {_key(k): v for k, v in (aliases or {}).items()}
    expected_norm = {_key(x) for x in (expected or [])}

    fn_key = _key(filename)

    # Alias mapping (case/space-insensitive)
    if fn_key in aliases_norm:
        new_name = aliases_norm[fn_key]
        is_expected = (True if not expected else _key(new_name) in expected_norm)
        return new_name, True, is_expected

    # If no alias matched, check if the filename itself is expected (case/space-insensitive)
    is_expected = (True if not expected else fn_key in expected_norm)

    # Keep original filename unchanged if not aliased
    return filename, False, is_expected

def ext_allowed(path: str, allowed_exts: list[str]) -> bool:
    ext = os.path.splitext(path)[1].lower()
    allowed = [e.lower() for e in allowed_exts]
    return ext in allowed

import os

def canonicalize_filename(
    original: str,
    canonical_base: str
) -> tuple[str, str]:
    """
    Force filename to <canonical_base>.<original extension>.

    Returns:
        (canonical_name, original_extension)
    """
    _, ext = os.path.splitext(original)
    ext = ext.lower() if ext else ""
    canonical_name = f"{canonical_base}{ext}"
    return canonical_name, ext