from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import delete, or_, select
from sqlalchemy.orm import sessionmaker

from canvas_code_bot.core.models import (
    AllowedRole,
    Config,
    HistoryEntry,
    Quiz,
    QuizEngine,
    RotationOutcome,
    Schedule,
    ScheduleKind,
    ScheduleStatus,
    TriggeredBy,
)
from canvas_code_bot.data.entities import (
    AllowedRoleEntity,
    ConfigEntity,
    HistoryEntity,
    QuizEntity,
    ScheduleEntity,
)


def _strip_tz(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    return dt.replace(tzinfo=None)


def _quiz_to_entity(q: Quiz) -> QuizEntity:
    return QuizEntity(
        id=q.id or None,
        course_id=q.course_id,
        course_name=q.course_name,
        assignment_id=q.assignment_id,
        quiz_name=q.quiz_name,
        engine=q.engine.value,
        resource_id=q.resource_id,
        notify_channel_id=q.notify_channel_id,
        current_code=q.current_code,
        current_code_at=_strip_tz(q.current_code_at),
        added_by=q.added_by,
        added_at=_strip_tz(q.added_at),
    )


def _entity_to_quiz(e: QuizEntity) -> Quiz:
    return Quiz(
        id=e.id,
        course_id=e.course_id,
        course_name=e.course_name,
        assignment_id=e.assignment_id,
        quiz_name=e.quiz_name,
        engine=QuizEngine(e.engine),
        resource_id=e.resource_id,
        notify_channel_id=e.notify_channel_id,
        current_code=e.current_code,
        current_code_at=e.current_code_at,
        added_by=e.added_by,
        added_at=e.added_at,
    )


def _schedule_to_entity(s: Schedule) -> ScheduleEntity:
    return ScheduleEntity(
        id=s.id or None,
        quiz_id=s.quiz_id,
        kind=s.kind.value,
        group_id=s.group_id,
        cron=s.cron,
        run_at=_strip_tz(s.run_at),
        timezone=s.timezone,
        start_at=_strip_tz(s.start_at),
        end_at=_strip_tz(s.end_at),
        random=s.random,
        fixed_code=s.fixed_code,
        code_length=s.code_length,
        status=s.status.value,
        created_by=s.created_by,
        created_at=_strip_tz(s.created_at),
        last_fired_at=_strip_tz(s.last_fired_at),
        next_fire_at=_strip_tz(s.next_fire_at),
    )


def _entity_to_schedule(e: ScheduleEntity) -> Schedule:
    return Schedule(
        id=e.id,
        quiz_id=e.quiz_id,
        kind=ScheduleKind(e.kind),
        group_id=e.group_id,
        cron=e.cron,
        run_at=e.run_at,
        timezone=e.timezone,
        start_at=e.start_at,
        end_at=e.end_at,
        random=e.random,
        fixed_code=e.fixed_code,
        code_length=e.code_length,
        status=ScheduleStatus(e.status),
        created_by=e.created_by,
        created_at=e.created_at,
        last_fired_at=e.last_fired_at,
        next_fire_at=e.next_fire_at,
    )


def _history_to_entity(h: HistoryEntry) -> HistoryEntity:
    return HistoryEntity(
        id=h.id or None,
        quiz_id=h.quiz_id,
        schedule_id=h.schedule_id,
        triggered_by=h.triggered_by.value,
        fired_at=_strip_tz(h.fired_at),
        code_set=h.code_set,
        outcome=h.outcome.value,
        attempts=h.attempts,
        canvas_status=h.canvas_status,
        error_message=h.error_message,
    )


def _entity_to_history(e: HistoryEntity) -> HistoryEntry:
    return HistoryEntry(
        id=e.id,
        quiz_id=e.quiz_id,
        schedule_id=e.schedule_id,
        triggered_by=TriggeredBy(e.triggered_by),
        fired_at=e.fired_at,
        code_set=e.code_set,
        outcome=RotationOutcome(e.outcome),
        attempts=e.attempts,
        canvas_status=e.canvas_status,
        error_message=e.error_message,
    )


def _entity_to_config(e: ConfigEntity) -> Config:
    return Config(
        id=e.id,
        notify_channel_id=e.notify_channel_id,
        updated_by=e.updated_by,
        updated_at=e.updated_at,
    )


class SqlQuizRepo:
    def __init__(self, session_factory: sessionmaker) -> None:
        self._sf = session_factory

    def add(self, quiz: Quiz) -> Quiz:
        entity = _quiz_to_entity(quiz)
        with self._sf.begin() as session:
            session.add(entity)
        return _entity_to_quiz(entity)

    def get(self, quiz_id: int) -> Quiz | None:
        with self._sf() as session:
            e = session.get(QuizEntity, quiz_id)
            return _entity_to_quiz(e) if e else None

    def get_by_assignment(
        self, course_id: int, assignment_id: int
    ) -> Quiz | None:
        with self._sf() as session:
            e = session.scalar(
                select(QuizEntity).where(
                    QuizEntity.course_id == course_id,
                    QuizEntity.assignment_id == assignment_id,
                )
            )
            return _entity_to_quiz(e) if e else None

    def get_by_resource_id(
        self, course_id: int, resource_id: int
    ) -> Quiz | None:
        with self._sf() as session:
            e = session.scalar(
                select(QuizEntity).where(
                    QuizEntity.course_id == course_id,
                    QuizEntity.resource_id == resource_id,
                )
            )
            return _entity_to_quiz(e) if e else None

    def list_all(self) -> list[Quiz]:
        with self._sf() as session:
            rows = session.scalars(select(QuizEntity)).all()
            return [_entity_to_quiz(r) for r in rows]

    def update_current_code(
        self, quiz_id: int, code: str, at: datetime
    ) -> None:
        with self._sf.begin() as session:
            e = session.get(QuizEntity, quiz_id)
            if e:
                e.current_code = code
                e.current_code_at = _strip_tz(at)

    def update_notify_channel(
        self, quiz_id: int, channel_id: int | None
    ) -> None:
        with self._sf.begin() as session:
            e = session.get(QuizEntity, quiz_id)
            if e:
                e.notify_channel_id = channel_id

    def remove(self, quiz_id: int) -> None:
        with self._sf.begin() as session:
            e = session.get(QuizEntity, quiz_id)
            if e:
                session.delete(e)


class SqlScheduleRepo:
    def __init__(self, session_factory: sessionmaker) -> None:
        self._sf = session_factory

    def add(self, schedule: Schedule) -> Schedule:
        entity = _schedule_to_entity(schedule)
        with self._sf.begin() as session:
            session.add(entity)
        return _entity_to_schedule(entity)

    def get(self, schedule_id: int) -> Schedule | None:
        with self._sf() as session:
            e = session.get(ScheduleEntity, schedule_id)
            return _entity_to_schedule(e) if e else None

    def get_active(self, quiz_id: int) -> Schedule | None:
        with self._sf() as session:
            e = session.scalar(
                select(ScheduleEntity).where(
                    ScheduleEntity.quiz_id == quiz_id,
                    ScheduleEntity.status == ScheduleStatus.ACTIVE.value,
                )
            )
            return _entity_to_schedule(e) if e else None

    def list_active(self) -> list[Schedule]:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        with self._sf() as session:
            rows = session.scalars(
                select(ScheduleEntity).where(
                    ScheduleEntity.status == ScheduleStatus.ACTIVE.value,
                    or_(
                        ScheduleEntity.end_at == None,  # noqa: E711
                        ScheduleEntity.end_at >= now,
                    ),
                )
            ).all()
            return [_entity_to_schedule(r) for r in rows]

    def list_for_quiz(self, quiz_id: int) -> list[Schedule]:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        with self._sf() as session:
            rows = session.scalars(
                select(ScheduleEntity).where(
                    ScheduleEntity.quiz_id == quiz_id,
                    ScheduleEntity.status == ScheduleStatus.ACTIVE.value,
                    or_(
                        ScheduleEntity.end_at == None,  # noqa: E711
                        ScheduleEntity.end_at >= now,
                    ),
                )
            ).all()
            return [_entity_to_schedule(r) for r in rows]

    def list_by_group(self, group_id: str) -> list[Schedule]:
        with self._sf() as session:
            rows = session.scalars(
                select(ScheduleEntity).where(
                    ScheduleEntity.group_id == group_id,
                    ScheduleEntity.status == ScheduleStatus.ACTIVE.value,
                )
            ).all()
            return [_entity_to_schedule(r) for r in rows]

    def update_status(self, schedule_id: int, status: ScheduleStatus) -> None:
        with self._sf.begin() as session:
            e = session.get(ScheduleEntity, schedule_id)
            if e:
                e.status = status.value

    def update_last_fired(self, schedule_id: int, fired_at: datetime) -> None:
        with self._sf.begin() as session:
            e = session.get(ScheduleEntity, schedule_id)
            if e:
                e.last_fired_at = _strip_tz(fired_at)

    def replace_for_quiz(self, quiz_id: int, schedule: Schedule) -> Schedule:
        entity = _schedule_to_entity(schedule)
        with self._sf.begin() as session:
            session.execute(
                delete(ScheduleEntity).where(ScheduleEntity.quiz_id == quiz_id)
            )
            session.add(entity)
        return _entity_to_schedule(entity)

    def remove(self, schedule_id: int) -> None:
        with self._sf.begin() as session:
            e = session.get(ScheduleEntity, schedule_id)
            if e:
                session.delete(e)

    def list_all(self) -> list[Schedule]:
        with self._sf() as session:
            rows = session.scalars(select(ScheduleEntity)).all()
            return [_entity_to_schedule(r) for r in rows]

    def update_schedule(self, schedule: Schedule) -> Schedule:
        if not schedule.id:
            raise ValueError("update_schedule requires a schedule with a non-zero id")
        with self._sf.begin() as session:
            e = session.get(ScheduleEntity, schedule.id)
            if e is None:
                raise ValueError(f"Schedule {schedule.id} not found")
            e.kind = schedule.kind.value
            e.group_id = schedule.group_id
            e.cron = schedule.cron
            e.run_at = _strip_tz(schedule.run_at)
            e.timezone = schedule.timezone
            e.start_at = _strip_tz(schedule.start_at)
            e.end_at = _strip_tz(schedule.end_at)
            e.random = schedule.random
            e.fixed_code = schedule.fixed_code
            e.code_length = schedule.code_length
            e.status = schedule.status.value
        return _entity_to_schedule(e)

    def remove_by_quiz(self, quiz_id: int) -> None:
        with self._sf.begin() as session:
            session.execute(
                delete(ScheduleEntity).where(ScheduleEntity.quiz_id == quiz_id)
            )


class SqlHistoryRepo:
    def __init__(self, session_factory: sessionmaker) -> None:
        self._sf = session_factory

    def record(self, entry: HistoryEntry) -> HistoryEntry:
        entity = _history_to_entity(entry)
        with self._sf.begin() as session:
            session.add(entity)
        return _entity_to_history(entity)

    def last_for_quiz(self, quiz_id: int) -> HistoryEntry | None:
        with self._sf() as session:
            e = session.scalar(
                select(HistoryEntity)
                .where(HistoryEntity.quiz_id == quiz_id)
                .order_by(HistoryEntity.fired_at.desc())
                .limit(1)
            )
            return _entity_to_history(e) if e else None


class SqlConfigRepo:
    def __init__(self, session_factory: sessionmaker) -> None:
        self._sf = session_factory

    def get(self) -> Config:
        with self._sf() as session:
            e = session.get(ConfigEntity, 1)
            if e is None:
                # Return in-memory default; first set_channel call creates the row.
                return Config(updated_by=0, updated_at=datetime(2000, 1, 1))
            return _entity_to_config(e)

    def set_channel(
        self, channel_id: int, updated_by: int, at: datetime
    ) -> None:
        with self._sf.begin() as session:
            e = session.get(ConfigEntity, 1)
            if e is None:
                e = ConfigEntity(
                    id=1,
                    notify_channel_id=channel_id,
                    updated_by=updated_by,
                    updated_at=_strip_tz(at),
                )
                session.add(e)
            else:
                e.notify_channel_id = channel_id
                e.updated_by = updated_by
                e.updated_at = _strip_tz(at)


def _entity_to_allowed_role(e: AllowedRoleEntity) -> AllowedRole:
    return AllowedRole(
        id=e.id,
        role_id=e.role_id,
        added_by=e.added_by,
        added_at=e.added_at,
    )


class SqlAllowedRoleRepo:
    def __init__(self, session_factory: sessionmaker) -> None:
        self._sf = session_factory

    def add(self, role_id: int, added_by: int, at: datetime) -> AllowedRole:
        with self._sf.begin() as session:
            existing = session.scalar(
                select(AllowedRoleEntity).where(AllowedRoleEntity.role_id == role_id)
            )
            if existing is not None:
                return _entity_to_allowed_role(existing)
            entity = AllowedRoleEntity(
                role_id=role_id,
                added_by=added_by,
                added_at=_strip_tz(at),
            )
            session.add(entity)
            session.flush()  # populate entity.id; convert while session is still open
            return _entity_to_allowed_role(entity)

    def remove(self, role_id: int) -> None:
        with self._sf.begin() as session:
            session.execute(
                delete(AllowedRoleEntity).where(AllowedRoleEntity.role_id == role_id)
            )

    def list_all(self) -> list[AllowedRole]:
        with self._sf() as session:
            rows = session.scalars(select(AllowedRoleEntity)).all()
            return [_entity_to_allowed_role(r) for r in rows]

    def has_any(self, role_ids: set[int]) -> bool:
        if not role_ids:
            return False
        with self._sf() as session:
            result = session.scalar(
                select(AllowedRoleEntity.id)
                .where(AllowedRoleEntity.role_id.in_(role_ids))
                .limit(1)
            )
            return result is not None
