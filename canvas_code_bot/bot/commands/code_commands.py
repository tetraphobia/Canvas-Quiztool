"""
/quizbot code show    <quizids>
/quizbot code update-now <quizids> [random] [code]
"""
from __future__ import annotations

import logging

import discord
from discord import app_commands

from canvas_code_bot.core.models import CodePolicy, TriggeredBy

logger = logging.getLogger(__name__)

_DEFAULT_LENGTH = 6


class CodeGroup(app_commands.Group, name="code", description="Access-code operations."):
    def __init__(self, services) -> None:
        super().__init__()
        self._svc = services

    @app_commands.command(name="show", description="Re-post the current access code(s) to the relay channel.")
    @app_commands.describe(quizids="Comma-separated quiz IDs.")
    async def show(self, interaction: discord.Interaction, quizids: str) -> None:
        await interaction.response.defer(ephemeral=True)

        ids = _parse_ids(quizids)
        if not ids:
            await interaction.followup.send("No valid quiz IDs provided.", ephemeral=True)
            return

        results = []
        for qid in ids:
            quiz = self._svc.quiz_repo.get(qid)
            if quiz is None:
                results.append(f"Quiz {qid}: not found.")
                continue

            if quiz.current_code is None:
                results.append(f"**{quiz.quiz_name}**: no code has been set yet.")
                continue

            channel_id = quiz.notify_channel_id or self._svc.config_repo.get().notify_channel_id
            if channel_id is None:
                results.append(f"**{quiz.quiz_name}**: no relay channel configured.")
                continue

            channel = interaction.client.get_channel(channel_id)
            if channel is None:
                results.append(f"**{quiz.quiz_name}**: relay channel not accessible.")
                continue

            embed = discord.Embed(title="Current Access Code", color=discord.Color.blurple())
            embed.add_field(name="Quiz", value=quiz.quiz_name, inline=False)
            embed.add_field(name="Course", value=quiz.course_name, inline=True)
            embed.add_field(name="Code", value=f"`{quiz.current_code}`", inline=True)
            await channel.send(embed=embed)
            results.append(f"**{quiz.quiz_name}**: posted to {channel.mention}.")

        await interaction.followup.send("\n".join(results), ephemeral=True)

    @app_commands.command(
        name="update-now",
        description="Rotate the access code immediately and post it to the relay channel.",
    )
    @app_commands.describe(
        quizids="Comma-separated quiz IDs.",
        random="Generate a random code (default: true).",
        code="Fixed code to use (only when random=false).",
    )
    async def update_now(
        self,
        interaction: discord.Interaction,
        quizids: str,
        random: bool = True,
        code: str | None = None,
    ) -> None:
        error = _validate_code_args(random, code)
        if error:
            await interaction.response.send_message(error, ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        ids = _parse_ids(quizids)
        if not ids:
            await interaction.followup.send("No valid quiz IDs provided.", ephemeral=True)
            return

        results = []
        for qid in ids:
            quiz = self._svc.quiz_repo.get(qid)
            if quiz is None:
                results.append(f"Quiz {qid}: not found.")
                continue
            try:
                policy = CodePolicy(length=_DEFAULT_LENGTH) if random else None
                result = await self._svc.rotation.rotate(
                    quiz=quiz,
                    triggered_by=TriggeredBy.MANUAL,
                    policy=policy,
                    fixed_code=None if random else code,
                )
                if result.outcome.value == "success":
                    results.append(f"**{quiz.quiz_name}**: rotated (code posted to relay channel).")
                else:
                    results.append(
                        f"**{quiz.quiz_name}**: rotation failed — {result.error_message}."
                    )
            except Exception as exc:
                logger.exception("update-now failed for quiz %d", qid)
                results.append(f"**{quiz.quiz_name}**: unexpected error — {exc}.")

        await interaction.followup.send("\n".join(results), ephemeral=True)


def _parse_ids(raw: str) -> list[int]:
    ids = []
    for part in raw.split(","):
        part = part.strip()
        if part.isdigit():
            ids.append(int(part))
    return ids


def _validate_code_args(random: bool, code: str | None) -> str | None:
    if not random and not code:
        return "Provide a `code` value when `random=false`."
    if random and code:
        return "Cannot specify both `random=true` and a fixed `code`."
    return None
