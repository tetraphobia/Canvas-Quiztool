from __future__ import annotations

from datetime import datetime

from canvas_code_bot.core.models import Schedule, ScheduleKind

_EPOCH = datetime(2000, 1, 1)
_FAR = datetime(9999, 12, 31)


def _schedule_window(s: Schedule) -> tuple[datetime, datetime]:
    if s.kind == ScheduleKind.ONESHOT:
        t = s.run_at or _EPOCH
        return (t, t)
    return (s.start_at or _EPOCH, s.end_at or _FAR)


def _overlaps(a: Schedule, b: Schedule) -> bool:
    if a.kind != b.kind:
        return False
    a0, a1 = _schedule_window(a)
    b0, b1 = _schedule_window(b)
    return a0 <= b1 and b0 <= a1


def _find_overlaps(proposed: Schedule, existing: list[Schedule]) -> list[Schedule]:
    return [s for s in existing if _overlaps(proposed, s)]
