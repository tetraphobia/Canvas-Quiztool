from __future__ import annotations


def parse_ids(raw: str) -> list[int]:
    """Parse a comma-separated string of integers into a list."""
    ids = []
    for part in raw.split(","):
        part = part.strip()
        if part.isdigit():
            ids.append(int(part))
    return ids
