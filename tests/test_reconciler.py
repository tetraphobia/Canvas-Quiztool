"""
Tests for scheduling/reconciler.py.

Uses fake repos and a fake RotationService so no real DB or Canvas calls
are made.  The `now` parameter is fixed to make tests deterministic.
"""
from datetime import datetime, timedelta

import pytest

from canvas_code_bot.core.models import (
    CodePolicy,
    Config,
    Quiz,
    RotationOutcome,
    RotationResult,
    Schedule,
    ScheduleKind,
    ScheduleStatus,
    TriggeredBy,
)
from canvas_code_bot.scheduling.reconciler import Reconciler, _last_expected_fire_utc

# ── Fixed timestamps ──────────────────────────────────────────────────────────

# "now" used throughout: 2026-08-27 14:00 UTC (= 10:00 AM ET in summer)
NOW = datetime(2026, 8, 27, 14, 0, 0)
ONE_HOUR_AGO = NOW - timedelta(hours=1)
TWO_HOURS_AGO = NOW - timedelta(hours=2)
ONE_DAY_AGO = NOW - timedelta(days=1)
TOMORROW = NOW + timedelta(days=1)
_TZ = "America/New_York"


# ── Fakes ─────────────────────────────────────────────────────────────────────

class FakeRotationService:
    def __init__(self):
        self.rotate_calls: list[dict] = []

    async def rotate(self, quiz, triggered_by, schedule_id=None, policy=None, fixed_code=None):
        self.rotate_calls.append({
            "quiz_id": quiz.id,
            "triggered_by": triggered_by,
            "schedule_id": schedule_id,
            "fixed_code": fixed_code,
        })
        return RotationResult(
            outcome=RotationOutcome.SUCCESS, code_set="RECON1", attempts=1
        )

    async def rotate_group(self, pairs, triggered_by, policy=None, fixed_code=None):
        for quiz, schedule_id in pairs:
            self.rotate_calls.append({
                "quiz_id": quiz.id,
                "triggered_by": triggered_by,
                "schedule_id": schedule_id,
                "fixed_code": fixed_code,
            })


class FakeNotifier:
    def __init__(self):
        self.error_calls: list[dict] = []

    async def notify_success(self, channel_id, quiz, code): ...

    async def notify_group_success(self, channel_id, quizzes, code): ...

    async def notify_error(self, channel_id, quiz, error, admin_id):
        self.error_calls.append({"channel_id": channel_id, "quiz_id": quiz.id})


class FakeScheduleRepo:
    def __init__(self, schedules: list[Schedule]):
        self._schedules = schedules

    def list_active(self):
        return [s for s in self._schedules if s.status == ScheduleStatus.ACTIVE]

    def list_by_group(self, group_id: str):
        return [
            s for s in self._schedules
            if s.group_id == group_id and s.status == ScheduleStatus.ACTIVE
        ]


class FakeQuizRepo:
    def __init__(self, quizzes: list[Quiz]):
        self._map = {q.id: q for q in quizzes}

    def get(self, quiz_id):
        return self._map.get(quiz_id)


class FakeConfigRepo:
    def __init__(self, channel_id=99):
        self._cfg = Config(updated_by=0, updated_at=NOW, notify_channel_id=channel_id)

    def get(self):
        return self._cfg

    def set_channel(self, *_): ...


# ── Helpers ───────────────────────────────────────────────────────────────────

def _quiz(quiz_id: int = 1) -> Quiz:
    return Quiz(
        id=quiz_id, course_id=10, assignment_id=100,
        course_name="CS101", quiz_name="Midterm",
        added_by=999, added_at=NOW,
    )


def _recurring(quiz_id=1, sched_id=10, group_id=None, cron="*/30 * * * *",
               last_fired_at=None, start_at=None, end_at=None) -> Schedule:
    return Schedule(
        id=sched_id, quiz_id=quiz_id, kind=ScheduleKind.RECURRING,
        group_id=group_id,
        timezone=_TZ, random=True, status=ScheduleStatus.ACTIVE,
        created_by=999, created_at=ONE_DAY_AGO,
        cron=cron, last_fired_at=last_fired_at,
        start_at=start_at, end_at=end_at,
    )


def _oneshot(quiz_id=1, sched_id=20, group_id=None,
             run_at=ONE_HOUR_AGO, last_fired_at=None) -> Schedule:
    return Schedule(
        id=sched_id, quiz_id=quiz_id, kind=ScheduleKind.ONESHOT,
        group_id=group_id,
        timezone=_TZ, random=True, status=ScheduleStatus.ACTIVE,
        created_by=999, created_at=ONE_DAY_AGO,
        run_at=run_at, last_fired_at=last_fired_at,
    )


def _reconciler(schedules, quizzes=None, notifier=None, rotation_svc=None,
                late_guard_hours=24):
    if quizzes is None:
        quizzes = [_quiz(s.quiz_id) for s in schedules]
    return Reconciler(
        schedule_repo=FakeScheduleRepo(schedules),
        quiz_repo=FakeQuizRepo(quizzes),
        rotation_service=rotation_svc or FakeRotationService(),
        notifier=notifier or FakeNotifier(),
        config_repo=FakeConfigRepo(),
        admin_discord_id=42,
        oneshot_late_guard_hours=late_guard_hours,
    ), rotation_svc or FakeRotationService()


# ── _last_expected_fire_utc unit tests ────────────────────────────────────────

def test_expected_fire_returns_past_time():
    s = _recurring(cron="*/30 * * * *")  # every 30 minutes
    result = _last_expected_fire_utc(s, NOW)
    assert result is not None
    assert result < NOW


def test_expected_fire_none_when_end_passed():
    s = _recurring(cron="*/5 * * * *", end_at=TWO_HOURS_AGO)
    result = _last_expected_fire_utc(s, NOW)
    assert result is None


def test_expected_fire_none_before_start_window():
    s = _recurring(cron="0 9 * * *", start_at=TOMORROW)
    result = _last_expected_fire_utc(s, NOW)
    assert result is None


# ── Recurring schedule reconciliation ─────────────────────────────────────────

async def test_recurring_fires_when_missed():
    svc = FakeRotationService()
    recon = Reconciler(
        schedule_repo=FakeScheduleRepo([_recurring(last_fired_at=None)]),
        quiz_repo=FakeQuizRepo([_quiz()]),
        rotation_service=svc,
        notifier=FakeNotifier(),
        config_repo=FakeConfigRepo(),
        admin_discord_id=42,
    )
    await recon.run(now=NOW)
    assert len(svc.rotate_calls) == 1
    assert svc.rotate_calls[0]["triggered_by"] == TriggeredBy.RECONCILER


async def test_recurring_does_not_fire_when_up_to_date():
    # last_fired_at is just before NOW (within the last 30-min window)
    svc = FakeRotationService()
    recon = Reconciler(
        schedule_repo=FakeScheduleRepo([
            _recurring(cron="*/30 * * * *", last_fired_at=NOW - timedelta(minutes=5))
        ]),
        quiz_repo=FakeQuizRepo([_quiz()]),
        rotation_service=svc,
        notifier=FakeNotifier(),
        config_repo=FakeConfigRepo(),
        admin_discord_id=42,
    )
    await recon.run(now=NOW)
    assert len(svc.rotate_calls) == 0


async def test_recurring_does_not_fire_past_end():
    svc = FakeRotationService()
    recon = Reconciler(
        schedule_repo=FakeScheduleRepo([_recurring(end_at=TWO_HOURS_AGO)]),
        quiz_repo=FakeQuizRepo([_quiz()]),
        rotation_service=svc,
        notifier=FakeNotifier(),
        config_repo=FakeConfigRepo(),
        admin_discord_id=42,
    )
    await recon.run(now=NOW)
    assert len(svc.rotate_calls) == 0


# ── One-shot schedule reconciliation ──────────────────────────────────────────

async def test_oneshot_fires_when_missed_within_guard():
    svc = FakeRotationService()
    recon = Reconciler(
        schedule_repo=FakeScheduleRepo([_oneshot(run_at=ONE_HOUR_AGO)]),
        quiz_repo=FakeQuizRepo([_quiz()]),
        rotation_service=svc,
        notifier=FakeNotifier(),
        config_repo=FakeConfigRepo(),
        admin_discord_id=42,
        oneshot_late_guard_hours=24,
    )
    await recon.run(now=NOW)
    assert len(svc.rotate_calls) == 1


async def test_oneshot_pings_admin_when_too_late():
    notifier = FakeNotifier()
    svc = FakeRotationService()
    very_old = NOW - timedelta(hours=48)
    recon = Reconciler(
        schedule_repo=FakeScheduleRepo([_oneshot(run_at=very_old)]),
        quiz_repo=FakeQuizRepo([_quiz()]),
        rotation_service=svc,
        notifier=notifier,
        config_repo=FakeConfigRepo(channel_id=77),
        admin_discord_id=42,
        oneshot_late_guard_hours=24,
    )
    await recon.run(now=NOW)
    # Should alert admin, NOT fire the rotation
    assert len(svc.rotate_calls) == 0
    assert len(notifier.error_calls) == 1
    assert notifier.error_calls[0]["channel_id"] == 77


async def test_oneshot_skips_already_fired():
    svc = FakeRotationService()
    recon = Reconciler(
        schedule_repo=FakeScheduleRepo([_oneshot(last_fired_at=ONE_HOUR_AGO)]),
        quiz_repo=FakeQuizRepo([_quiz()]),
        rotation_service=svc,
        notifier=FakeNotifier(),
        config_repo=FakeConfigRepo(),
        admin_discord_id=42,
    )
    await recon.run(now=NOW)
    assert len(svc.rotate_calls) == 0


async def test_oneshot_skips_future():
    svc = FakeRotationService()
    recon = Reconciler(
        schedule_repo=FakeScheduleRepo([_oneshot(run_at=TOMORROW)]),
        quiz_repo=FakeQuizRepo([_quiz()]),
        rotation_service=svc,
        notifier=FakeNotifier(),
        config_repo=FakeConfigRepo(),
        admin_discord_id=42,
    )
    await recon.run(now=NOW)
    assert len(svc.rotate_calls) == 0


# ── Edge cases ────────────────────────────────────────────────────────────────

async def test_skips_when_quiz_not_found():
    svc = FakeRotationService()
    recon = Reconciler(
        schedule_repo=FakeScheduleRepo([_recurring(quiz_id=999)]),
        quiz_repo=FakeQuizRepo([]),  # quiz 999 not in repo
        rotation_service=svc,
        notifier=FakeNotifier(),
        config_repo=FakeConfigRepo(),
        admin_discord_id=42,
    )
    await recon.run(now=NOW)
    assert len(svc.rotate_calls) == 0


async def test_multiple_schedules_processed_independently():
    svc = FakeRotationService()
    quiz1, quiz2 = _quiz(1), _quiz(2)
    recon = Reconciler(
        schedule_repo=FakeScheduleRepo([
            _recurring(quiz_id=1, sched_id=10, last_fired_at=None),   # missed
            _recurring(quiz_id=2, sched_id=11, last_fired_at=NOW - timedelta(minutes=5)),  # current
        ]),
        quiz_repo=FakeQuizRepo([quiz1, quiz2]),
        rotation_service=svc,
        notifier=FakeNotifier(),
        config_repo=FakeConfigRepo(),
        admin_discord_id=42,
    )
    await recon.run(now=NOW)
    assert len(svc.rotate_calls) == 1
    assert svc.rotate_calls[0]["quiz_id"] == 1


# ── Group-based code sharing ──────────────────────────────────────────────────

async def test_grouped_schedules_both_fire_on_catchup():
    """Two quizzes in the same group, both missed — both should fire."""
    svc = FakeRotationService()
    group = "test-group-abc"
    quiz1, quiz2 = _quiz(1), _quiz(2)
    recon = Reconciler(
        schedule_repo=FakeScheduleRepo([
            _recurring(quiz_id=1, sched_id=10, group_id=group, last_fired_at=None),
            _recurring(quiz_id=2, sched_id=11, group_id=group, last_fired_at=None),
        ]),
        quiz_repo=FakeQuizRepo([quiz1, quiz2]),
        rotation_service=svc,
        notifier=FakeNotifier(),
        config_repo=FakeConfigRepo(),
        admin_discord_id=42,
    )
    await recon.run(now=NOW)
    assert len(svc.rotate_calls) == 2
    fired_ids = {c["quiz_id"] for c in svc.rotate_calls}
    assert fired_ids == {1, 2}


async def test_grouped_schedules_skip_current_member():
    """Group with two quizzes: one missed, one up-to-date — only missed fires."""
    svc = FakeRotationService()
    group = "test-group-xyz"
    quiz1, quiz2 = _quiz(1), _quiz(2)
    recon = Reconciler(
        schedule_repo=FakeScheduleRepo([
            _recurring(quiz_id=1, sched_id=10, group_id=group, last_fired_at=None),
            _recurring(quiz_id=2, sched_id=11, group_id=group,
                       last_fired_at=NOW - timedelta(minutes=5)),
        ]),
        quiz_repo=FakeQuizRepo([quiz1, quiz2]),
        rotation_service=svc,
        notifier=FakeNotifier(),
        config_repo=FakeConfigRepo(),
        admin_discord_id=42,
    )
    await recon.run(now=NOW)
    assert len(svc.rotate_calls) == 1
    assert svc.rotate_calls[0]["quiz_id"] == 1
