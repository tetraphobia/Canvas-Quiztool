from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from croniter import croniter

from canvas_code_bot.core.interfaces import (
    ConfigRepo,
    NotifierPort,
    QuizRepo,
    ScheduleRepo,
)
from canvas_code_bot.core.models import (
    CodePolicy,
    DEFAULT_CODE_LENGTH,
    Quiz,
    Schedule,
    ScheduleKind,
    TriggeredBy,
)
from canvas_code_bot.core.services import RotationService

logger = logging.getLogger(__name__)


def _utc_now_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _to_aware_utc(dt: datetime) -> datetime:
    return dt.replace(tzinfo=timezone.utc)


def _last_expected_fire_utc(schedule: Schedule, now_utc: datetime) -> datetime | None:
    tz = ZoneInfo(schedule.timezone)
    now_aware = _to_aware_utc(now_utc)

    # Window end check
    if schedule.end_at and _to_aware_utc(schedule.end_at) < now_aware:
        return None

    # Convert now to local timezone for croniter
    now_local = now_aware.astimezone(tz)

    iter_ = croniter(schedule.cron, now_local)
    prev_local = iter_.get_prev(datetime)  # naive datetime in local tz

    # Attach timezone info and convert back to naive UTC
    prev_aware = prev_local.replace(tzinfo=tz)
    prev_utc = prev_aware.astimezone(timezone.utc).replace(tzinfo=None)

    # Window start check
    if schedule.start_at and prev_utc < schedule.start_at:
        return None

    return prev_utc


class Reconciler:
    """Catches up missed rotations on startup."""

    def __init__(
        self,
        schedule_repo: ScheduleRepo,
        quiz_repo: QuizRepo,
        rotation_service: RotationService,
        notifier: NotifierPort,
        config_repo: ConfigRepo,
        admin_discord_id: int,
        oneshot_late_guard_hours: int = 24,
    ) -> None:
        self._schedules = schedule_repo
        self._quizzes = quiz_repo
        self._rotation = rotation_service
        self._notifier = notifier
        self._config_repo = config_repo
        self._admin_id = admin_discord_id
        self._late_guard = timedelta(hours=oneshot_late_guard_hours)

    async def run(self, now: datetime | None = None) -> None:
        """Check all active schedules and catch up any missed rotations."""
        now = now or _utc_now_naive()
        active = self._schedules.list_active()
        logger.info("Reconciler: checking %d active schedule(s)", len(active))

        # Group schedules so all quizzes in a group share one code on catch-up.
        groups: dict[str, list[Schedule]] = {}
        for sched in active:
            key = sched.group_id or str(sched.id)
            groups.setdefault(key, []).append(sched)

        for group_scheds in groups.values():
            await self._process_group(group_scheds, now)

    async def _process_group(
        self, schedules: list[Schedule], now: datetime
    ) -> None:
        to_fire: list[tuple[Quiz, Schedule]] = []

        for schedule in schedules:
            quiz = self._quizzes.get(schedule.quiz_id)
            if quiz is None:
                logger.warning(
                    "Reconciler: quiz %d not found, skipping", schedule.quiz_id
                )
                continue

            if schedule.kind == ScheduleKind.ONESHOT:
                should = await self._should_fire_oneshot(schedule, quiz, now)
            else:
                should = self._should_fire_recurring(schedule, quiz, now)

            if should:
                to_fire.append((quiz, schedule))

        if not to_fire:
            return

        # Use the first schedule's policy; all in the group share the same
        # cron/run_at/random/fixed_code settings.
        rep = to_fire[0][1]
        policy = CodePolicy(length=rep.code_length or DEFAULT_CODE_LENGTH)
        fixed = rep.fixed_code if not rep.random else None
        pairs = [(quiz, sched.id) for quiz, sched in to_fire]
        await self._rotation.rotate_group(
            pairs, TriggeredBy.RECONCILER, policy=policy, fixed_code=fixed
        )

    async def _should_fire_oneshot(
        self, schedule: Schedule, quiz: Quiz, now: datetime
    ) -> bool:
        if schedule.last_fired_at is not None:
            return False

        run_at = schedule.run_at
        if run_at is None or run_at > now:
            return False

        late_by = now - run_at
        if late_by > self._late_guard:
            logger.warning(
                "Reconciler: one-shot schedule %d for quiz %d is %s late "
                "(> %s guard) — alerting admin instead of firing",
                schedule.id,
                quiz.id,
                late_by,
                self._late_guard,
            )
            await self._alert_late_oneshot(schedule, quiz, run_at, late_by)
            return False

        logger.info(
            "Reconciler: firing missed one-shot schedule %d for quiz %d",
            schedule.id,
            quiz.id,
        )
        return True

    def _should_fire_recurring(
        self, schedule: Schedule, quiz: Quiz, now: datetime
    ) -> bool:
        expected = _last_expected_fire_utc(schedule, now)
        if expected is None:
            return False

        last = schedule.last_fired_at
        if last is not None and expected <= last:
            return False

        logger.info(
            "Reconciler: firing missed recurring schedule %d for quiz %d "
            "(expected fire at %s, last fired at %s)",
            schedule.id,
            quiz.id,
            expected,
            last,
        )
        return True

    async def _alert_late_oneshot(
        self,
        schedule: Schedule,
        quiz: Quiz,
        run_at: datetime,
        late_by: timedelta,
    ) -> None:
        channel_id = (
            quiz.notify_channel_id or self._config_repo.get().notify_channel_id
        )
        if channel_id is None:
            logger.error(
                "Reconciler: no channel configured — cannot alert admin about "
                "late one-shot schedule %d for quiz %d",
                schedule.id,
                quiz.id,
            )
            return

        hours = late_by.total_seconds() / 3600
        message = (
            f"One-shot schedule for quiz **{quiz.quiz_name}** was due at "
            f"`{run_at}` UTC but was missed by {hours:.1f}h (> guard threshold). "
            f"Use `/quizbot code update-now` to rotate manually."
        )
        await self._notifier.notify_error(
            channel_id, quiz, message, self._admin_id
        )
