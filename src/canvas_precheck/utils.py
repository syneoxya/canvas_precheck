import os

def time_ago(seconds: int) -> str:
    if seconds < 60: return f"{seconds}s"
    minutes = seconds // 60
    if minutes < 60: return f"{minutes}m"
    hours = minutes // 60
    if hours < 48: return f"{hours}h"
    return f"{hours // 24}d"

def normalize_filename(filename: str, aliases: dict, expected: list[str]) -> tuple[str, bool, bool]:
    if filename in aliases:
        new_name = aliases[filename]
        return new_name, True, (new_name in expected if expected else True)
    return filename, False, (filename in expected if expected else True)

def ext_allowed(path: str, allowed_exts: list[str]) -> bool:
    ext = os.path.splitext(path)[1].lower()
    allowed = [e.lower() for e in allowed_exts]
    return ext in allowed