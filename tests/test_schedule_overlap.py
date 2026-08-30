"""
Unit tests for the schedule overlap-detection helpers in schedule_commands.py.

All functions under test are pure — no Discord, DB, or Canvas calls.
"""
from datetime import datetime

import pytest

from canvas_code_bot.core.models import Schedule, ScheduleKind, ScheduleStatus
from canvas_code_bot.bot.commands.schedule_commands import (
    _find_overlaps,
    _overlaps,
    _schedule_window,
)

_NOW = datetime(2026, 9, 1, 12, 0, 0)
_D = lambda y, m, d: datetime(y, m, d)  # noqa: E731


def _recurring(start=None, end=None, quiz_id=1, sched_id=0) -> Schedule:
    return Schedule(
        id=sched_id,
        quiz_id=quiz_id,
        kind=ScheduleKind.RECURRING,
        timezone="America/New_York",
        random=True,
        status=ScheduleStatus.ACTIVE,
        created_by=1,
        created_at=_NOW,
        cron="0 9 * * *",
        start_at=start,
        end_at=end,
    )


def _oneshot(run_at, quiz_id=1, sched_id=0) -> Schedule:
    return Schedule(
        id=sched_id,
        quiz_id=quiz_id,
        kind=ScheduleKind.ONESHOT,
        timezone="America/New_York",
        random=True,
        status=ScheduleStatus.ACTIVE,
        created_by=1,
        created_at=_NOW,
        run_at=run_at,
    )


# ── _schedule_window ──────────────────────────────────────────────────────────

def test_window_oneshot_returns_point():
    t = _D(2026, 9, 5)
    s = _oneshot(run_at=t)
    assert _schedule_window(s) == (t, t)


def test_window_recurring_unbounded():
    from canvas_code_bot.bot.commands.schedule_commands import _EPOCH, _FAR
    s = _recurring()
    assert _schedule_window(s) == (_EPOCH, _FAR)


def test_window_recurring_bounded():
    s0 = _D(2026, 9, 1)
    s1 = _D(2026, 9, 14)
    s = _recurring(start=s0, end=s1)
    assert _schedule_window(s) == (s0, s1)


# ── _overlaps ─────────────────────────────────────────────────────────────────

def test_two_unbounded_recurring_always_overlap():
    assert _overlaps(_recurring(), _recurring())


def test_two_bounded_non_overlapping():
    a = _recurring(start=_D(2026, 8, 1), end=_D(2026, 8, 31))
    b = _recurring(start=_D(2026, 9, 1), end=_D(2026, 9, 30))
    # Aug ends before Sep starts — touching at a single point counts as overlap
    # (a.end == b.start → a0<=b1 and b0<=a1 holds since Aug31 < Sep1 → False)
    assert not _overlaps(a, b)


def test_two_bounded_overlapping():
    a = _recurring(start=_D(2026, 9, 1), end=_D(2026, 9, 14))
    b = _recurring(start=_D(2026, 9, 10), end=_D(2026, 9, 30))
    assert _overlaps(a, b)


def test_oneshot_and_recurring_never_overlap():
    """A one-shot and a recurring schedule serve different purposes; no conflict."""
    rec = _recurring(start=_D(2026, 9, 1), end=_D(2026, 9, 30))
    shot = _oneshot(run_at=_D(2026, 9, 15))  # run_at is inside the recurring window
    assert not _overlaps(rec, shot)
    assert not _overlaps(shot, rec)


def test_unbounded_recurring_does_not_overlap_oneshot():
    """Even an unbounded recurring must not flag a one-shot as a conflict."""
    rec = _recurring()  # window = [EPOCH, FAR]
    shot = _oneshot(run_at=_D(2026, 9, 5))
    assert not _overlaps(rec, shot)
    assert not _overlaps(shot, rec)


def test_two_oneshots_same_time_overlap():
    t = _D(2026, 9, 5)
    assert _overlaps(_oneshot(run_at=t), _oneshot(run_at=t))


def test_two_oneshots_different_time_no_overlap():
    a = _oneshot(run_at=_D(2026, 9, 5))
    b = _oneshot(run_at=_D(2026, 9, 6))
    assert not _overlaps(a, b)


def test_unbounded_recurring_overlaps_any_bounded():
    unbounded = _recurring()
    bounded = _recurring(start=_D(2099, 1, 1), end=_D(2099, 12, 31))
    assert _overlaps(unbounded, bounded)


# ── _find_overlaps ────────────────────────────────────────────────────────────

def test_find_overlaps_empty_existing():
    proposed = _recurring()
    assert _find_overlaps(proposed, []) == []


def test_find_overlaps_returns_conflicting():
    proposed = _recurring(start=_D(2026, 9, 1), end=_D(2026, 9, 30))
    conflict = _recurring(start=_D(2026, 9, 15), end=_D(2026, 10, 15), sched_id=7)
    no_conflict = _recurring(start=_D(2026, 10, 1), end=_D(2026, 10, 31), sched_id=8)
    result = _find_overlaps(proposed, [conflict, no_conflict])
    assert result == [conflict]


def test_find_overlaps_multiple_conflicts():
    proposed = _recurring()   # unbounded — overlaps everything
    s1 = _recurring(start=_D(2026, 9, 1), end=_D(2026, 9, 14), sched_id=1)
    s2 = _recurring(start=_D(2026, 10, 1), end=_D(2026, 10, 31), sched_id=2)
    result = _find_overlaps(proposed, [s1, s2])
    assert len(result) == 2


def test_find_overlaps_no_conflict_when_windows_disjoint():
    proposed = _recurring(start=_D(2026, 10, 1), end=_D(2026, 10, 31))
    existing = _recurring(start=_D(2026, 8, 1), end=_D(2026, 8, 31), sched_id=5)
    assert _find_overlaps(proposed, [existing]) == []
