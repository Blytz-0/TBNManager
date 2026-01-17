# cogs/admin/strikes.py
"""
Strike Management Commands

Admin commands for managing player strikes. Replaces Trello-based system
with database-backed strike tracking.
"""

import discord
from discord import app_commands
from discord.ext import commands
from database.queries import StrikeQueries, PlayerQueries, GuildQueries, AuditQueries
from services.permissions import require_admin
import logging

logger = logging.getLogger(__name__)


class StrikeCommands(commands.Cog):
    """Commands for managing player strikes."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="addstrike",
        description="Add a strike to a player"
    )
    @app_commands.describe(
        player_name="The player's in-game name",
        in_game_id="The player's Alderon ID (XXX-XXX-XXX)",
        reason="Reason for the strike"
    )
    async def add_strike(self, interaction: discord.Interaction,
                         player_name: str, in_game_id: str, reason: str):
        """Add a strike to a player."""

        # Check admin permissions
        if not await require_admin(interaction):
            return

        await interaction.response.defer()

        try:
            guild_id = interaction.guild_id
            GuildQueries.get_or_create(guild_id, interaction.guild.name)

            # Check if feature is enabled
            if not GuildQueries.is_feature_enabled(guild_id, 'strikes'):
                await interaction.followup.send(
                    "Strike system is not enabled on this server.",
                    ephemeral=True
                )
                return

            # Check if player is already banned
            if StrikeQueries.is_banned(guild_id, in_game_id):
                await interaction.followup.send(
                    f"**{player_name}** (`{in_game_id}`) is already banned and cannot receive more strikes."
                )
                return

            # Get linked Discord user if exists
            linked_player = PlayerQueries.get_by_player_id(guild_id, in_game_id)
            user_id = linked_player['user_id'] if linked_player else None

            # Add the strike
            strike = StrikeQueries.add_strike(
                guild_id=guild_id,
                player_name=player_name,
                in_game_id=in_game_id,
                reason=reason,
                admin_id=interaction.user.id,
                admin_name=str(interaction.user),
                user_id=user_id
            )

            strike_number = strike['strike_number']

            # Log to audit
            AuditQueries.log(
                guild_id=guild_id,
                action_type=AuditQueries.ACTION_STRIKE_ADDED,
                performed_by_id=interaction.user.id,
                performed_by_name=str(interaction.user),
                target_user_id=user_id,
                target_player_name=player_name,
                details={
                    'in_game_id': in_game_id,
                    'reason': reason,
                    'strike_number': strike_number
                }
            )

            # Create response embed
            if strike_number == 1:
                color = discord.Color.yellow()
                title = "1st Strike Issued"
            elif strike_number == 2:
                color = discord.Color.orange()
                title = "2nd Strike Issued"
            else:
                color = discord.Color.red()
                title = f"Strike #{strike_number} Issued"

            embed = discord.Embed(
                title=title,
                color=color
            )
            embed.add_field(name="Player", value=player_name, inline=True)
            embed.add_field(name="Alderon ID", value=f"`{in_game_id}`", inline=True)
            embed.add_field(name="Strike #", value=str(strike_number), inline=True)
            embed.add_field(name="Reason", value=reason, inline=False)
            embed.add_field(name="Issued By", value=interaction.user.mention, inline=True)
            embed.set_footer(text=f"Strike ID: {strike['id']}")

            await interaction.followup.send(embed=embed)

            # Handle 3rd strike - auto ban prompt
            if strike_number >= 3 and GuildQueries.is_feature_enabled(guild_id, 'auto_ban'):
                await self._handle_third_strike(interaction, player_name, in_game_id, reason, user_id)

            # DM the user if linked and feature enabled
            if user_id and GuildQueries.is_feature_enabled(guild_id, 'dm_notifications'):
                await self._notify_user(interaction.guild, user_id, strike_number, reason)

        except Exception as e:
            logger.error(f"Error in /addstrike: {e}", exc_info=True)
            await interaction.followup.send(
                "An error occurred while adding the strike. Please try again.",
                ephemeral=True
            )

    async def _handle_third_strike(self, interaction: discord.Interaction,
                                   player_name: str, in_game_id: str,
                                   reason: str, user_id: int | None):
        """Handle automatic ban prompt after 3rd strike."""

        guild_id = interaction.guild_id

        # Send warning
        await interaction.followup.send(
            f"⚠️ **{player_name}** (`{in_game_id}`) has reached 3 strikes and needs to be banned!"
        )

        # Create confirmation view
        view = BanConfirmationView(
            bot=self.bot,
            guild_id=guild_id,
            player_name=player_name,
            in_game_id=in_game_id,
            reason=f"3rd Strike: {reason}",
            banned_by=interaction.user,
            user_id=user_id
        )

        await interaction.followup.send(
            "Has this player been banned in-game?",
            view=view
        )

    async def _notify_user(self, guild: discord.Guild, user_id: int,
                          strike_number: int, reason: str):
        """Send DM notification to user about their strike."""
        try:
            member = guild.get_member(user_id)
            if member:
                embed = discord.Embed(
                    title=f"You have received Strike #{strike_number}",
                    description=f"**Server:** {guild.name}",
                    color=discord.Color.red()
                )
                embed.add_field(name="Reason", value=reason, inline=False)

                if strike_number >= 3:
                    embed.add_field(
                        name="⚠️ Warning",
                        value="You have reached 3 strikes and may be banned.",
                        inline=False
                    )

                await member.send(embed=embed)
        except discord.Forbidden:
            logger.warning(f"Could not DM user {user_id} about strike")
        except Exception as e:
            logger.error(f"Error sending strike notification: {e}")

    @app_commands.command(
        name="strikes",
        description="View strikes for a player"
    )
    @app_commands.describe(
        in_game_id="The player's Alderon ID (XXX-XXX-XXX)"
    )
    async def view_strikes(self, interaction: discord.Interaction, in_game_id: str):
        """View all strikes for a player."""

        if not await require_admin(interaction):
            return

        try:
            guild_id = interaction.guild_id
            GuildQueries.get_or_create(guild_id, interaction.guild.name)

            strikes = StrikeQueries.get_player_strikes(guild_id, in_game_id)

            if not strikes:
                await interaction.response.send_message(
                    f"No strikes found for player with ID `{in_game_id}`.",
                    ephemeral=True
                )
                return

            # Get player name from most recent strike
            player_name = strikes[-1]['player_name']
            active_count = sum(1 for s in strikes if s['is_active'])

            embed = discord.Embed(
                title=f"Strikes for {player_name}",
                description=f"Alderon ID: `{in_game_id}`\n"
                           f"Active Strikes: **{active_count}**",
                color=discord.Color.orange() if active_count > 0 else discord.Color.green()
            )

            for strike in strikes:
                status = "🔴 Active" if strike['is_active'] else "⚪ Removed"
                embed.add_field(
                    name=f"Strike #{strike['strike_number']} - {status}",
                    value=f"**Reason:** {strike['reason']}\n"
                          f"**By:** {strike['admin_name']}\n"
                          f"**Date:** {strike['created_at'].strftime('%Y-%m-%d %H:%M')}",
                    inline=False
                )

            # Check if banned
            ban = StrikeQueries.get_ban(guild_id, in_game_id)
            if ban:
                embed.add_field(
                    name="🚫 BANNED",
                    value=f"Banned on {ban['banned_at'].strftime('%Y-%m-%d')}\n"
                          f"In-game: {'Yes' if ban['banned_in_game'] else 'Pending'}",
                    inline=False
                )

            await interaction.response.send_message(embed=embed)

        except Exception as e:
            logger.error(f"Error in /strikes: {e}", exc_info=True)
            await interaction.response.send_message(
                "An error occurred while retrieving strikes.",
                ephemeral=True
            )

    @app_commands.command(
        name="removestrike",
        description="Remove a specific strike from a player"
    )
    @app_commands.describe(
        strike_id="The strike ID to remove (shown in /strikes)"
    )
    async def remove_strike(self, interaction: discord.Interaction, strike_id: int):
        """Remove a strike by ID."""

        if not await require_admin(interaction):
            return

        try:
            guild_id = interaction.guild_id

            # Remove the strike
            if StrikeQueries.remove_strike(strike_id):
                AuditQueries.log(
                    guild_id=guild_id,
                    action_type=AuditQueries.ACTION_STRIKE_REMOVED,
                    performed_by_id=interaction.user.id,
                    performed_by_name=str(interaction.user),
                    details={'strike_id': strike_id}
                )

                await interaction.response.send_message(
                    f"Strike #{strike_id} has been removed.",
                    ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    f"Strike #{strike_id} not found.",
                    ephemeral=True
                )

        except Exception as e:
            logger.error(f"Error in /removestrike: {e}", exc_info=True)
            await interaction.response.send_message(
                "An error occurred while removing the strike.",
                ephemeral=True
            )

    @app_commands.command(
        name="clearstrikes",
        description="Clear all strikes for a player"
    )
    @app_commands.describe(
        in_game_id="The player's Alderon ID (XXX-XXX-XXX)"
    )
    async def clear_strikes(self, interaction: discord.Interaction, in_game_id: str):
        """Clear all active strikes for a player."""

        if not await require_admin(interaction):
            return

        try:
            guild_id = interaction.guild_id
            count = StrikeQueries.clear_strikes(guild_id, in_game_id)

            if count > 0:
                AuditQueries.log(
                    guild_id=guild_id,
                    action_type=AuditQueries.ACTION_STRIKES_CLEARED,
                    performed_by_id=interaction.user.id,
                    performed_by_name=str(interaction.user),
                    details={'in_game_id': in_game_id, 'count': count}
                )

                await interaction.response.send_message(
                    f"Cleared {count} strike(s) for player `{in_game_id}`."
                )
            else:
                await interaction.response.send_message(
                    f"No active strikes found for player `{in_game_id}`.",
                    ephemeral=True
                )

        except Exception as e:
            logger.error(f"Error in /clearstrikes: {e}", exc_info=True)
            await interaction.response.send_message(
                "An error occurred while clearing strikes.",
                ephemeral=True
            )

    @app_commands.command(
        name="recentstrikes",
        description="View recent strikes in this server"
    )
    async def recent_strikes(self, interaction: discord.Interaction):
        """View the most recent strikes."""

        if not await require_admin(interaction):
            return

        try:
            guild_id = interaction.guild_id
            GuildQueries.get_or_create(guild_id, interaction.guild.name)

            strikes = StrikeQueries.get_recent_strikes(guild_id, limit=10)

            if not strikes:
                await interaction.response.send_message(
                    "No strikes have been issued in this server yet.",
                    ephemeral=True
                )
                return

            embed = discord.Embed(
                title="Recent Strikes",
                description=f"Last {len(strikes)} strikes in {interaction.guild.name}",
                color=discord.Color.orange()
            )

            for strike in strikes:
                status = "🔴" if strike['is_active'] else "⚪"
                embed.add_field(
                    name=f"{status} {strike['player_name']} - Strike #{strike['strike_number']}",
                    value=f"ID: `{strike['in_game_id']}`\n"
                          f"Reason: {strike['reason'][:50]}...\n"
                          f"By: {strike['admin_name']} | {strike['created_at'].strftime('%m/%d %H:%M')}",
                    inline=False
                )

            await interaction.response.send_message(embed=embed)

        except Exception as e:
            logger.error(f"Error in /recentstrikes: {e}", exc_info=True)
            await interaction.response.send_message(
                "An error occurred while retrieving recent strikes.",
                ephemeral=True
            )


class BanConfirmationView(discord.ui.View):
    """View for confirming in-game ban after 3rd strike."""

    def __init__(self, bot, guild_id: int, player_name: str, in_game_id: str,
                 reason: str, banned_by: discord.User, user_id: int | None):
        super().__init__(timeout=300)  # 5 minute timeout
        self.bot = bot
        self.guild_id = guild_id
        self.player_name = player_name
        self.in_game_id = in_game_id
        self.reason = reason
        self.banned_by = banned_by
        self.user_id = user_id

    @discord.ui.button(label="Yes, banned in-game", style=discord.ButtonStyle.danger)
    async def confirm_ban(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Confirm the in-game ban."""

        # Add ban record
        StrikeQueries.add_ban(
            guild_id=self.guild_id,
            player_name=self.player_name,
            in_game_id=self.in_game_id,
            reason=self.reason,
            banned_by_id=self.banned_by.id,
            banned_by_name=str(self.banned_by),
            user_id=self.user_id,
            banned_in_game=True
        )

        AuditQueries.log(
            guild_id=self.guild_id,
            action_type=AuditQueries.ACTION_BAN,
            performed_by_id=self.banned_by.id,
            performed_by_name=str(self.banned_by),
            target_user_id=self.user_id,
            target_player_name=self.player_name,
            details={'in_game_id': self.in_game_id, 'reason': self.reason, 'in_game': True}
        )

        await interaction.response.edit_message(
            content=f"✅ **{self.player_name}** (`{self.in_game_id}`) has been recorded as banned.",
            view=None
        )

    @discord.ui.button(label="Not yet", style=discord.ButtonStyle.secondary)
    async def pending_ban(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Mark ban as pending."""

        StrikeQueries.add_ban(
            guild_id=self.guild_id,
            player_name=self.player_name,
            in_game_id=self.in_game_id,
            reason=self.reason,
            banned_by_id=self.banned_by.id,
            banned_by_name=str(self.banned_by),
            user_id=self.user_id,
            banned_in_game=False
        )

        AuditQueries.log(
            guild_id=self.guild_id,
            action_type=AuditQueries.ACTION_BAN,
            performed_by_id=self.banned_by.id,
            performed_by_name=str(self.banned_by),
            target_user_id=self.user_id,
            target_player_name=self.player_name,
            details={'in_game_id': self.in_game_id, 'reason': self.reason, 'in_game': False}
        )

        await interaction.response.edit_message(
            content=f"📋 **{self.player_name}** (`{self.in_game_id}`) has been recorded. "
                    f"Remember to ban them in-game!",
            view=None
        )


async def setup(bot: commands.Bot):
    """Load the StrikeCommands cog."""
    await bot.add_cog(StrikeCommands(bot))
