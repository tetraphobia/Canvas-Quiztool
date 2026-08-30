"""
Tests for SqlQuizRepo, SqlScheduleRepo, SqlHistoryRepo, SqlConfigRepo.

All tests run against an in-memory SQLite database — no real file, no mocking.
"""
from datetime import datetime

import pytest
from sqlalchemy import create_engine

from canvas_code_bot.core.models import (
    Config,
    HistoryEntry,
    Quiz,
    RotationOutcome,
    Schedule,
    ScheduleKind,
    ScheduleStatus,
    TriggeredBy,
)
from canvas_code_bot.data import entities as _entities_module  # noqa: F401 – registers ORM classes
from canvas_code_bot.data.db import Base, make_session_factory
from canvas_code_bot.data.repositories import (
    SqlConfigRepo,
    SqlHistoryRepo,
    SqlQuizRepo,
    SqlScheduleRepo,
)

# ── Helpers ───────────────────────────────────────────────────────────────────

_NOW = datetime(2026, 8, 27, 12, 0, 0)


def _quiz(**kw) -> Quiz:
    return Quiz(
        course_id=kw.get("course_id", 1),
        assignment_id=kw.get("assignment_id", 10),
        course_name=kw.get("course_name", "Course A"),
        quiz_name=kw.get("quiz_name", "Quiz 1"),
        added_by=kw.get("added_by", 999),
        added_at=kw.get("added_at", _NOW),
    )


def _schedule(quiz_id: int, **kw) -> Schedule:
    return Schedule(
        quiz_id=quiz_id,
        kind=kw.get("kind", ScheduleKind.RECURRING),
        group_id=kw.get("group_id", None),
        timezone="America/New_York",
        random=kw.get("random", True),
        status=kw.get("status", ScheduleStatus.ACTIVE),
        created_by=kw.get("created_by", 999),
        created_at=kw.get("created_at", _NOW),
        cron=kw.get("cron", "*/15 * * * *"),
        end_at=kw.get("end_at", None),
    )


def _history(quiz_id: int, **kw) -> HistoryEntry:
    return HistoryEntry(
        quiz_id=quiz_id,
        triggered_by=kw.get("triggered_by", TriggeredBy.MANUAL),
        fired_at=kw.get("fired_at", _NOW),
        code_set=kw.get("code_set", "ABC123"),
        outcome=kw.get("outcome", RotationOutcome.SUCCESS),
        attempts=kw.get("attempts", 1),
    )


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def sf():
    """Fresh in-memory SQLite session factory per test."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return make_session_factory(engine)


@pytest.fixture()
def quiz_repo(sf):
    return SqlQuizRepo(sf)


@pytest.fixture()
def schedule_repo(sf):
    return SqlScheduleRepo(sf)


@pytest.fixture()
def history_repo(sf):
    return SqlHistoryRepo(sf)


@pytest.fixture()
def config_repo(sf):
    return SqlConfigRepo(sf)


# ── QuizRepo ──────────────────────────────────────────────────────────────────

def test_quiz_add_assigns_id(quiz_repo):
    saved = quiz_repo.add(_quiz())
    assert saved.id > 0


def test_quiz_get_round_trips(quiz_repo):
    saved = quiz_repo.add(_quiz(quiz_name="Finals"))
    fetched = quiz_repo.get(saved.id)
    assert fetched is not None
    assert fetched.quiz_name == "Finals"
    assert fetched.course_id == 1


def test_quiz_get_missing_returns_none(quiz_repo):
    assert quiz_repo.get(9999) is None


def test_quiz_get_by_assignment(quiz_repo):
    saved = quiz_repo.add(_quiz(course_id=5, assignment_id=50))
    found = quiz_repo.get_by_assignment(5, 50)
    assert found is not None
    assert found.id == saved.id


def test_quiz_get_by_assignment_not_found(quiz_repo):
    quiz_repo.add(_quiz(course_id=5, assignment_id=50))
    assert quiz_repo.get_by_assignment(5, 99) is None
    assert quiz_repo.get_by_assignment(9, 50) is None


def test_quiz_list_all(quiz_repo):
    quiz_repo.add(_quiz(assignment_id=1))
    quiz_repo.add(_quiz(assignment_id=2))
    assert len(quiz_repo.list_all()) == 2


def test_quiz_list_all_empty(quiz_repo):
    assert quiz_repo.list_all() == []


def test_quiz_update_current_code(quiz_repo):
    saved = quiz_repo.add(_quiz())
    quiz_repo.update_current_code(saved.id, "XYZ789", _NOW)
    updated = quiz_repo.get(saved.id)
    assert updated.current_code == "XYZ789"
    assert updated.current_code_at == _NOW


def test_quiz_remove(quiz_repo):
    saved = quiz_repo.add(_quiz())
    quiz_repo.remove(saved.id)
    assert quiz_repo.get(saved.id) is None


def test_quiz_remove_nonexistent_is_noop(quiz_repo):
    quiz_repo.remove(9999)  # must not raise


# ── ScheduleRepo ──────────────────────────────────────────────────────────────

@pytest.fixture()
def stored_quiz(quiz_repo):
    return quiz_repo.add(_quiz())


def test_schedule_add_assigns_id(schedule_repo, stored_quiz):
    s = schedule_repo.add(_schedule(stored_quiz.id))
    assert s.id > 0


def test_schedule_get_round_trips(schedule_repo, stored_quiz):
    s = schedule_repo.add(_schedule(stored_quiz.id, cron="0 * * * *"))
    fetched = schedule_repo.get(s.id)
    assert fetched is not None
    assert fetched.cron == "0 * * * *"
    assert fetched.kind == ScheduleKind.RECURRING


def test_schedule_get_active_found(schedule_repo, stored_quiz):
    s = schedule_repo.add(_schedule(stored_quiz.id))
    found = schedule_repo.get_active(stored_quiz.id)
    assert found is not None
    assert found.id == s.id


def test_schedule_get_active_not_found(schedule_repo, stored_quiz):
    schedule_repo.add(_schedule(stored_quiz.id, status=ScheduleStatus.COMPLETED))
    assert schedule_repo.get_active(stored_quiz.id) is None


def test_schedule_list_active(sf, quiz_repo, schedule_repo):
    q1 = quiz_repo.add(_quiz(assignment_id=1))
    q2 = quiz_repo.add(_quiz(assignment_id=2))
    q3 = quiz_repo.add(_quiz(assignment_id=3))
    schedule_repo.add(_schedule(q1.id, status=ScheduleStatus.ACTIVE))
    schedule_repo.add(_schedule(q2.id, status=ScheduleStatus.PAUSED))
    schedule_repo.add(_schedule(q3.id, status=ScheduleStatus.ACTIVE))
    assert len(schedule_repo.list_active()) == 2


def test_schedule_list_by_group(sf, quiz_repo, schedule_repo):
    q1 = quiz_repo.add(_quiz(assignment_id=1))
    q2 = quiz_repo.add(_quiz(assignment_id=2))
    q3 = quiz_repo.add(_quiz(assignment_id=3))
    schedule_repo.add(_schedule(q1.id, group_id="grp-A"))
    schedule_repo.add(_schedule(q2.id, group_id="grp-A"))
    schedule_repo.add(_schedule(q3.id, group_id="grp-B"))
    assert len(schedule_repo.list_by_group("grp-A")) == 2
    assert len(schedule_repo.list_by_group("grp-B")) == 1
    assert len(schedule_repo.list_by_group("grp-C")) == 0


def test_schedule_update_status(schedule_repo, stored_quiz):
    s = schedule_repo.add(_schedule(stored_quiz.id))
    schedule_repo.update_status(s.id, ScheduleStatus.COMPLETED)
    assert schedule_repo.get(s.id).status == ScheduleStatus.COMPLETED


def test_schedule_update_last_fired(schedule_repo, stored_quiz):
    s = schedule_repo.add(_schedule(stored_quiz.id))
    fired = datetime(2026, 8, 27, 14, 30, 0)
    schedule_repo.update_last_fired(s.id, fired)
    assert schedule_repo.get(s.id).last_fired_at == fired


def test_schedule_list_active_excludes_expired(sf, quiz_repo, schedule_repo):
    """Schedules whose end_at is in the past must not appear in list_active()."""
    from datetime import timedelta, timezone as tz
    real_now = datetime.now(tz.utc).replace(tzinfo=None)
    q = quiz_repo.add(_quiz(assignment_id=99))
    past_end = real_now - timedelta(hours=1)
    future_end = real_now + timedelta(hours=1)
    schedule_repo.add(_schedule(q.id, end_at=past_end))    # expired
    schedule_repo.add(_schedule(q.id, end_at=future_end))  # still active
    schedule_repo.add(_schedule(q.id))                     # no end_at (forever active)
    active = schedule_repo.list_active()
    assert len(active) == 2
    for s in active:
        assert s.end_at is None or s.end_at >= real_now


def test_schedule_list_for_quiz(sf, quiz_repo, schedule_repo):
    """list_for_quiz returns only active non-expired schedules for the given quiz."""
    from datetime import timedelta, timezone as tz
    real_now = datetime.now(tz.utc).replace(tzinfo=None)
    q1 = quiz_repo.add(_quiz(assignment_id=1))
    q2 = quiz_repo.add(_quiz(assignment_id=2))
    past_end = real_now - timedelta(hours=1)
    schedule_repo.add(_schedule(q1.id))                                               # active, no end
    schedule_repo.add(_schedule(q1.id, end_at=real_now + timedelta(hours=1)))        # active, future end
    schedule_repo.add(_schedule(q1.id, end_at=past_end))                             # expired — excluded
    schedule_repo.add(_schedule(q1.id, status=ScheduleStatus.COMPLETED))             # non-active — excluded
    schedule_repo.add(_schedule(q2.id))                                               # different quiz — excluded
    result = schedule_repo.list_for_quiz(q1.id)
    assert len(result) == 2
    for s in result:
        assert s.quiz_id == q1.id


def test_schedule_remove(schedule_repo, stored_quiz):
    """remove() deletes the specific schedule row."""
    s = schedule_repo.add(_schedule(stored_quiz.id))
    schedule_repo.remove(s.id)
    assert schedule_repo.get(s.id) is None


def test_schedule_remove_nonexistent_is_noop(schedule_repo):
    """remove() on a missing ID must not raise."""
    schedule_repo.remove(99999)


def test_schedule_multiple_per_quiz(schedule_repo, stored_quiz):
    """A quiz can now hold multiple active schedules."""
    from datetime import timedelta, timezone as tz
    real_now = datetime.now(tz.utc).replace(tzinfo=None)
    s1 = schedule_repo.add(_schedule(stored_quiz.id, cron="0 9 * * *",
                                     end_at=real_now + timedelta(days=7)))
    s2 = schedule_repo.add(_schedule(stored_quiz.id, cron="0 17 * * *",
                                     end_at=real_now + timedelta(days=14)))
    result = schedule_repo.list_for_quiz(stored_quiz.id)
    assert len(result) == 2
    assert {r.id for r in result} == {s1.id, s2.id}


def test_schedule_replace_for_quiz(schedule_repo, stored_quiz):
    schedule_repo.add(_schedule(stored_quiz.id, cron="0 * * * *"))
    replaced = schedule_repo.replace_for_quiz(
        stored_quiz.id, _schedule(stored_quiz.id, cron="*/5 * * * *")
    )
    # New schedule has the updated cron
    assert replaced.cron == "*/5 * * * *"
    # Active schedule for the quiz reflects the replacement
    active = schedule_repo.get_active(stored_quiz.id)
    assert active is not None
    assert active.cron == "*/5 * * * *"


def test_schedule_list_all_returns_every_row(sf, quiz_repo, schedule_repo):
    """list_all() returns ALL rows regardless of status or end_at."""
    from datetime import timedelta, timezone as tz
    real_now = datetime.now(tz.utc).replace(tzinfo=None)
    q = quiz_repo.add(_quiz(assignment_id=77))
    # expired (end_at in the past)
    schedule_repo.add(_schedule(q.id, end_at=real_now - timedelta(hours=1)))
    # completed status
    schedule_repo.add(_schedule(q.id, status=ScheduleStatus.COMPLETED))
    # normal active
    schedule_repo.add(_schedule(q.id))
    result = schedule_repo.list_all()
    assert len(result) == 3


def test_schedule_list_all_empty(schedule_repo):
    assert schedule_repo.list_all() == []


def test_schedule_update_changes_cron(schedule_repo, stored_quiz):
    s = schedule_repo.add(_schedule(stored_quiz.id, cron="0 9 * * *"))
    updated = Schedule(
        id=s.id,
        quiz_id=s.quiz_id,
        kind=s.kind,
        group_id=s.group_id,
        timezone=s.timezone,
        random=s.random,
        status=s.status,
        created_by=s.created_by,
        created_at=s.created_at,
        cron="0 17 * * *",
    )
    result = schedule_repo.update_schedule(updated)
    assert result.cron == "0 17 * * *"
    assert schedule_repo.get(s.id).cron == "0 17 * * *"


def test_schedule_update_kind_switch(schedule_repo, stored_quiz):
    """Switching from RECURRING to ONESHOT clears cron and sets run_at."""
    run_at = datetime(2026, 9, 1, 9, 0)
    s = schedule_repo.add(_schedule(stored_quiz.id, cron="0 9 * * *"))
    updated = Schedule(
        id=s.id,
        quiz_id=s.quiz_id,
        kind=ScheduleKind.ONESHOT,
        group_id=s.group_id,
        timezone=s.timezone,
        random=s.random,
        status=s.status,
        created_by=s.created_by,
        created_at=s.created_at,
        cron=None,
        run_at=run_at,
    )
    result = schedule_repo.update_schedule(updated)
    assert result.kind == ScheduleKind.ONESHOT
    assert result.cron is None
    assert result.run_at == run_at


def test_schedule_update_preserves_immutable_fields(schedule_repo, stored_quiz):
    """update_schedule never clobbers id, quiz_id, created_by, or created_at."""
    s = schedule_repo.add(_schedule(stored_quiz.id))
    updated = Schedule(
        id=s.id,
        quiz_id=s.quiz_id,
        kind=s.kind,
        group_id=s.group_id,
        timezone=s.timezone,
        random=False,
        fixed_code="NEWFIX",
        status=s.status,
        created_by=s.created_by,
        created_at=s.created_at,
        cron="0 8 * * *",
    )
    result = schedule_repo.update_schedule(updated)
    assert result.id == s.id
    assert result.quiz_id == s.quiz_id
    assert result.created_by == s.created_by
    assert result.created_at == s.created_at
    assert result.random is False
    assert result.fixed_code == "NEWFIX"


def test_schedule_update_not_found_raises(schedule_repo):
    phantom = Schedule(
        id=99999,
        quiz_id=1,
        kind=ScheduleKind.RECURRING,
        timezone="America/New_York",
        random=True,
        status=ScheduleStatus.ACTIVE,
        created_by=0,
        created_at=_NOW,
        cron="0 9 * * *",
    )
    with pytest.raises(ValueError, match="99999"):
        schedule_repo.update_schedule(phantom)


def test_schedule_update_zero_id_raises(schedule_repo, stored_quiz):
    s = _schedule(stored_quiz.id)  # id=None / 0
    with pytest.raises(ValueError):
        schedule_repo.update_schedule(s)


def test_schedule_remove_by_quiz(schedule_repo, stored_quiz):
    s = schedule_repo.add(_schedule(stored_quiz.id))
    schedule_repo.remove_by_quiz(stored_quiz.id)
    assert schedule_repo.get(s.id) is None


# ── HistoryRepo ───────────────────────────────────────────────────────────────

def test_history_record_assigns_id(history_repo, stored_quiz):
    h = history_repo.record(_history(stored_quiz.id))
    assert h.id > 0


def test_history_record_round_trips(history_repo, stored_quiz):
    h = history_repo.record(
        _history(stored_quiz.id, code_set="TESTCD", outcome=RotationOutcome.FAILED, attempts=3)
    )
    last = history_repo.last_for_quiz(stored_quiz.id)
    assert last is not None
    assert last.code_set == "TESTCD"
    assert last.outcome == RotationOutcome.FAILED
    assert last.attempts == 3


def test_history_last_for_quiz_returns_most_recent(history_repo, stored_quiz):
    earlier = datetime(2026, 8, 27, 10, 0)
    later = datetime(2026, 8, 27, 11, 0)
    history_repo.record(_history(stored_quiz.id, fired_at=earlier, code_set="OLD"))
    history_repo.record(_history(stored_quiz.id, fired_at=later, code_set="NEW"))
    last = history_repo.last_for_quiz(stored_quiz.id)
    assert last.code_set == "NEW"


def test_history_last_for_quiz_none_when_empty(history_repo, stored_quiz):
    assert history_repo.last_for_quiz(stored_quiz.id) is None


def test_history_triggered_by_round_trips(history_repo, stored_quiz):
    history_repo.record(_history(stored_quiz.id, triggered_by=TriggeredBy.SCHEDULE))
    assert history_repo.last_for_quiz(stored_quiz.id).triggered_by == TriggeredBy.SCHEDULE


# ── ConfigRepo ────────────────────────────────────────────────────────────────

def test_config_get_returns_default_when_no_row(config_repo):
    cfg = config_repo.get()
    assert cfg.notify_channel_id is None


def test_config_set_channel_creates_row(config_repo):
    config_repo.set_channel(channel_id=111, updated_by=999, at=_NOW)
    cfg = config_repo.get()
    assert cfg.notify_channel_id == 111


def test_config_set_channel_updates_existing(config_repo):
    config_repo.set_channel(111, 999, _NOW)
    config_repo.set_channel(222, 999, _NOW)
    assert config_repo.get().notify_channel_id == 222


def test_config_always_row_id_1(config_repo):
    config_repo.set_channel(111, 999, _NOW)
    assert config_repo.get().id == 1
