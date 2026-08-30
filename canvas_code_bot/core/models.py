from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

DEFAULT_CODE_CHARSET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789" # Excludes I, O, 0, 1
DEFAULT_CODE_LENGTH = 6


class QuizEngine(str, Enum):
    NEW = "new"        # New Quizzes LTI engine (/api/quiz/v1/...)
    CLASSIC = "classic"  # Classic Quizzes (/api/v1/courses/.../quizzes/...)


class ScheduleKind(str, Enum):
    RECURRING = "recurring"
    ONESHOT = "oneshot"


class ScheduleStatus(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    ERROR = "error"


class RotationOutcome(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"


class TriggeredBy(str, Enum):
    SCHEDULE = "schedule"
    MANUAL = "manual"
    RECONCILER = "reconciler"


@dataclass
class CodePolicy:
    """Code-generation parameters for a single rotation."""
    charset: str = DEFAULT_CODE_CHARSET
    length: int = DEFAULT_CODE_LENGTH


@dataclass
class CanvasQuizInfo:
    """Quiz metadata returned from Canvas."""
    assignment_id: int
    title: str
    requires_access_code: bool
    engine: QuizEngine = QuizEngine.NEW
    resource_id: int = 0  # quiz_id for Classic, assignment_id for New
    current_access_code: str | None = None


@dataclass
class Quiz:
    """Registered quiz (maps to the ``quizzes`` table)."""
    course_id: int
    assignment_id: int
    course_name: str
    quiz_name: str
    added_by: int # Discord user id
    added_at: datetime
    id: int = 0
    engine: QuizEngine = QuizEngine.NEW
    resource_id: int = 0  # quiz_id for Classic, assignment_id for New
    notify_channel_id: int | None = None
    current_code: str | None = None
    current_code_at: datetime | None = None


@dataclass
class Schedule:
    """Rotation schedule (maps to the ``schedules`` table)."""
    quiz_id: int
    kind: ScheduleKind
    timezone: str # (IANA) Defaults to "America/New_York"
    random: bool
    status: ScheduleStatus
    created_by: int
    created_at: datetime
    id: int = 0
    group_id: str | None = None  # shared UUID for quizzes scheduled together
    cron: str | None = None
    run_at: datetime | None = None
    start_at: datetime | None = None
    end_at: datetime | None = None
    fixed_code: str | None = None
    code_length: int | None = None
    last_fired_at: datetime | None = None
    next_fire_at: datetime | None = None


@dataclass
class HistoryEntry:
    """Single rotation attempt (maps to the ``rotation_history`` table)."""
    quiz_id: int
    triggered_by: TriggeredBy
    fired_at: datetime
    code_set: str
    outcome: RotationOutcome
    attempts: int
    id: int = 0
    schedule_id: int | None = None
    canvas_status: int | None = None
    error_message: str | None = None


@dataclass
class Config:
    """Single-row runtime config (maps to the ``config`` table)."""
    updated_by: int
    updated_at: datetime
    id: int = 1             # always row 1
    notify_channel_id: int | None = None

@dataclass
class AllowedRole:
    """A Discord role permitted to use /quizbot commands (maps to ``allowed_roles`` table)."""
    role_id: int      # Discord role snowflake ID
    added_by: int     # Discord user ID who granted it
    added_at: datetime
    id: int = 0


@dataclass
class RotationResult:
    """Result of a single rotation attempt."""
    outcome: RotationOutcome
    code_set: str
    attempts: int
    canvas_status: int | None = None
    error_message: str | None = None
