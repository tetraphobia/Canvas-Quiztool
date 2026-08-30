from __future__ import annotations

from canvas_code_bot.core.exceptions import ScheduleConflictError
from canvas_code_bot.core.interfaces import ScheduleRepo
from canvas_code_bot.core.models import Schedule
from canvas_code_bot.core.schedule_overlap import _find_overlaps
from canvas_code_bot.scheduling.scheduler import RotationScheduler


class ScheduleService:
    """Manages schedule persistence and APScheduler job registration."""

    def __init__(self, schedule_repo: ScheduleRepo, scheduler: RotationScheduler) -> None:
        self._repo = schedule_repo
        self._scheduler = scheduler

    def add_schedule(self, proposed: Schedule) -> Schedule:
        """Persist a new schedule and register its APScheduler job.

        Raises ScheduleConflictError if the proposed schedule overlaps an existing one.
        """
        existing = self._repo.list_for_quiz(proposed.quiz_id)
        conflicts = _find_overlaps(proposed, existing)
        if conflicts:
            raise ScheduleConflictError([s.id for s in conflicts])
        saved = self._repo.add(proposed)
        self._scheduler.add_or_replace_job(saved)
        return saved

    def update_schedule(self, updated: Schedule, timing_changed: bool) -> Schedule:
        """Persist changes to an existing schedule.

        Re-registers the APScheduler job when timing_changed is True.
        Raises ScheduleConflictError if the update creates an overlap with another schedule.
        """
        others = [
            s for s in self._repo.list_for_quiz(updated.quiz_id) if s.id != updated.id
        ]
        conflicts = _find_overlaps(updated, others)
        if conflicts:
            raise ScheduleConflictError([s.id for s in conflicts])
        saved = self._repo.update_schedule(updated)
        if timing_changed:
            self._scheduler.add_or_replace_job(updated)
        return saved

    def delete_schedule(self, schedule_id: int) -> None:
        """Delete a schedule by ID and remove its APScheduler job if the group is now empty."""
        sched = self._repo.get(schedule_id)
        if sched is None:
            raise ValueError(f"Schedule {schedule_id} not found.")
        group_id = sched.group_id
        self._repo.remove(schedule_id)
        if group_id and not self._repo.list_by_group(group_id):
            self._scheduler.remove_job_for_group(group_id)

    def remove_jobs_for_quiz(self, quiz_id: int) -> None:
        """Remove APScheduler jobs for groups that will be empty once quiz_id's schedules are gone.

        Call this before deleting the quiz so the repo can still answer queries.
        """
        active = self._repo.list_for_quiz(quiz_id)
        group_ids = {s.group_id for s in active if s.group_id}
        for gid in group_ids:
            others = [s for s in self._repo.list_by_group(gid) if s.quiz_id != quiz_id]
            if not others:
                self._scheduler.remove_job_for_group(gid)
