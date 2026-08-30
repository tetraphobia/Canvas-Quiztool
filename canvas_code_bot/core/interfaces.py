from __future__ import annotations

from datetime import datetime
from typing import Protocol

from canvas_code_bot.core.models import (
    AllowedRole,
    CanvasQuizInfo,
    CodePolicy,
    Config,
    HistoryEntry,
    Quiz,
    Schedule,
    ScheduleStatus,
)


class CanvasPort(Protocol):
    """Quiz-code operations against the Canvas API (Classic and New Quizzes)."""

    async def get_quiz(
        self, course_id: int, assignment_id: int
    ) -> CanvasQuizInfo:
        """Fetch quiz metadata for an assignment.

        Raises CanvasAuthError on 401, CanvasNotFoundError on 404,
        CanvasError on other failures.
        """
        ...

    async def get_classic_quiz_by_quiz_id(
        self, course_id: int, quiz_id: int
    ) -> CanvasQuizInfo:
        """Fetch Classic quiz metadata by quiz_id.

        The returned CanvasQuizInfo.assignment_id is populated from the API response.
        Raises CanvasAuthError on 401, CanvasNotFoundError on 404,
        CanvasError on other failures.
        """
        ...

    async def set_access_code(self, quiz: Quiz, code: str) -> int:
        """Set the quiz's access code. Returns the HTTP status code.

        Raises CanvasAuthError on 401, CanvasNotFoundError on 404,
        CanvasError on other failures.
        """
        ...

    async def verify_access_code(self, quiz: Quiz, code: str) -> bool:
        """Confirm the quiz's current access code matches code.

        Returns True if it matches, False otherwise. Raises CanvasError on failure.
        """
        ...


class NotifierPort(Protocol):
    """Posts embeds to Discord relay channels."""

    async def notify_success(
        self, channel_id: int, quiz: Quiz, code: str
    ) -> None:
        """Post a 'new code' embed to the relay channel (single quiz)."""
        ...

    async def notify_group_success(
        self, channel_id: int, quizzes: list[Quiz], code: str
    ) -> None:
        """Post a single combined 'new code' embed for multiple quizzes."""
        ...

    async def notify_error(
        self, channel_id: int, quiz: Quiz, error: str, admin_id: int
    ) -> None:
        """Post an error embed and ping the admin."""
        ...


class CodeGen(Protocol):
    """Generates access codes according to a policy."""

    def generate(self, policy: CodePolicy) -> str:
        """Return a new code string. Must be pure / no side-effects."""
        ...


class QuizRepo(Protocol):
    """Persistence for registered quizzes."""

    def add(self, quiz: Quiz) -> Quiz:
        """Persist a new quiz; returns it with ``id`` assigned."""
        ...

    def get(self, quiz_id: int) -> Quiz | None: ...

    def get_by_assignment(
        self, course_id: int, assignment_id: int
    ) -> Quiz | None: ...

    def get_by_resource_id(
        self, course_id: int, resource_id: int
    ) -> Quiz | None:
        """Look up a quiz by course_id + resource_id (quiz_id for Classic, assignment_id for New)."""
        ...

    def list_all(self) -> list[Quiz]: ...

    def update_current_code(
        self, quiz_id: int, code: str, at: datetime
    ) -> None: ...

    def update_notify_channel(
        self, quiz_id: int, channel_id: int | None
    ) -> None: ...

    def remove(self, quiz_id: int) -> None:
        """Delete a quiz and all associated records."""
        ...


class ScheduleRepo(Protocol):
    """Persistence for rotation schedules."""

    def add(self, schedule: Schedule) -> Schedule:
        """Persist a new schedule; returns it with ``id`` assigned."""
        ...

    def get(self, schedule_id: int) -> Schedule | None: ...

    def get_active(self, quiz_id: int) -> Schedule | None:
        """Return the single active schedule for a quiz, or None."""
        ...

    def list_active(self) -> list[Schedule]:
        """All schedules with status ACTIVE whose end_at has not yet passed."""
        ...

    def list_for_quiz(self, quiz_id: int) -> list[Schedule]:
        """All active, non-expired schedules for a specific quiz."""
        ...

    def list_by_group(self, group_id: str) -> list[Schedule]:
        """All active schedules sharing a group_id."""
        ...

    def update_status(
        self, schedule_id: int, status: ScheduleStatus
    ) -> None: ...

    def update_last_fired(
        self, schedule_id: int, fired_at: datetime
    ) -> None: ...

    def replace_for_quiz(self, quiz_id: int, schedule: Schedule) -> Schedule:
        """
        Atomically remove any existing schedule for the quiz and persist the
        new one. Returns the new schedule with ``id`` assigned.
        """
        ...

    def list_all(self) -> list[Schedule]:
        """All schedules regardless of status or expiry."""
        ...

    def remove(self, schedule_id: int) -> None:
        """Delete a specific schedule by its ID."""
        ...

    def remove_by_quiz(self, quiz_id: int) -> None: ...

    def update_schedule(self, schedule: Schedule) -> Schedule:
        """
        Persist all mutable fields of an existing schedule identified by schedule.id.
        Returns the updated Schedule. Raises ValueError if id is 0 or not found.
        """
        ...


class HistoryRepo(Protocol):
    """Append-only audit trail of rotation attempts."""

    def record(self, entry: HistoryEntry) -> HistoryEntry:
        """Persist a history entry; returns it with ``id`` assigned."""
        ...

    def last_for_quiz(self, quiz_id: int) -> HistoryEntry | None:
        """Most recent entry for a quiz, or None."""
        ...


class ConfigRepo(Protocol):
    """Single-row runtime configuration."""

    def get(self) -> Config:
        """Return current config; creates defaults row on first call."""
        ...

    def set_channel(
        self, channel_id: int, updated_by: int, at: datetime
    ) -> None:
        """Update the global relay channel."""
        ...


class AllowedRoleRepo(Protocol):
    """Persisted set of Discord roles that may use /quizbot commands."""

    def add(self, role_id: int, added_by: int, at: datetime) -> AllowedRole:
        """Add a role to the allowed set; idempotent if already present."""
        ...

    def remove(self, role_id: int) -> None:
        """Remove a role; no-op if it was not in the set."""
        ...

    def list_all(self) -> list[AllowedRole]: ...

    def has_any(self, role_ids: set[int]) -> bool:
        """Return True if at least one of ``role_ids`` is in the allowed set."""
        ...
