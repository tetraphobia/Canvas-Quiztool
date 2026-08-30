from __future__ import annotations

from datetime import timezone

from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger

from canvas_code_bot.core.models import Schedule, ScheduleKind


def _parse_crontab(expr: str) -> dict:
    parts = expr.split()
    if len(parts) != 5:
        raise ValueError(
            f"Expected 5-field crontab (minute hour day month weekday), "
            f"got {len(parts)} field(s): {expr!r}"
        )
    keys = ("minute", "hour", "day", "month", "day_of_week")
    return dict(zip(keys, parts))


def build_trigger(schedule: Schedule) -> CronTrigger | DateTrigger:
    """Returns a CronTrigger for recurring schedules or a DateTrigger for one-shot schedules."""
    if schedule.kind == ScheduleKind.RECURRING:
        return CronTrigger(
            **_parse_crontab(schedule.cron),
            timezone=schedule.timezone,
            start_date=schedule.start_at.replace(tzinfo=timezone.utc) if schedule.start_at else None,
            end_date=schedule.end_at.replace(tzinfo=timezone.utc) if schedule.end_at else None,
        )

    return DateTrigger(run_date=schedule.run_at, timezone="UTC")
