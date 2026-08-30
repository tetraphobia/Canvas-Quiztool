from __future__ import annotations

import logging
from typing import Callable, Coroutine

from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from canvas_code_bot.core.models import Schedule
from canvas_code_bot.scheduling.triggers import build_trigger

logger = logging.getLogger(__name__)

# Registered by the composition root; must be set before start().
_rotation_handler: Callable[[str], Coroutine] | None = None


async def _job_func(group_id: str) -> None:
    if _rotation_handler is None:
        logger.error(
            "Rotation handler not registered; skipping job (group_id=%s)",
            group_id,
        )
        return
    await _rotation_handler(group_id)


def register_rotation_handler(
    handler: Callable[[str], Coroutine],
) -> None:
    """Registers the handler called when a scheduled rotation fires."""
    global _rotation_handler
    _rotation_handler = handler


def _group_job_id(group_id: str) -> str:
    return f"group_{group_id}"


class RotationScheduler:
    """AsyncIOScheduler wrapper for quiz rotation jobs."""

    def __init__(self, db_url: str) -> None:
        jobstores = {"default": SQLAlchemyJobStore(url=db_url)}
        self._scheduler = AsyncIOScheduler(
            jobstores=jobstores,
            job_defaults={"coalesce": True, "max_instances": 1},
        )

    def start(self) -> None:
        self._scheduler.start()
        logger.info("Rotation scheduler started")

    def shutdown(self, wait: bool = False) -> None:
        self._scheduler.shutdown(wait=wait)

    @property
    def running(self) -> bool:
        return self._scheduler.running

    def add_or_replace_job(self, schedule: Schedule) -> None:
        """Register or replace the APScheduler job for a schedule's group."""
        if not schedule.group_id:
            logger.error(
                "Cannot register job for schedule %d: group_id is not set",
                schedule.id,
            )
            return
        trigger = build_trigger(schedule)
        job_id = _group_job_id(schedule.group_id)
        self._scheduler.add_job(
            _job_func,
            trigger=trigger,
            args=[schedule.group_id],
            id=job_id,
            replace_existing=True,
            coalesce=True,
            max_instances=1,
        )
        logger.debug(
            "Scheduled job for group_id=%s (schedule_id=%d)",
            schedule.group_id,
            schedule.id,
        )

    def remove_job_for_group(self, group_id: str) -> None:
        job_id = _group_job_id(group_id)
        if self._scheduler.get_job(job_id):
            self._scheduler.remove_job(job_id)
            logger.debug("Removed job for group_id=%s", group_id)
