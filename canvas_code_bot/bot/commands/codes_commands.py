from __future__ import annotations

import logging

import discord
from discord import app_commands

from canvas_code_bot.bot.commands.command_utils import parse_ids
from canvas_code_bot.core.models import CodePolicy, TriggeredBy

logger = logging.getLogger(__name__)

_DEFAULT_LENGTH = 6


class CodesGroup(app_commands.Group, name="codes", description="Access-code operations."):
    def __init__(self, services) -> None:
        super().__init__()
        self._svc = services

    @app_commands.command(name="help", description="Show usage for /qb codes commands.")
    async def help(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        embed = discord.Embed(
            title="/qb codes — Access Code Operations",
            description=(
                "View current access codes or trigger an immediate rotation "
                "outside of any scheduled window."
            ),
            color=discord.Color.blurple(),
        )
        embed.add_field(
            name="`list [show_all]`",
            value=(
                "Show current access codes for all registered quizzes.\n"
                "Default: only quizzes that have a code set.\n"
                "• `show_all:True` — include quizzes with no code yet."
            ),
            inline=False,
        )
        embed.add_field(
            name="`update quizids:<ids> [options]`",
            value=(
                "Immediately rotate the access code for one or more quizzes "
                "(comma-separated IDs). The new code is posted to the relay channel.\n"
                "**Code** — provide exactly one of:\n"
                "• `random:True` *(default)* — generate a random 6-character code\n"
                "• `random:False code:<value>` — set a specific fixed code"
            ),
            inline=False,
        )
        embed.add_field(
            name="Examples",
            value=(
                "Rotate two quizzes with a random code:\n"
                "`/qb codes update quizids:1,2`\n\n"
                "Set a specific code on quiz 3:\n"
                "`/qb codes update quizids:3 random:False code:EXAM99`\n\n"
                "See all quizzes, even those without a code:\n"
                "`/qb codes list show_all:True`"
            ),
            inline=False,
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="list", description="Show current access codes for registered quizzes.")
    @app_commands.describe(
        show_all="Include quizzes that have no code set yet (default: false).",
    )
    async def list_codes(
        self, interaction: discord.Interaction, show_all: bool = False
    ) -> None:
        quizzes = self._svc.quiz_repo.list_all()
        if not quizzes:
            await interaction.response.send_message("No quizzes registered.", ephemeral=True)
            return

        embed = discord.Embed(title="Current Access Codes", color=discord.Color.blurple())
        shown = 0
        for q in quizzes:
            if not show_all and q.current_code is None:
                continue
            code_val = f"`{q.current_code}`" if q.current_code else "_not set_"
            embed.add_field(
                name=f"{q.quiz_name} (id={q.id})",
                value=code_val,
                inline=True,
            )
            shown += 1

        if shown == 0:
            msg = "No codes have been set yet."
            if not show_all:
                msg += " Use `show_all: True` to see all registered quizzes."
            await interaction.response.send_message(msg, ephemeral=True)
            return

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(
        name="update",
        description="Rotate the access code immediately for one or more quizzes.",
    )
    @app_commands.describe(
        quizids="Comma-separated quiz IDs.",
        random="Generate a random code (default: true).",
        code="Fixed code to use (only when random=false).",
    )
    async def update_code(
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

        ids = parse_ids(quizids)
        if not ids:
            await interaction.followup.send("No valid quiz IDs provided.", ephemeral=True)
            return

        lines: list[str] = []
        pairs = []
        for qid in ids:
            quiz = self._svc.quiz_repo.get(qid)
            if quiz is None:
                lines.append(f"Quiz {qid}: not found.")
            else:
                pairs.append((quiz, None))

        if not pairs:
            await interaction.followup.send("\n".join(lines) or "No valid quizzes.", ephemeral=True)
            return

        try:
            policy = CodePolicy(length=_DEFAULT_LENGTH) if random else None
            results = await self._svc.rotation.rotate_group(
                pairs=pairs,
                triggered_by=TriggeredBy.MANUAL,
                policy=policy,
                fixed_code=None if random else code,
            )
        except Exception as exc:
            logger.exception("codes update failed")
            await interaction.followup.send(f"Unexpected error: {exc}", ephemeral=True)
            return

        for quiz, result in results:
            if result.outcome.value == "success":
                lines.append(f"**{quiz.quiz_name}**: rotated (code posted to relay channel).")
            else:
                lines.append(
                    f"**{quiz.quiz_name}**: rotation failed — {result.error_message}."
                )

        await interaction.followup.send("\n".join(lines), ephemeral=True)


def _validate_code_args(random: bool, code: str | None) -> str | None:
    if not random and not code:
        return "Provide a `code` value when `random=false`."
    if random and code:
        return "Cannot specify both `random=true` and a fixed `code`."
    return None
