from __future__ import annotations

from datetime import datetime
from typing import Iterator

import pytest

from canvas_code_bot.core.exceptions import ScheduleConflictError
from canvas_code_bot.core.models import Schedule, ScheduleKind, ScheduleStatus
from canvas_code_bot.scheduling.schedule_service import ScheduleService

_NOW = datetime(2026, 9, 1, 12, 0, 0)
_D = lambda y, m, d: datetime(y, m, d)  # noqa: E731


# ── Fakes ─────────────────────────────────────────────────────────────────────

class FakeScheduleRepo:
    def __init__(self, schedules: list[Schedule] | None = None) -> None:
        self._schedules: list[Schedule] = list(schedules or [])
        self._next_id = 1

    def add(self, schedule: Schedule) -> Schedule:
        s = Schedule(**{**schedule.__dict__, "id": self._next_id})
        self._next_id += 1
        self._schedules.append(s)
        return s

    def get(self, schedule_id: int) -> Schedule | None:
        return next((s for s in self._schedules if s.id == schedule_id), None)

    def get_active(self, quiz_id: int) -> Schedule | None:
        return next((s for s in self._schedules if s.quiz_id == quiz_id), None)

    def list_active(self) -> list[Schedule]:
        return [s for s in self._schedules if s.status == ScheduleStatus.ACTIVE]

    def list_for_quiz(self, quiz_id: int) -> list[Schedule]:
        return [s for s in self._schedules if s.quiz_id == quiz_id and s.status == ScheduleStatus.ACTIVE]

    def list_by_group(self, group_id: str) -> list[Schedule]:
        return [s for s in self._schedules if s.group_id == group_id and s.status == ScheduleStatus.ACTIVE]

    def list_all(self) -> list[Schedule]:
        return list(self._schedules)

    def update_status(self, schedule_id: int, status: ScheduleStatus) -> None:
        for s in self._schedules:
            if s.id == schedule_id:
                self._schedules[self._schedules.index(s)] = Schedule(**{**s.__dict__, "status": status})
                break

    def update_last_fired(self, schedule_id: int, fired_at: datetime) -> None:
        pass

    def replace_for_quiz(self, quiz_id: int, schedule: Schedule) -> Schedule:
        self._schedules = [s for s in self._schedules if s.quiz_id != quiz_id]
        return self.add(schedule)

    def remove(self, schedule_id: int) -> None:
        self._schedules = [s for s in self._schedules if s.id != schedule_id]

    def remove_by_quiz(self, quiz_id: int) -> None:
        self._schedules = [s for s in self._schedules if s.quiz_id != quiz_id]

    def update_schedule(self, schedule: Schedule) -> Schedule:
        for i, s in enumerate(self._schedules):
            if s.id == schedule.id:
                self._schedules[i] = schedule
                return schedule
        raise ValueError(f"Schedule {schedule.id} not found.")


class FakeScheduler:
    def __init__(self) -> None:
        self.added: list[Schedule] = []
        self.removed: list[str] = []

    def add_or_replace_job(self, schedule: Schedule) -> None:
        self.added.append(schedule)

    def remove_job_for_group(self, group_id: str) -> None:
        self.removed.append(group_id)


def _recurring(
    quiz_id: int = 1,
    sched_id: int = 0,
    group_id: str = "group-a",
    start: datetime | None = None,
    end: datetime | None = None,
) -> Schedule:
    return Schedule(
        id=sched_id,
        quiz_id=quiz_id,
        kind=ScheduleKind.RECURRING,
        group_id=group_id,
        timezone="America/New_York",
        random=True,
        status=ScheduleStatus.ACTIVE,
        created_by=1,
        created_at=_NOW,
        cron="0 9 * * *",
        start_at=start,
        end_at=end,
    )


def _oneshot(
    quiz_id: int = 1,
    sched_id: int = 0,
    group_id: str = "group-a",
    run_at: datetime | None = None,
) -> Schedule:
    return Schedule(
        id=sched_id,
        quiz_id=quiz_id,
        kind=ScheduleKind.ONESHOT,
        group_id=group_id,
        timezone="America/New_York",
        random=True,
        status=ScheduleStatus.ACTIVE,
        created_by=1,
        created_at=_NOW,
        run_at=run_at or _D(2026, 9, 5),
    )


def _svc(
    schedules: list[Schedule] | None = None,
) -> tuple[ScheduleService, FakeScheduleRepo, FakeScheduler]:
    repo = FakeScheduleRepo(schedules)
    scheduler = FakeScheduler()
    service = ScheduleService(schedule_repo=repo, scheduler=scheduler)
    return service, repo, scheduler


# ── add_schedule ──────────────────────────────────────────────────────────────

def test_add_schedule_persists_and_registers_job():
    svc, repo, scheduler = _svc()
    proposed = _recurring(quiz_id=1)

    saved = svc.add_schedule(proposed)

    assert saved.id == 1
    assert len(repo.list_all()) == 1
    assert len(scheduler.added) == 1


def test_add_schedule_conflict_raises():
    existing = _recurring(quiz_id=1, sched_id=5)
    svc, repo, scheduler = _svc(schedules=[existing])
    proposed = _recurring(quiz_id=1)  # same unbounded window → conflict

    with pytest.raises(ScheduleConflictError) as exc_info:
        svc.add_schedule(proposed)

    assert 5 in exc_info.value.conflict_ids
    assert len(scheduler.added) == 0


def test_add_schedule_no_conflict_when_windows_disjoint():
    existing = _recurring(
        quiz_id=1, sched_id=5, start=_D(2026, 8, 1), end=_D(2026, 8, 31)
    )
    svc, repo, scheduler = _svc(schedules=[existing])
    proposed = _recurring(
        quiz_id=1, start=_D(2026, 9, 1), end=_D(2026, 9, 30)
    )

    saved = svc.add_schedule(proposed)

    assert saved.id is not None
    assert len(scheduler.added) == 1


def test_add_schedule_conflict_error_contains_all_conflicting_ids():
    s1 = _recurring(quiz_id=1, sched_id=5, start=_D(2026, 9, 1), end=_D(2026, 9, 14))
    s2 = _recurring(quiz_id=1, sched_id=6, start=_D(2026, 9, 10), end=_D(2026, 9, 30))
    svc, _, _ = _svc(schedules=[s1, s2])
    proposed = _recurring(quiz_id=1)  # unbounded → overlaps both

    with pytest.raises(ScheduleConflictError) as exc_info:
        svc.add_schedule(proposed)

    assert set(exc_info.value.conflict_ids) == {5, 6}


# ── update_schedule ───────────────────────────────────────────────────────────

def test_update_schedule_persists_and_re_registers_when_timing_changed():
    existing = _recurring(quiz_id=1, sched_id=1)
    svc, repo, scheduler = _svc(schedules=[existing])
    updated = _recurring(quiz_id=1, sched_id=1)

    svc.update_schedule(updated, timing_changed=True)

    assert repo.get(1) == updated
    assert len(scheduler.added) == 1


def test_update_schedule_does_not_re_register_when_timing_unchanged():
    existing = _recurring(quiz_id=1, sched_id=1)
    svc, repo, scheduler = _svc(schedules=[existing])
    updated = _recurring(quiz_id=1, sched_id=1)

    svc.update_schedule(updated, timing_changed=False)

    assert len(scheduler.added) == 0


def test_update_schedule_conflict_with_other_schedule_raises():
    s1 = _recurring(quiz_id=1, sched_id=1, start=_D(2026, 8, 1), end=_D(2026, 8, 31))
    s2 = _recurring(quiz_id=1, sched_id=2, start=_D(2026, 9, 1), end=_D(2026, 9, 30))
    svc, _, _ = _svc(schedules=[s1, s2])

    # Update s1 to overlap s2's window
    updated = _recurring(quiz_id=1, sched_id=1, start=_D(2026, 9, 10), end=_D(2026, 9, 20))
    with pytest.raises(ScheduleConflictError) as exc_info:
        svc.update_schedule(updated, timing_changed=True)

    assert 2 in exc_info.value.conflict_ids


def test_update_schedule_does_not_conflict_with_itself():
    existing = _recurring(quiz_id=1, sched_id=1)
    svc, repo, _ = _svc(schedules=[existing])
    updated = _recurring(quiz_id=1, sched_id=1)

    # Should not raise even though it overlaps with itself
    svc.update_schedule(updated, timing_changed=False)
    assert repo.get(1) == updated


# ── delete_schedule ───────────────────────────────────────────────────────────

def test_delete_schedule_removes_from_repo():
    s = _recurring(quiz_id=1, sched_id=1, group_id="g1")
    svc, repo, _ = _svc(schedules=[s])

    svc.delete_schedule(1)

    assert repo.get(1) is None


def test_delete_schedule_removes_apscheduler_job_when_group_empty():
    s = _recurring(quiz_id=1, sched_id=1, group_id="g1")
    svc, _, scheduler = _svc(schedules=[s])

    svc.delete_schedule(1)

    assert "g1" in scheduler.removed


def test_delete_schedule_keeps_apscheduler_job_when_group_not_empty():
    s1 = _recurring(quiz_id=1, sched_id=1, group_id="g1")
    s2 = _recurring(quiz_id=2, sched_id=2, group_id="g1")
    svc, _, scheduler = _svc(schedules=[s1, s2])

    svc.delete_schedule(1)

    assert "g1" not in scheduler.removed


def test_delete_schedule_not_found_raises():
    svc, _, _ = _svc()

    with pytest.raises(ValueError, match="99"):
        svc.delete_schedule(99)


# ── remove_jobs_for_quiz ──────────────────────────────────────────────────────

def test_remove_jobs_for_quiz_removes_job_for_solo_group():
    s = _recurring(quiz_id=1, sched_id=1, group_id="g1")
    svc, _, scheduler = _svc(schedules=[s])

    svc.remove_jobs_for_quiz(quiz_id=1)

    assert "g1" in scheduler.removed


def test_remove_jobs_for_quiz_keeps_job_when_other_quiz_in_group():
    s1 = _recurring(quiz_id=1, sched_id=1, group_id="g1")
    s2 = _recurring(quiz_id=2, sched_id=2, group_id="g1")
    svc, _, scheduler = _svc(schedules=[s1, s2])

    svc.remove_jobs_for_quiz(quiz_id=1)

    assert "g1" not in scheduler.removed


def test_remove_jobs_for_quiz_no_schedules_is_noop():
    svc, _, scheduler = _svc()

    svc.remove_jobs_for_quiz(quiz_id=99)

    assert scheduler.removed == []
