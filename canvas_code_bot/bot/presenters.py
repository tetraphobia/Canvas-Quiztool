from __future__ import annotations

import logging

import discord

from canvas_code_bot.core.models import Quiz

logger = logging.getLogger(__name__)


class DiscordNotifier:
    """Implements NotifierPort using discord.py embeds."""

    def __init__(self, bot: discord.Client) -> None:
        self._bot = bot

    async def notify_success(
        self, channel_id: int, quiz: Quiz, code: str
    ) -> None:
        channel = self._bot.get_channel(channel_id)
        if channel is None:
            logger.warning(
                "notify_success: channel %d not found (quiz %d)", channel_id, quiz.id
            )
            return
        embed = discord.Embed(
            title="Access Code Updated",
            color=discord.Color.green(),
        )
        embed.add_field(name="Quiz", value=quiz.quiz_name, inline=False)
        embed.add_field(name="Course", value=quiz.course_name, inline=True)
        embed.add_field(name="Code", value=f"`{code}`", inline=True)
        await channel.send(embed=embed)

    async def notify_group_success(
        self, channel_id: int, quizzes: list[Quiz], code: str
    ) -> None:
        channel = self._bot.get_channel(channel_id)
        if channel is None:
            logger.warning(
                "notify_group_success: channel %d not found", channel_id
            )
            return
        embed = discord.Embed(
            title="Access Code Updated",
            color=discord.Color.green(),
        )
        quiz_lines = "\n".join(
            f"({q.course_id}) {q.quiz_name}" for q in quizzes
        )
        embed.add_field(name="Quizzes", value=quiz_lines, inline=False)
        embed.add_field(name="Code", value=f"`{code}`", inline=True)
        await channel.send(embed=embed)

    async def notify_error(
        self, channel_id: int, quiz: Quiz, error: str, admin_id: int
    ) -> None:
        channel = self._bot.get_channel(channel_id)
        if channel is None:
            logger.warning(
                "notify_error: channel %d not found (quiz %d)", channel_id, quiz.id
            )
            return
        embed = discord.Embed(
            title="Rotation Failed",
            description=error,
            color=discord.Color.red(),
        )
        embed.add_field(name="Quiz", value=quiz.quiz_name, inline=False)
        await channel.send(content=f"<@{admin_id}>", embed=embed)
