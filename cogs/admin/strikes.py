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
    @app_commands.guild_only()
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

            # Get admin's top role for display
            admin_role = interaction.user.top_role
            admin_display = admin_role.name if admin_role.name != "@everyone" else "Member"

            embed = discord.Embed(
                title=title,
                color=color
            )
            embed.add_field(name="Player", value=player_name, inline=True)
            embed.add_field(name="Alderon ID", value=f"`{in_game_id}`", inline=True)
            embed.add_field(name="Strike #", value=str(strike_number), inline=True)
            embed.add_field(name="Reason", value=reason, inline=False)
            embed.add_field(name="Issued By", value=f"{interaction.user.mention} ({admin_display})", inline=True)
            embed.set_footer(text="Strikes expire after 30 days each")

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
        description="View active strikes for a player (last 3)"
    )
    @app_commands.guild_only()
    @app_commands.describe(
        in_game_id="The player's Alderon ID (XXX-XXX-XXX)"
    )
    async def view_strikes(self, interaction: discord.Interaction, in_game_id: str):
        """View active strikes for a player (max 3, with expiry info)."""

        if not await require_admin(interaction):
            return

        try:
            guild_id = interaction.guild_id
            GuildQueries.get_or_create(guild_id, interaction.guild.name)

            # Get active strikes only (this also auto-expires old ones)
            active_strikes = StrikeQueries.get_active_strikes(guild_id, in_game_id)
            expiry_info = StrikeQueries.get_strike_expiry_info(guild_id, in_game_id)

            # Also get all strikes to find player name
            all_strikes = StrikeQueries.get_player_strikes(guild_id, in_game_id)

            if not all_strikes:
                await interaction.response.send_message(
                    f"No strikes found for player with ID `{in_game_id}`.",
                    ephemeral=True
                )
                return

            # Get player name from most recent strike
            player_name = all_strikes[-1]['player_name']
            active_count = len(active_strikes)
            total_count = len(all_strikes)

            embed = discord.Embed(
                title=f"Active Strikes for {player_name}",
                description=f"Alderon ID: `{in_game_id}`\n"
                           f"Active Strikes: **{active_count}** (Total history: {total_count})",
                color=discord.Color.orange() if active_count > 0 else discord.Color.green()
            )

            if active_count == 0:
                embed.add_field(
                    name="No Active Strikes",
                    value="This player has no active strikes.\nUse `/strikehistory` to view past strikes.",
                    inline=False
                )
            else:
                # Show only last 3 active strikes with expiry info
                expiry_map = {e['id']: e for e in expiry_info}
                for strike in active_strikes[-3:]:  # Last 3 active strikes
                    expiry = expiry_map.get(strike['id'], {})
                    days_left = expiry.get('days_until_expiry', '?')

                    embed.add_field(
                        name=f"Strike #{strike['strike_number']} - 🔴 Active",
                        value=f"**Reason:** {strike['reason']}\n"
                              f"**By:** {strike['admin_name']}\n"
                              f"**Date:** {strike['created_at'].strftime('%Y-%m-%d')}\n"
                              f"**Expires in:** {days_left} day(s)",
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

            embed.set_footer(text="Use /strikehistory for full strike log")

            await interaction.response.send_message(embed=embed)

        except Exception as e:
            logger.error(f"Error in /strikes: {e}", exc_info=True)
            await interaction.response.send_message(
                "An error occurred while retrieving strikes.",
                ephemeral=True
            )

    @app_commands.command(
        name="removestrike",
        description="Remove a strike from a player"
    )
    @app_commands.guild_only()
    @app_commands.describe(
        in_game_id="The player's Alderon ID (XXX-XXX-XXX)",
        strike_number="Which strike to remove (1, 2, or 3). Removes most recent if not specified."
    )
    async def remove_strike(self, interaction: discord.Interaction,
                            in_game_id: str,
                            strike_number: int = None):
        """Remove a strike from a player by Alderon ID."""

        if not await require_admin(interaction):
            return

        try:
            guild_id = interaction.guild_id

            # Get active strikes for this player
            active_strikes = StrikeQueries.get_active_strikes(guild_id, in_game_id)

            if not active_strikes:
                await interaction.response.send_message(
                    f"No active strikes found for player `{in_game_id}`.",
                    ephemeral=True
                )
                return

            # Find the strike to remove
            if strike_number is not None:
                # Find specific strike by number
                strike_to_remove = next(
                    (s for s in active_strikes if s['strike_number'] == strike_number),
                    None
                )
                if not strike_to_remove:
                    await interaction.response.send_message(
                        f"No active strike #{strike_number} found for player `{in_game_id}`.\n"
                        f"Active strikes: {', '.join(str(s['strike_number']) for s in active_strikes)}",
                        ephemeral=True
                    )
                    return
            else:
                # Remove the most recent (highest numbered) strike
                strike_to_remove = active_strikes[-1]

            # Remove the strike
            if StrikeQueries.remove_strike(strike_to_remove['id']):
                AuditQueries.log(
                    guild_id=guild_id,
                    action_type=AuditQueries.ACTION_STRIKE_REMOVED,
                    performed_by_id=interaction.user.id,
                    performed_by_name=str(interaction.user),
                    target_player_name=strike_to_remove['player_name'],
                    details={
                        'strike_id': strike_to_remove['id'],
                        'in_game_id': in_game_id,
                        'strike_number': strike_to_remove['strike_number']
                    }
                )

                remaining = len(active_strikes) - 1
                await interaction.response.send_message(
                    f"Removed strike #{strike_to_remove['strike_number']} from **{strike_to_remove['player_name']}** (`{in_game_id}`).\n"
                    f"Remaining active strikes: **{remaining}**"
                )
            else:
                await interaction.response.send_message(
                    "Failed to remove strike. Please try again.",
                    ephemeral=True
                )

        except Exception as e:
            logger.error(f"Error in /removestrike: {e}", exc_info=True)
            await interaction.response.send_message(
                "An error occurred while removing the strike.",
                ephemeral=True
            )

    @app_commands.command(
        name="strikehistory",
        description="View full strike history for a player"
    )
    @app_commands.guild_only()
    @app_commands.describe(
        in_game_id="The player's Alderon ID (XXX-XXX-XXX)"
    )
    async def strike_history(self, interaction: discord.Interaction, in_game_id: str):
        """View full strike history for a player (all strikes including removed/expired)."""

        if not await require_admin(interaction):
            return

        try:
            guild_id = interaction.guild_id
            GuildQueries.get_or_create(guild_id, interaction.guild.name)

            all_strikes = StrikeQueries.get_player_strikes(guild_id, in_game_id)

            if not all_strikes:
                await interaction.response.send_message(
                    f"No strike history found for player with ID `{in_game_id}`.",
                    ephemeral=True
                )
                return

            # Get player name from most recent strike
            player_name = all_strikes[-1]['player_name']
            active_count = sum(1 for s in all_strikes if s['is_active'])
            total_count = len(all_strikes)

            embed = discord.Embed(
                title=f"Strike History for {player_name}",
                description=f"Alderon ID: `{in_game_id}`\n"
                           f"Active: **{active_count}** | Total: **{total_count}**",
                color=discord.Color.blue()
            )

            for strike in all_strikes:
                # Determine status
                if strike['is_active']:
                    status = "🔴 Active"
                elif strike.get('expiry_reason') == 'auto_expired':
                    status = "⏰ Expired"
                else:
                    status = "⚪ Removed"

                embed.add_field(
                    name=f"Strike #{strike['strike_number']} - {status}",
                    value=f"**Reason:** {strike['reason'][:100]}{'...' if len(strike['reason']) > 100 else ''}\n"
                          f"**By:** {strike['admin_name']}\n"
                          f"**Date:** {strike['created_at'].strftime('%Y-%m-%d %H:%M')}",
                    inline=False
                )

                # Discord embeds have a limit of 25 fields
                if len(embed.fields) >= 20:
                    embed.add_field(
                        name="...",
                        value=f"*{total_count - 20} more strikes not shown*",
                        inline=False
                    )
                    break

            # Check if banned
            ban = StrikeQueries.get_ban(guild_id, in_game_id)
            if ban:
                embed.add_field(
                    name="🚫 BANNED",
                    value=f"Banned on {ban['banned_at'].strftime('%Y-%m-%d')}\n"
                          f"Reason: {ban['reason'][:50]}...",
                    inline=False
                )

            await interaction.response.send_message(embed=embed)

        except Exception as e:
            logger.error(f"Error in /strikehistory: {e}", exc_info=True)
            await interaction.response.send_message(
                "An error occurred while retrieving strike history.",
                ephemeral=True
            )

    @app_commands.command(
        name="clearstrikes",
        description="Clear all strikes for a player"
    )
    @app_commands.guild_only()
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
    @app_commands.guild_only()
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

    @app_commands.command(
        name="unban",
        description="Unban a player"
    )
    @app_commands.guild_only()
    @app_commands.describe(
        in_game_id="The player's Alderon ID (XXX-XXX-XXX)"
    )
    async def unban_player(self, interaction: discord.Interaction, in_game_id: str):
        """Unban a player by their Alderon ID."""

        if not await require_admin(interaction):
            return

        try:
            guild_id = interaction.guild_id

            # Check if player is actually banned
            ban = StrikeQueries.get_ban(guild_id, in_game_id)
            if not ban:
                await interaction.response.send_message(
                    f"No active ban found for player `{in_game_id}`.",
                    ephemeral=True
                )
                return

            player_name = ban['player_name']

            # Unban the player
            if StrikeQueries.unban(guild_id, in_game_id, interaction.user.id):
                AuditQueries.log(
                    guild_id=guild_id,
                    action_type=AuditQueries.ACTION_UNBAN,
                    performed_by_id=interaction.user.id,
                    performed_by_name=str(interaction.user),
                    target_user_id=ban.get('user_id'),
                    target_player_name=player_name,
                    details={'in_game_id': in_game_id}
                )

                embed = discord.Embed(
                    title="Player Unbanned",
                    color=discord.Color.green()
                )
                embed.add_field(name="Player", value=player_name, inline=True)
                embed.add_field(name="Alderon ID", value=f"`{in_game_id}`", inline=True)
                embed.add_field(name="Unbanned By", value=interaction.user.mention, inline=True)
                embed.set_footer(text="Remember to unban them in-game if applicable!")

                await interaction.response.send_message(embed=embed)
            else:
                await interaction.response.send_message(
                    "Failed to unban player. Please try again.",
                    ephemeral=True
                )

        except Exception as e:
            logger.error(f"Error in /unban: {e}", exc_info=True)
            await interaction.response.send_message(
                "An error occurred while unbanning the player.",
                ephemeral=True
            )

    @app_commands.command(
        name="bans",
        description="View all banned players in this server"
    )
    @app_commands.guild_only()
    @app_commands.describe(
        show_unbanned="Also show players who were unbanned"
    )
    async def list_bans(self, interaction: discord.Interaction, show_unbanned: bool = False):
        """List all banned players."""

        if not await require_admin(interaction):
            return

        try:
            guild_id = interaction.guild_id
            GuildQueries.get_or_create(guild_id, interaction.guild.name)

            bans = StrikeQueries.get_all_bans(guild_id, include_unbanned=show_unbanned)

            if not bans:
                await interaction.response.send_message(
                    "No banned players found." if not show_unbanned else "No ban records found.",
                    ephemeral=True
                )
                return

            embed = discord.Embed(
                title="Banned Players" if not show_unbanned else "Ban History",
                description=f"{len(bans)} record(s) in {interaction.guild.name}",
                color=discord.Color.red()
            )

            for ban in bans[:15]:  # Limit to 15 to avoid embed limits
                status_parts = []
                if ban['banned_in_game']:
                    status_parts.append("In-game: Yes")
                else:
                    status_parts.append("In-game: Pending")

                if ban['unbanned_at']:
                    status_parts.append(f"Unbanned: {ban['unbanned_at'].strftime('%Y-%m-%d')}")
                    icon = "✅"
                else:
                    icon = "🚫"

                embed.add_field(
                    name=f"{icon} {ban['player_name']}",
                    value=f"ID: `{ban['in_game_id']}`\n"
                          f"Reason: {ban['reason'][:40]}...\n"
                          f"Banned: {ban['banned_at'].strftime('%Y-%m-%d')} | {' | '.join(status_parts)}",
                    inline=False
                )

            if len(bans) > 15:
                embed.set_footer(text=f"Showing 15 of {len(bans)} bans")

            await interaction.response.send_message(embed=embed)

        except Exception as e:
            logger.error(f"Error in /bans: {e}", exc_info=True)
            await interaction.response.send_message(
                "An error occurred while retrieving bans.",
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
