from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

import aiohttp

from canvas_code_bot.bot.client import QuizbotClient, Services
from canvas_code_bot.bot.presenters import DiscordNotifier
from canvas_code_bot.canvas.client import CanvasClient
from canvas_code_bot.canvas.quizzes import CanvasQuizGateway
from canvas_code_bot.codes.generator import RandomCodeGenerator
from canvas_code_bot.config import AppConfig
from canvas_code_bot.core.models import CodePolicy, ScheduleKind, ScheduleStatus, TriggeredBy
from canvas_code_bot.core.services import ConfigService, RegistryService, RotationService
from canvas_code_bot.data.db import make_engine, make_session_factory, migrate
from canvas_code_bot.data.entities import Base
from canvas_code_bot.data.repositories import (
    SqlAllowedRoleRepo,
    SqlConfigRepo,
    SqlHistoryRepo,
    SqlQuizRepo,
    SqlScheduleRepo,
)
from canvas_code_bot.logging_conf import setup_logging
from canvas_code_bot.scheduling.reconciler import Reconciler
from canvas_code_bot.scheduling.schedule_service import ScheduleService
from canvas_code_bot.scheduling.scheduler import RotationScheduler, register_rotation_handler

logger = logging.getLogger(__name__)


async def main() -> None:
    cfg = AppConfig.from_env()
    setup_logging(cfg.app_mode)
    logger.info("Starting Canvas Quizbot (mode=%s)", cfg.app_mode)

    engine = make_engine(cfg.db_url)
    Base.metadata.create_all(engine)
    migrate(engine)
    sf = make_session_factory(engine)

    quiz_repo = SqlQuizRepo(sf)
    schedule_repo = SqlScheduleRepo(sf)
    history_repo = SqlHistoryRepo(sf)
    config_repo = SqlConfigRepo(sf)
    allowed_role_repo = SqlAllowedRoleRepo(sf)

    async with aiohttp.ClientSession() as http_session:
        canvas_client = CanvasClient(
            base_url=cfg.canvas_base_url,
            token=cfg.canvas_token,
            session=http_session,
        )
        canvas = CanvasQuizGateway(canvas_client)

        code_gen = RandomCodeGenerator()

        bot = QuizbotClient()
        notifier = DiscordNotifier(bot)

        rotation_svc = RotationService(
            code_gen=code_gen,
            canvas=canvas,
            quiz_repo=quiz_repo,
            history_repo=history_repo,
            notifier=notifier,
            config_repo=config_repo,
            admin_discord_id=cfg.admin_discord_id,
        )
        registry_svc = RegistryService(quiz_repo=quiz_repo, canvas=canvas)
        config_svc = ConfigService(quiz_repo=quiz_repo, config_repo=config_repo)

        scheduler = RotationScheduler(cfg.db_url)
        schedule_svc = ScheduleService(schedule_repo=schedule_repo, scheduler=scheduler)

        async def _rotation_handler(group_id: str) -> None:
            schedules = schedule_repo.list_by_group(group_id)
            if not schedules:
                logger.warning(
                    "Scheduled job: no active schedules found for group %s", group_id
                )
                return

            pairs: list[tuple] = []
            for sched in schedules:
                quiz = quiz_repo.get(sched.quiz_id)
                if quiz is None:
                    logger.error(
                        "Scheduled job: quiz %d not found, skipping", sched.quiz_id
                    )
                    continue
                pairs.append((quiz, sched.id))

            if not pairs:
                return

            rep = schedules[0]
            policy = CodePolicy(length=rep.code_length or cfg.code_length)
            fixed = rep.fixed_code if not rep.random else None
            await rotation_svc.rotate_group(
                pairs=pairs,
                triggered_by=TriggeredBy.SCHEDULE,
                policy=policy,
                fixed_code=fixed,
            )

            now = datetime.now(timezone.utc).replace(tzinfo=None)
            for _, schedule_id in pairs:
                schedule_repo.update_last_fired(schedule_id, now)
                if rep.kind == ScheduleKind.ONESHOT:
                    schedule_repo.update_status(schedule_id, ScheduleStatus.COMPLETED)

        register_rotation_handler(_rotation_handler)

        bot.services = Services(
            registry=registry_svc,
            rotation=rotation_svc,
            config_svc=config_svc,
            schedule_svc=schedule_svc,
            quiz_repo=quiz_repo,
            schedule_repo=schedule_repo,
            history_repo=history_repo,
            config_repo=config_repo,
            scheduler=scheduler,
            canvas=canvas,
            allowed_role_repo=allowed_role_repo,
            admin_discord_id=cfg.admin_discord_id,
        )

        scheduler.start()

        # Re-register all active schedules so group-keyed APScheduler jobs are
        # up-to-date (the migration clears old quiz-keyed jobs).
        seen_groups: set[str] = set()
        for active_sched in schedule_repo.list_active():
            if active_sched.group_id and active_sched.group_id not in seen_groups:
                scheduler.add_or_replace_job(active_sched)
                seen_groups.add(active_sched.group_id)

        reconciler = Reconciler(
            schedule_repo=schedule_repo,
            quiz_repo=quiz_repo,
            rotation_service=rotation_svc,
            notifier=notifier,
            config_repo=config_repo,
            admin_discord_id=cfg.admin_discord_id,
            oneshot_late_guard_hours=cfg.oneshot_late_guard_hours,
        )
        await reconciler.run()
        logger.info("Startup reconciler complete.")

        try:
            async with bot:
                await bot.start(cfg.discord_token)
        finally:
            if scheduler.running:
                scheduler.shutdown(wait=False)
            logger.info("Shutdown complete.")


asyncio.run(main())
