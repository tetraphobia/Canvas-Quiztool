from __future__ import annotations


def parse_ids(raw: str) -> list[int]:
    """Parse a comma-separated string of integers into a list."""
    ids = []
    for part in raw.split(","):
        part = part.strip()
        if part.isdigit():
            ids.append(int(part))
    return ids


def lookup_quiz_ids_by_name(name: str, quiz_repo) -> list[int]:
    """Return the IDs of all registered quizzes with an exact name match."""
    return [q.id for q in quiz_repo.list_all() if q.quiz_name == name]
