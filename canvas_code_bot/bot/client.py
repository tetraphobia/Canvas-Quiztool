from __future__ import annotations

import logging
from dataclasses import dataclass

import discord
from discord.ext import commands

from canvas_code_bot.core.interfaces import (
    AllowedRoleRepo,
    CanvasPort,
    ConfigRepo,
    HistoryRepo,
    QuizRepo,
    ScheduleRepo,
)
from canvas_code_bot.core.services import ConfigService, RegistryService, RotationService
from canvas_code_bot.scheduling.schedule_service import ScheduleService
from canvas_code_bot.scheduling.scheduler import RotationScheduler

logger = logging.getLogger(__name__)


@dataclass
class Services:
    """All injected dependencies in one place, passed to command groups."""

    registry: RegistryService
    rotation: RotationService
    config_svc: ConfigService
    schedule_svc: ScheduleService
    quiz_repo: QuizRepo
    schedule_repo: ScheduleRepo
    history_repo: HistoryRepo
    config_repo: ConfigRepo
    scheduler: RotationScheduler
    canvas: CanvasPort
    allowed_role_repo: AllowedRoleRepo
    admin_discord_id: int


class QuizbotClient(commands.Bot):
    """discord.py Bot subclass."""

    def __init__(self, **kwargs) -> None:
        intents = discord.Intents.default()
        super().__init__(command_prefix="!", intents=intents, **kwargs)
        self.services: Services | None = None

    async def setup_hook(self) -> None:
        if self.services is None:
            raise RuntimeError(
                "QuizbotClient.services must be assigned before bot.start()."
            )
        from canvas_code_bot.bot.commands.quiz_commands import QbGroup

        group = QbGroup(self.services)
        self.tree.add_command(group)
        await self.tree.sync()
        logger.info("Slash commands synced globally.")

    async def on_ready(self) -> None:
        logger.info("Bot ready: %s (id=%d)", self.user, self.user.id)
