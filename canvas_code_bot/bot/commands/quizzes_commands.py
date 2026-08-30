from __future__ import annotations

import logging

import discord
from discord import app_commands

from canvas_code_bot.canvas.url_parser import parse_quiz_url
from canvas_code_bot.core.exceptions import CanvasError

logger = logging.getLogger(__name__)


class QuizzesGroup(app_commands.Group, name="quizzes", description="Manage registered quizzes."):
    def __init__(self, services) -> None:
        super().__init__()
        self._svc = services

    @app_commands.command(name="help", description="Show usage for /qb quizzes commands.")
    async def help(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        embed = discord.Embed(
            title="/qb quizzes — Quiz Management",
            description="Register and manage Canvas quizzes tracked by the bot.",
            color=discord.Color.blurple(),
        )
        embed.add_field(
            name="`list [show_all]`",
            value=(
                "Show registered quizzes.\n"
                "Default: only quizzes with at least one active schedule.\n"
                "• `show_all:True` — include quizzes with no schedule."
            ),
            inline=False,
        )
        embed.add_field(
            name="`add url:<Canvas URL>`",
            value=(
                "Register a quiz by its full Canvas URL.\n"
                "Accepts both **assignments** and **quizzes** URLs.\n"
                "The bot auto-detects Classic vs New Quizzes engine at registration time."
            ),
            inline=False,
        )
        embed.add_field(
            name="`delete quiz:<URL or ID>`",
            value=(
                "Remove a quiz and **all** of its schedules.\n"
                "Accepts the Canvas URL or the short integer quiz ID "
                "(shown in `list`)."
            ),
            inline=False,
        )
        embed.add_field(
            name="Examples",
            value=(
                "`/qb quizzes add url:https://canvas.example.edu/courses/123/assignments/456`\n"
                "`/qb quizzes list show_all:True`\n"
                "`/qb quizzes delete quiz:3`"
            ),
            inline=False,
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="list", description="Show registered quizzes.")
    @app_commands.describe(
        show_all="Include quizzes that have no active schedule (default: false).",
    )
    async def list_quizzes(
        self, interaction: discord.Interaction, show_all: bool = False
    ) -> None:
        quizzes = self._svc.quiz_repo.list_all()
        if not quizzes:
            await interaction.response.send_message("No quizzes registered.", ephemeral=True)
            return

        embed = discord.Embed(title="Registered Quizzes", color=discord.Color.blurple())
        shown = 0
        for q in quizzes:
            active_scheds = self._svc.schedule_repo.list_for_quiz(q.id)
            has_schedule = bool(active_scheds)
            if not show_all and not has_schedule:
                continue
            status = f"{len(active_scheds)} schedule(s)" if has_schedule else "no schedule"
            embed.add_field(
                name=f"id={q.id} · {q.quiz_name}",
                value=f"Course: {q.course_name} · {status}",
                inline=False,
            )
            shown += 1

        if shown == 0:
            msg = "No scheduled quizzes." if not show_all else "No quizzes registered."
            if not show_all:
                msg += " Use `show_all: True` to see all registered quizzes."
            await interaction.response.send_message(msg, ephemeral=True)
            return

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="add", description="Register a quiz by its Canvas URL.")
    @app_commands.describe(url="The full Canvas quiz URL (assignments/… or quizzes/… URL).")
    async def add_quiz(self, interaction: discord.Interaction, url: str) -> None:
        try:
            parsed = parse_quiz_url(url)
        except ValueError as exc:
            await interaction.response.send_message(
                f"Invalid URL: {exc}", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)
        try:
            if parsed.assignment_id is not None:
                quiz = await self._svc.registry.add_quiz(
                    course_id=parsed.course_id,
                    assignment_id=parsed.assignment_id,
                    added_by=interaction.user.id,
                )
            else:
                quiz = await self._svc.registry.add_quiz_by_quiz_id(
                    course_id=parsed.course_id,
                    quiz_id=parsed.quiz_id,
                    added_by=interaction.user.id,
                )
            await interaction.followup.send(
                f"Registered **{quiz.quiz_name}** (id={quiz.id}).", ephemeral=True
            )
        except ValueError as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
        except CanvasError as exc:
            await interaction.followup.send(f"Canvas error: {exc}", ephemeral=True)

    @app_commands.command(name="delete", description="Remove a quiz by its URL or short ID.")
    @app_commands.describe(quiz="The Canvas URL or the short integer quiz ID.")
    async def delete_quiz(self, interaction: discord.Interaction, quiz: str) -> None:
        quiz_id = _resolve_quiz_id(quiz, self._svc)
        if quiz_id is None:
            await interaction.response.send_message(
                "Quiz not found. Provide the URL or a valid quiz ID.", ephemeral=True
            )
            return

        quiz_obj = self._svc.quiz_repo.get(quiz_id)
        name = quiz_obj.quiz_name if quiz_obj else f"id={quiz_id}"

        self._svc.schedule_svc.remove_jobs_for_quiz(quiz_id)
        self._svc.registry.remove_quiz(quiz_id)

        await interaction.response.send_message(
            f"Removed **{name}** and all its schedules.", ephemeral=True
        )


def _resolve_quiz_id(raw: str, services) -> int | None:
    """Return quiz_id given a raw string that is either an int ID or a URL."""
    raw = raw.strip()
    if raw.isdigit():
        return int(raw)
    try:
        parsed = parse_quiz_url(raw)
        if parsed.assignment_id is not None:
            q = services.quiz_repo.get_by_assignment(parsed.course_id, parsed.assignment_id)
        else:
            q = services.quiz_repo.get_by_resource_id(parsed.course_id, parsed.quiz_id)
        return q.id if q else None
    except ValueError:
        return None
