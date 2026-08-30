from __future__ import annotations

from datetime import datetime, timezone

import discord
from discord import app_commands

from canvas_code_bot.bot.commands.command_utils import parse_ids


class ConfigGroup(app_commands.Group, name="config", description="Manage bot configuration."):
    def __init__(self, services) -> None:
        super().__init__()
        self._svc = services

    @app_commands.command(name="help", description="Show usage for /qb config commands.")
    async def help(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        embed = discord.Embed(
            title="/qb config — Bot Configuration",
            description="Manage the relay channel and role-based access to /qb commands.",
            color=discord.Color.blurple(),
        )
        embed.add_field(
            name="`set-channel channel:<#channel> [quizids]`",
            value=(
                "Set the Discord channel where the bot posts new access codes.\n"
                "• Omit `quizids` to set the **global** relay channel for all quizzes.\n"
                "• Provide `quizids:<comma-separated IDs>` to override the channel "
                "for specific quizzes only."
            ),
            inline=False,
        )
        embed.add_field(
            name="`add-role role:<@role>`  *(admin only)*",
            value=(
                "Grant a Discord role access to all `/qb` commands.\n"
                "Only the bot admin (set via environment variable) can run this."
            ),
            inline=False,
        )
        embed.add_field(
            name="`remove-role role:<@role>`  *(admin only)*",
            value="Revoke a role's access to `/qb` commands.",
            inline=False,
        )
        embed.add_field(
            name="`show`",
            value=(
                "Display the current configuration:\n"
                "global relay channel, allowed roles, and per-quiz channel overrides."
            ),
            inline=False,
        )
        embed.add_field(
            name="Examples",
            value=(
                "Set global relay channel:\n"
                "`/qb config set-channel channel:#quiz-codes`\n\n"
                "Override channel for quiz 2 only:\n"
                "`/qb config set-channel channel:#quiz-2-codes quizids:2`\n\n"
                "Grant access to instructors role:\n"
                "`/qb config add-role role:@Instructors`"
            ),
            inline=False,
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="set-channel", description="Set the relay channel (global or per-quiz).")
    @app_commands.describe(
        channel="The Discord channel to post codes in.",
        quizids="Comma-separated quiz IDs for per-quiz override (omit for global).",
    )
    async def set_channel(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        quizids: str | None = None,
    ) -> None:
        if quizids is None:
            self._svc.config_svc.set_global_channel(
                channel.id, updated_by=interaction.user.id
            )
            await interaction.response.send_message(
                f"Global relay channel set to {channel.mention}.", ephemeral=True
            )
            return

        ids = parse_ids(quizids)
        if not ids:
            await interaction.response.send_message(
                "No valid quiz IDs provided.", ephemeral=True
            )
            return

        missing, updated = [], []
        for qid in ids:
            quiz = self._svc.quiz_repo.get(qid)
            if quiz is None:
                missing.append(str(qid))
                continue
            self._svc.config_svc.set_quiz_channel(
                qid, channel.id, updated_by=interaction.user.id
            )
            updated.append(quiz.quiz_name)

        parts = []
        if updated:
            parts.append(f"Channel set to {channel.mention} for: {', '.join(updated)}.")
        if missing:
            parts.append(f"Quiz IDs not found: {', '.join(missing)}.")
        await interaction.response.send_message(" ".join(parts), ephemeral=True)

    @app_commands.command(
        name="add-role",
        description="Allow a Discord role to use /quizbot commands. Admin only.",
    )
    @app_commands.describe(role="The role to grant access.")
    async def add_role(
        self, interaction: discord.Interaction, role: discord.Role
    ) -> None:
        if not self._is_admin(interaction):
            await interaction.response.send_message(
                "Only the bot admin can manage allowed roles.", ephemeral=True
            )
            return
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        self._svc.allowed_role_repo.add(role.id, added_by=interaction.user.id, at=now)
        await interaction.response.send_message(
            f"{role.mention} can now use /quizbot commands.", ephemeral=True
        )

    @app_commands.command(
        name="remove-role",
        description="Revoke a Discord role's access to /quizbot commands. Admin only.",
    )
    @app_commands.describe(role="The role to revoke.")
    async def remove_role(
        self, interaction: discord.Interaction, role: discord.Role
    ) -> None:
        if not self._is_admin(interaction):
            await interaction.response.send_message(
                "Only the bot admin can manage allowed roles.", ephemeral=True
            )
            return
        self._svc.allowed_role_repo.remove(role.id)
        await interaction.response.send_message(
            f"{role.mention} can no longer use /quizbot commands.", ephemeral=True
        )

    @app_commands.command(name="show", description="Show current bot configuration.")
    async def show(self, interaction: discord.Interaction) -> None:
        cfg = self._svc.config_svc.get()
        global_ch = f"<#{cfg.notify_channel_id}>" if cfg.notify_channel_id else "_not set_"

        embed = discord.Embed(title="Bot Configuration", color=discord.Color.blurple())
        embed.add_field(name="Global relay channel", value=global_ch, inline=False)

        allowed = self._svc.allowed_role_repo.list_all()
        roles_val = (
            " ".join(f"<@&{r.role_id}>" for r in allowed)
            if allowed
            else "_none — only the admin can run commands_"
        )
        embed.add_field(name="Allowed roles", value=roles_val, inline=False)

        quizzes = self._svc.quiz_repo.list_all()
        overrides = [
            f"**{q.quiz_name}** (id={q.id}): <#{q.notify_channel_id}>"
            for q in quizzes
            if q.notify_channel_id is not None
        ]
        if overrides:
            embed.add_field(
                name="Per-quiz channel overrides",
                value="\n".join(overrides),
                inline=False,
            )

        await interaction.response.send_message(embed=embed, ephemeral=True)

    def _is_admin(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self._svc.admin_discord_id


