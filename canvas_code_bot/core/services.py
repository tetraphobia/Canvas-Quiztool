from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from canvas_code_bot.core.exceptions import CanvasAuthError, CanvasNotFoundError
from canvas_code_bot.core.interfaces import (
    CanvasPort,
    CodeGen,
    ConfigRepo,
    HistoryRepo,
    NotifierPort,
    QuizRepo,
)
from canvas_code_bot.core.models import (
    CodePolicy,
    Config,
    HistoryEntry,
    Quiz,
    RotationOutcome,
    RotationResult,
    TriggeredBy,
)

logger = logging.getLogger(__name__)

# Errors that must not be retried (token issues, deleted quiz)
_FATAL = (CanvasAuthError, CanvasNotFoundError)


class RotationService:
    """Orchestrates access code rotation: generates, sets, verifies, persists, and notifies."""

    def __init__(
        self,
        code_gen: CodeGen,
        canvas: CanvasPort,
        quiz_repo: QuizRepo,
        history_repo: HistoryRepo,
        notifier: NotifierPort,
        config_repo: ConfigRepo,
        admin_discord_id: int,
        max_attempts: int = 3,
        backoff_base: float = 1.0,
    ) -> None:
        self._code_gen = code_gen
        self._canvas = canvas
        self._quiz_repo = quiz_repo
        self._history_repo = history_repo
        self._notifier = notifier
        self._config_repo = config_repo
        self._admin_id = admin_discord_id
        self._max_attempts = max_attempts
        self._backoff_base = backoff_base

    async def rotate(
        self,
        quiz: Quiz,
        triggered_by: TriggeredBy,
        schedule_id: int | None = None,
        policy: CodePolicy | None = None,
        fixed_code: str | None = None,
        notify: bool = True,
    ) -> RotationResult:
        """Set a new access code for quiz."""
        code = (
            fixed_code
            if fixed_code is not None
            else self._code_gen.generate(policy or CodePolicy())
        )

        result = await self._attempt(quiz, code)

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        self._history_repo.record(
            HistoryEntry(
                quiz_id=quiz.id,
                schedule_id=schedule_id,
                triggered_by=triggered_by,
                fired_at=now,
                code_set=code,
                outcome=result.outcome,
                attempts=result.attempts,
                canvas_status=result.canvas_status,
                error_message=result.error_message,
            )
        )

        if result.outcome == RotationOutcome.SUCCESS:
            self._quiz_repo.update_current_code(quiz.id, code, now)

        if notify:
            channel_id = self._resolve_channel(quiz)
            if result.outcome == RotationOutcome.SUCCESS:
                if channel_id is not None:
                    await self._notifier.notify_success(channel_id, quiz, code)
            else:
                logger.error(
                    "Rotation failed for quiz %d after %d attempt(s): %s",
                    quiz.id,
                    result.attempts,
                    result.error_message,
                )
                if channel_id is not None:
                    await self._notifier.notify_error(
                        channel_id,
                        quiz,
                        result.error_message or "Unknown error",
                        self._admin_id,
                    )
        else:
            if result.outcome != RotationOutcome.SUCCESS:
                logger.error(
                    "Rotation failed for quiz %d after %d attempt(s): %s",
                    quiz.id,
                    result.attempts,
                    result.error_message,
                )

        return result

    # ── internals ─────────────────────────────────────────────────────────────

    async def _attempt(self, quiz: Quiz, code: str) -> RotationResult:
        last_exc: Exception | None = None
        last_status: int | None = None

        for attempt in range(self._max_attempts):
            if attempt > 0:
                await asyncio.sleep(self._backoff_base * attempt)

            try:
                http_status = await self._canvas.set_access_code(quiz, code)
                verified = await self._canvas.verify_access_code(quiz, code)
                if verified:
                    return RotationResult(
                        outcome=RotationOutcome.SUCCESS,
                        code_set=code,
                        attempts=attempt + 1,
                        canvas_status=http_status,
                    )
                last_exc = Exception(
                    "Verify-after-write failed: Canvas returned a different code"
                )
                last_status = http_status

            except _FATAL as exc:
                return RotationResult(
                    outcome=RotationOutcome.FAILED,
                    code_set=code,
                    attempts=attempt + 1,
                    canvas_status=exc.http_status,
                    error_message=str(exc),
                )
            except Exception as exc:
                last_exc = exc
                last_status = getattr(exc, "http_status", None)

        return RotationResult(
            outcome=RotationOutcome.FAILED,
            code_set=code,
            attempts=self._max_attempts,
            canvas_status=last_status,
            error_message=str(last_exc) if last_exc else "Max attempts exceeded",
        )

    async def rotate_group(
        self,
        pairs: list[tuple[Quiz, int | None]],
        triggered_by: TriggeredBy,
        policy: CodePolicy | None = None,
        fixed_code: str | None = None,
    ) -> list[tuple[Quiz, RotationResult]]:
        """Rotate all quizzes in pairs with a single shared code. Returns per-quiz results in the same order as pairs."""
        if not pairs:
            return []
        code = (
            fixed_code
            if fixed_code is not None
            else self._code_gen.generate(policy or CodePolicy())
        )

        results: list[tuple[Quiz, RotationResult]] = []
        for quiz, schedule_id in pairs:
            result = await self.rotate(
                quiz=quiz,
                triggered_by=triggered_by,
                schedule_id=schedule_id,
                fixed_code=code,
                notify=False,
            )
            results.append((quiz, result))

        # Group by channel so all quizzes going to the same channel
        # appear in a single combined embed.
        ok_by_ch: dict[int, list[Quiz]] = {}
        err_by_ch: dict[int, list[tuple[Quiz, str]]] = {}
        for quiz, result in results:
            ch = self._resolve_channel(quiz)
            if ch is None:
                continue
            if result.outcome == RotationOutcome.SUCCESS:
                ok_by_ch.setdefault(ch, []).append(quiz)
            else:
                err_by_ch.setdefault(ch, []).append(
                    (quiz, result.error_message or "Unknown error")
                )

        for ch, quizzes in ok_by_ch.items():
            await self._notifier.notify_group_success(ch, quizzes, code)
        for ch, quiz_errors in err_by_ch.items():
            for quiz, error in quiz_errors:
                await self._notifier.notify_error(ch, quiz, error, self._admin_id)

        return results

    def _resolve_channel(self, quiz: Quiz) -> int | None:
        if quiz.notify_channel_id is not None:
            return quiz.notify_channel_id
        return self._config_repo.get().notify_channel_id


class RegistryService:
    """Manages quiz registration."""

    def __init__(self, quiz_repo: QuizRepo, canvas: CanvasPort) -> None:
        self._quiz_repo = quiz_repo
        self._canvas = canvas

    async def add_quiz(
        self, course_id: int, assignment_id: int, added_by: int
    ) -> Quiz:
        """Register a new quiz.

        Raises ValueError if already registered, CanvasError on Canvas API failure.
        """
        existing = self._quiz_repo.get_by_assignment(course_id, assignment_id)
        if existing is not None:
            raise ValueError(
                f"Quiz (course={course_id}, assignment={assignment_id}) "
                f"is already registered as id={existing.id}."
            )

        info = await self._canvas.get_quiz(course_id, assignment_id)

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        quiz = Quiz(
            course_id=course_id,
            assignment_id=assignment_id,
            course_name=f"Course {course_id}",
            quiz_name=info.title,
            engine=info.engine,
            resource_id=info.resource_id,
            added_by=added_by,
            added_at=now,
        )
        return self._quiz_repo.add(quiz)

    async def add_quiz_by_quiz_id(
        self, course_id: int, quiz_id: int, added_by: int
    ) -> Quiz:
        """Register a Classic quiz by quiz_id.

        Raises ValueError if already registered, CanvasError on Canvas API failure.
        """
        info = await self._canvas.get_classic_quiz_by_quiz_id(course_id, quiz_id)

        existing = self._quiz_repo.get_by_assignment(course_id, info.assignment_id)
        if existing is not None:
            raise ValueError(
                f"Quiz (course={course_id}, assignment={info.assignment_id}) "
                f"is already registered as id={existing.id}."
            )

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        quiz = Quiz(
            course_id=course_id,
            assignment_id=info.assignment_id,
            course_name=f"Course {course_id}",
            quiz_name=info.title,
            engine=info.engine,
            resource_id=info.resource_id,
            added_by=added_by,
            added_at=now,
        )
        return self._quiz_repo.add(quiz)

    def remove_quiz(self, quiz_id: int) -> None:
        """Remove a quiz and all its schedules."""
        self._quiz_repo.remove(quiz_id)


class ConfigService:
    """Manages global and per-quiz relay channel configuration."""

    def __init__(self, quiz_repo: QuizRepo, config_repo: ConfigRepo) -> None:
        self._quiz_repo = quiz_repo
        self._config_repo = config_repo

    def set_global_channel(self, channel_id: int, updated_by: int) -> None:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        self._config_repo.set_channel(channel_id, updated_by, now)

    def set_quiz_channel(
        self, quiz_id: int, channel_id: int | None, updated_by: int
    ) -> None:
        self._quiz_repo.update_notify_channel(quiz_id, channel_id)

    def get(self) -> Config:
        return self._config_repo.get()
