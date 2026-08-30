"""
Pure unit tests for scheduling/triggers.py.

No I/O — just verify the right APScheduler trigger type is built with the
correct attributes from a Schedule domain object.
"""
from datetime import datetime

import pytest
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger

from canvas_code_bot.core.models import Schedule, ScheduleKind, ScheduleStatus
from canvas_code_bot.scheduling.triggers import build_trigger

_NOW = datetime(2026, 8, 27, 12, 0, 0)
_TZ = "America/New_York"


def _recurring(**kw) -> Schedule:
    return Schedule(
        quiz_id=1,
        kind=ScheduleKind.RECURRING,
        timezone=_TZ,
        random=True,
        status=ScheduleStatus.ACTIVE,
        created_by=999,
        created_at=_NOW,
        cron=kw.get("cron", "*/15 * * * *"),
        start_at=kw.get("start_at"),
        end_at=kw.get("end_at"),
    )


def _oneshot(**kw) -> Schedule:
    return Schedule(
        quiz_id=1,
        kind=ScheduleKind.ONESHOT,
        timezone=_TZ,
        random=True,
        status=ScheduleStatus.ACTIVE,
        created_by=999,
        created_at=_NOW,
        run_at=kw.get("run_at", datetime(2026, 9, 1, 14, 0, 0)),
    )


# ── trigger type ──────────────────────────────────────────────────────────────

def test_recurring_produces_cron_trigger():
    assert isinstance(build_trigger(_recurring()), CronTrigger)


def test_oneshot_produces_date_trigger():
    assert isinstance(build_trigger(_oneshot()), DateTrigger)


# ── CronTrigger attributes ────────────────────────────────────────────────────

def test_cron_trigger_timezone():
    trigger = build_trigger(_recurring())
    # APScheduler stores timezone as a tzinfo object; str() gives IANA name
    assert "New_York" in str(trigger.timezone)


def test_cron_trigger_from_standard_expression():
    """Various cron expressions parse without error."""
    for cron in ["*/15 * * * *", "0 9 * * 1-5", "30 14 * * *", "0 0 * * 0"]:
        trigger = build_trigger(_recurring(cron=cron))
        assert isinstance(trigger, CronTrigger)


def test_cron_trigger_start_date_propagated():
    start = datetime(2026, 9, 1, 8, 0, 0)
    trigger = build_trigger(_recurring(start_at=start))
    assert trigger.start_date is not None


def test_cron_trigger_end_date_propagated():
    end = datetime(2026, 9, 15, 23, 59, 0)
    trigger = build_trigger(_recurring(end_at=end))
    assert trigger.end_date is not None


def test_cron_trigger_no_window_when_not_set():
    trigger = build_trigger(_recurring())
    assert trigger.start_date is None
    assert trigger.end_date is None


# ── DateTrigger attributes ────────────────────────────────────────────────────

def test_date_trigger_run_date():
    run_at = datetime(2026, 9, 5, 10, 30, 0)
    trigger = build_trigger(_oneshot(run_at=run_at))
    # DateTrigger.run_date is a tz-aware datetime in the trigger's timezone
    assert trigger.run_date.year == run_at.year
    assert trigger.run_date.month == run_at.month
    assert trigger.run_date.day == run_at.day
    assert trigger.run_date.hour == run_at.hour
    assert trigger.run_date.minute == run_at.minute


def test_date_trigger_timezone_is_utc():
    trigger = build_trigger(_oneshot())
    assert "UTC" in str(trigger.run_date.tzinfo)
