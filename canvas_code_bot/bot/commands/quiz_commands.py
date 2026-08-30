from __future__ import annotations

import asyncio
import logging

import discord
from discord import app_commands

from canvas_code_bot.bot.commands.codes_commands import CodesGroup
from canvas_code_bot.bot.commands.config_commands import ConfigGroup
from canvas_code_bot.bot.commands.quizzes_commands import QuizzesGroup
from canvas_code_bot.bot.commands.schedules_commands import SchedulesGroup

logger = logging.getLogger(__name__)


class QbGroup(app_commands.Group, name="qb", description="Canvas quiz access-code rotation bot."):
    def __init__(self, services) -> None:
        super().__init__()
        self._svc = services
        self.add_command(QuizzesGroup(services))
        self.add_command(SchedulesGroup(services))
        self.add_command(CodesGroup(services))
        self.add_command(ConfigGroup(services))

    @app_commands.command(name="help", description="Show an overview of all /qb commands.")
    async def help(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        embed = discord.Embed(
            title="Canvas Quizbot — /qb help",
            description=(
                "Automates Canvas quiz access-code rotation on a schedule "
                "or on demand."
            ),
            color=discord.Color.blurple(),
        )
        embed.add_field(
            name="Quick start",
            value=(
                "1. **Register a quiz** — `/qb quizzes add url:<Canvas URL>`\n"
                "2. **Set the relay channel** — `/qb config set-channel channel:#your-channel`\n"
                "3. **Add a schedule** — `/qb schedules add quizids:<id> cron:0 9 * * 1-5`\n"
                "4. **Check codes** — `/qb codes list`"
            ),
            inline=False,
        )
        embed.add_field(
            name="/qb quizzes",
            value="Register, list, and remove Canvas quizzes.\nRun `/qb quizzes help` for details.",
            inline=False,
        )
        embed.add_field(
            name="/qb schedules",
            value=(
                "Add, update, list, and delete rotation schedules.\n"
                "Run `/qb schedules help` for details."
            ),
            inline=False,
        )
        embed.add_field(
            name="/qb codes",
            value=(
                "View current access codes or trigger an immediate rotation.\n"
                "Run `/qb codes help` for details."
            ),
            inline=False,
        )
        embed.add_field(
            name="/qb config",
            value=(
                "Set the relay channel and manage allowed roles.\n"
                "Run `/qb config help` for details."
            ),
            inline=False,
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Gate every /qb command to allowed roles (DB) or the admin user."""
        command_name = interaction.command.qualified_name if interaction.command else "unknown"
        guild_name = interaction.guild.name if interaction.guild else "DM"
        logger.info(
            "command=%r user=%s (%d) guild=%r",
            command_name,
            interaction.user.display_name,
            interaction.user.id,
            guild_name,
        )
        if interaction.user.id == self._svc.admin_discord_id:
            return True
        if interaction.guild is None:
            await interaction.response.send_message(
                "This command can only be used inside a server.", ephemeral=True
            )
            return False
        member = interaction.user
        if not hasattr(member, "roles"):
            await interaction.response.send_message(
                "You don't have permission to use this command.", ephemeral=True
            )
            return False
        user_role_ids = {r.id for r in member.roles}
        has_role = await asyncio.to_thread(
            self._svc.allowed_role_repo.has_any, user_role_ids
        )
        if not has_role:
            await interaction.response.send_message(
                "You don't have permission to use this command.", ephemeral=True
            )
            return False
        return True
