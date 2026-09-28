from __future__ import annotations

import logging

import discord
from discord import app_commands

from canvas_code_bot.bot.commands.command_utils import parse_ids

logger = logging.getLogger(__name__)


class AnnounceGroup(app_commands.Group, name="announce", description="Post Canvas announcements."):
    def __init__(self, services) -> None:
        super().__init__()
        self._svc = services

    @app_commands.command(
        name="all",
        description="Post an announcement to all tracked courses (or a subset).",
    )
    @app_commands.describe(
        title="Announcement title.",
        message="Announcement body (HTML is supported).",
        course_ids="Comma-separated course IDs to target (default: all tracked courses).",
    )
    async def announce_all(
        self,
        interaction: discord.Interaction,
        title: str,
        message: str,
        course_ids: str | None = None,
    ) -> None:
        await interaction.response.defer(ephemeral=True)

        courses = self._svc.course_repo.list_all()
        if not courses:
            await interaction.followup.send("No courses are tracked yet.", ephemeral=True)
            return

        if course_ids is not None:
            ids = set(parse_ids(course_ids))
            if not ids:
                await interaction.followup.send(
                    f"No valid course IDs in `{course_ids}`.", ephemeral=True
                )
                return
            courses = [c for c in courses if c.course_id in ids]
            if not courses:
                await interaction.followup.send(
                    "None of the specified course IDs are tracked.", ephemeral=True
                )
                return

        lines: list[str] = []
        for course in courses:
            try:
                topic_id = await self._svc.canvas.create_announcement(
                    course.course_id, title, message
                )
                lines.append(f"**{course.course_name}**: posted (topic id={topic_id}).")
            except Exception as exc:
                logger.exception("Failed to post announcement to course %d", course.course_id)
                lines.append(f"**{course.course_name}**: failed — {exc}.")

        await interaction.followup.send("\n".join(lines), ephemeral=True)
