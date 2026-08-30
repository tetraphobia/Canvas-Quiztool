from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from canvas_code_bot.core.schedule_overlap import (  # re-exported for tests
    _EPOCH,
    _FAR,
    _find_overlaps,
    _overlaps,
    _schedule_window,
)

_TZ = "America/New_York"
_LOCAL_TZ = ZoneInfo(_TZ)
_DEFAULT_WINDOW_DAYS = 14


def _validate(
    random: bool, code: str | None, cron: str | None, at: str | None
) -> str | None:
    if not cron and not at:
        return "Provide either `cron` (recurring) or `at` (one-shot)."
    if cron and at:
        return "Provide `cron` **or** `at`, not both."
    if not random and not code:
        return "Provide a `code` value when `random=false`."
    if random and code:
        return "Cannot specify both `random=true` and a fixed `code`."
    return None


def _parse_dt(s: str) -> datetime:
    """Parse ISO 8601; naive datetimes assumed America/New_York, returned as naive UTC."""
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_LOCAL_TZ)
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def _parse_ids(raw: str) -> list[int]:
    ids = []
    for part in raw.split(","):
        part = part.strip()
        if part.isdigit():
            ids.append(int(part))
    return ids
