# cogs/player/linking.py
"""
Player ID Linking Commands

Allows users to link their Discord account to their Alderon game ID.
"""

import re
import discord
from discord import app_commands
from discord.ext import commands
from database.queries import PlayerQueries, GuildQueries, AuditQueries
import logging

logger = logging.getLogger(__name__)


class PlayerLinking(commands.Cog):
    """Commands for linking Discord accounts to Alderon IDs."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="alderonid",
        description="Link your Discord account to your Alderon ID"
    )
    @app_commands.guild_only()
    @app_commands.describe(
        playerid="Your Alderon ID in format XXX-XXX-XXX",
        playername="Your in-game player name"
    )
    async def link_id(self, interaction: discord.Interaction,
                      playerid: str, playername: str):
        """Link Discord account to Alderon ID."""

        # Validate ID format
        if not re.match(r"^\d{3}-\d{3}-\d{3}$", playerid):
            await interaction.response.send_message(
                "Invalid ID format. Please use the format `XXX-XXX-XXX` "
                "(e.g., `123-456-789`).",
                ephemeral=True
            )
            return

        # Validate player name length
        if len(playername) < 2 or len(playername) > 50:
            await interaction.response.send_message(
                "Player name must be between 2 and 50 characters.",
                ephemeral=True
            )
            return

        try:
            # Ensure guild exists in database
            GuildQueries.get_or_create(
                interaction.guild_id,
                interaction.guild.name
            )

            # Check if feature is enabled
            if not GuildQueries.is_feature_enabled(interaction.guild_id, 'player_linking'):
                await interaction.response.send_message(
                    "Player linking is not enabled on this server.",
                    ephemeral=True
                )
                return

            # Check if this player ID is already linked to someone else
            existing = PlayerQueries.get_by_player_id(interaction.guild_id, playerid)
            if existing and existing['user_id'] != interaction.user.id:
                await interaction.response.send_message(
                    f"This Alderon ID is already linked to another Discord user. "
                    f"If this is your ID, please contact an admin.",
                    ephemeral=True
                )
                return

            # Link the player
            PlayerQueries.link_player(
                guild_id=interaction.guild_id,
                user_id=interaction.user.id,
                username=str(interaction.user),
                player_id=playerid,
                player_name=playername
            )

            # Log to audit
            AuditQueries.log(
                guild_id=interaction.guild_id,
                action_type=AuditQueries.ACTION_PLAYER_LINKED,
                performed_by_id=interaction.user.id,
                performed_by_name=str(interaction.user),
                target_user_id=interaction.user.id,
                details={'player_id': playerid, 'player_name': playername}
            )

            # Create success embed
            embed = discord.Embed(
                title="Player ID Linked",
                color=discord.Color.green()
            )
            embed.add_field(name="Discord User", value=interaction.user.mention, inline=True)
            embed.add_field(name="Alderon ID", value=f"`{playerid}`", inline=True)
            embed.add_field(name="Player Name", value=playername, inline=True)
            embed.set_footer(text="You can update this anytime by running the command again.")

            await interaction.response.send_message(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Error in /alderonid: {e}", exc_info=True)
            await interaction.response.send_message(
                "An error occurred while linking your player ID. Please try again later.",
                ephemeral=True
            )

    @app_commands.command(
        name="playerid",
        description="Look up a player's ID or Discord username"
    )
    @app_commands.guild_only()
    @app_commands.describe(
        query="Discord username or Alderon ID (XXX-XXX-XXX)"
    )
    async def lookup_player(self, interaction: discord.Interaction, query: str):
        """Look up player info by Discord name or Alderon ID."""

        try:
            # Ensure guild exists
            GuildQueries.get_or_create(interaction.guild_id, interaction.guild.name)

            # Check if feature is enabled
            if not GuildQueries.is_feature_enabled(interaction.guild_id, 'player_linking'):
                await interaction.response.send_message(
                    "Player linking is not enabled on this server.",
                    ephemeral=True
                )
                return

            # Determine if query is an Alderon ID or username
            is_alderon_id = re.match(r"^\d{3}-\d{3}-\d{3}$", query)

            if is_alderon_id:
                player = PlayerQueries.get_by_player_id(interaction.guild_id, query)
            else:
                player = PlayerQueries.get_by_username(interaction.guild_id, query)

            if not player:
                # Try search if exact match not found
                results = PlayerQueries.search(interaction.guild_id, query)
                if results:
                    embed = discord.Embed(
                        title="Search Results",
                        description=f"Found {len(results)} partial match(es):",
                        color=discord.Color.blue()
                    )
                    for p in results[:5]:  # Show max 5
                        embed.add_field(
                            name=p['player_name'],
                            value=f"ID: `{p['player_id']}`\nDiscord: {p['username']}",
                            inline=True
                        )
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                else:
                    await interaction.response.send_message(
                        f"No player found matching `{query}`.",
                        ephemeral=True
                    )
                return

            # Found exact match
            embed = discord.Embed(
                title="Player Information",
                color=discord.Color.blue()
            )
            embed.add_field(name="Player Name", value=player['player_name'], inline=True)
            embed.add_field(name="Alderon ID", value=f"`{player['player_id']}`", inline=True)
            embed.add_field(name="Discord", value=player['username'], inline=True)

            await interaction.response.send_message(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Error in /playerid: {e}", exc_info=True)
            await interaction.response.send_message(
                "An error occurred while looking up player info.",
                ephemeral=True
            )

    @app_commands.command(
        name="myid",
        description="View your linked Alderon ID"
    )
    @app_commands.guild_only()
    async def my_id(self, interaction: discord.Interaction):
        """View your own linked player info."""

        try:
            GuildQueries.get_or_create(interaction.guild_id, interaction.guild.name)

            player = PlayerQueries.get_by_user(interaction.guild_id, interaction.user.id)

            if not player:
                await interaction.response.send_message(
                    "You haven't linked an Alderon ID yet.\n"
                    "Use `/alderonid` to link your account.",
                    ephemeral=True
                )
                return

            embed = discord.Embed(
                title="Your Player Information",
                color=discord.Color.green()
            )
            embed.add_field(name="Player Name", value=player['player_name'], inline=True)
            embed.add_field(name="Alderon ID", value=f"`{player['player_id']}`", inline=True)
            embed.set_footer(text="Use /alderonid to update your info")

            await interaction.response.send_message(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Error in /myid: {e}", exc_info=True)
            await interaction.response.send_message(
                "An error occurred. Please try again later.",
                ephemeral=True
            )


async def setup(bot: commands.Bot):
    """Load the PlayerLinking cog."""
    await bot.add_cog(PlayerLinking(bot))
