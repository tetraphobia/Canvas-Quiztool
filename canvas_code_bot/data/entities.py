from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from canvas_code_bot.data.db import Base


class QuizEntity(Base):
    __tablename__ = "quizzes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    course_id: Mapped[int] = mapped_column(Integer, nullable=False)
    course_name: Mapped[str] = mapped_column(Text, nullable=False)
    assignment_id: Mapped[int] = mapped_column(Integer, nullable=False)
    quiz_name: Mapped[str] = mapped_column(Text, nullable=False)
    engine: Mapped[str] = mapped_column(Text, nullable=False, default="new")  # QuizEngine.value
    resource_id: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    notify_channel_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    current_code: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    current_code_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    added_by: Mapped[int] = mapped_column(Integer, nullable=False)
    added_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    schedules: Mapped[list["ScheduleEntity"]] = relationship(
        back_populates="quiz", cascade="all, delete-orphan", passive_deletes=True
    )
    history: Mapped[list["HistoryEntity"]] = relationship(
        back_populates="quiz", cascade="all, delete-orphan", passive_deletes=True
    )


class ScheduleEntity(Base):
    __tablename__ = "schedules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    quiz_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("quizzes.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(Text, nullable=False)        # ScheduleKind.value
    group_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    cron: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    run_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    timezone: Mapped[str] = mapped_column(Text, nullable=False)
    start_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    end_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    random: Mapped[bool] = mapped_column(Boolean, nullable=False)
    fixed_code: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    code_length: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False)      # ScheduleStatus.value
    created_by: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    last_fired_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    next_fire_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    quiz: Mapped["QuizEntity"] = relationship(back_populates="schedules")
    history: Mapped[list["HistoryEntity"]] = relationship(
        back_populates="schedule", passive_deletes=True
    )


class HistoryEntity(Base):
    __tablename__ = "rotation_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    quiz_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("quizzes.id", ondelete="CASCADE"), nullable=False
    )
    schedule_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("schedules.id", ondelete="SET NULL"), nullable=True
    )
    triggered_by: Mapped[str] = mapped_column(Text, nullable=False)   # TriggeredBy.value
    fired_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    code_set: Mapped[str] = mapped_column(Text, nullable=False)
    outcome: Mapped[str] = mapped_column(Text, nullable=False)         # RotationOutcome.value
    attempts: Mapped[int] = mapped_column(Integer, nullable=False)
    canvas_status: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    quiz: Mapped["QuizEntity"] = relationship(back_populates="history")
    schedule: Mapped[Optional["ScheduleEntity"]] = relationship(back_populates="history")


class ConfigEntity(Base):
    __tablename__ = "config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    notify_channel_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    updated_by: Mapped[int] = mapped_column(Integer, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class AllowedRoleEntity(Base):
    __tablename__ = "allowed_roles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    role_id: Mapped[int] = mapped_column(Integer, nullable=False, unique=True)
    added_by: Mapped[int] = mapped_column(Integer, nullable=False)
    added_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
