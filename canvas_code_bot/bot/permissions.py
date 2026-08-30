from __future__ import annotations

import discord
from discord import app_commands


def has_role(role_id: int) -> app_commands.check:
    """Returns an app_commands.check that passes only if the invoking member holds role_id."""
    async def predicate(interaction: discord.Interaction) -> bool:
        if interaction.guild is None:
            await interaction.response.send_message(
                "This command can only be used inside a server.", ephemeral=True
            )
            return False
        member = interaction.user
        if not hasattr(member, "roles") or not any(
            r.id == role_id for r in member.roles
        ):
            await interaction.response.send_message(
                "You don't have permission to use this command.", ephemeral=True
            )
            return False
        return True

    return app_commands.check(predicate)
