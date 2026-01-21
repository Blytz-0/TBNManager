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
    async def add_strike(self, interaction: discord.Interaction):
        """Add a strike to a player - opens a modal form."""

        # Check admin permissions
        if not await require_admin(interaction):
            return

        guild_id = interaction.guild_id
        GuildQueries.get_or_create(guild_id, interaction.guild.name)

        # Check if feature is enabled
        if not GuildQueries.is_feature_enabled(guild_id, 'strikes'):
            await interaction.response.send_message(
                "Strike system is not enabled on this server.",
                ephemeral=True
            )
            return

        # Show the strike modal
        modal = AddStrikeModal(self)
        await interaction.response.send_modal(modal)

    async def _process_strike(self, interaction: discord.Interaction,
                              player_name: str, in_game_id: str, reason: str):
        """Process a strike after modal submission."""
        try:
            guild_id = interaction.guild_id

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

            if strike.get('reference_id'):
                embed.add_field(name="Reference ID", value=f"`{strike['reference_id']}`", inline=True)

            embed.set_footer(text="Strikes expire after 30 days each")

            await interaction.followup.send(embed=embed)

            # Handle 3rd strike - auto ban prompt
            if strike_number >= 3 and GuildQueries.is_feature_enabled(guild_id, 'auto_ban'):
                await self._handle_third_strike(interaction, player_name, in_game_id, reason, user_id)

            # DM the user if linked and feature enabled
            if user_id and GuildQueries.is_feature_enabled(guild_id, 'dm_notifications'):
                await self._notify_user(
                    interaction.guild, user_id, strike_number, reason,
                    admin_name=str(interaction.user), in_game_id=in_game_id,
                    reference_id=strike.get('reference_id')
                )

        except Exception as e:
            logger.error(f"Error processing strike: {e}", exc_info=True)
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
                          strike_number: int, reason: str,
                          admin_name: str = None, in_game_id: str = None,
                          reference_id: str = None):
        """Send DM notification to user about their strike."""
        try:
            member = guild.get_member(user_id)
            if not member:
                return

            from datetime import datetime, timedelta
            now = datetime.now()
            expiry_date = now + timedelta(days=30 * strike_number)

            # Determine color based on severity
            if strike_number == 1:
                color = discord.Color.yellow()
            elif strike_number == 2:
                color = discord.Color.orange()
            else:
                color = discord.Color.red()

            embed = discord.Embed(
                title=f"Strike #{strike_number} Received",
                description=f"You have received a strike on **{guild.name}**",
                color=color,
                timestamp=now
            )

            # Strike details
            embed.add_field(name="Reason", value=reason, inline=False)
            embed.add_field(name="Issued On", value=now.strftime("%d %B %Y at %H:%M"), inline=True)
            embed.add_field(name="Issued By", value=admin_name or "Staff", inline=True)

            if in_game_id:
                embed.add_field(name="Player ID", value=f"`{in_game_id}`", inline=True)

            # Reference ID for appeals
            if reference_id:
                embed.add_field(name="Reference ID", value=f"`{reference_id}`", inline=True)

            # Expiry info
            embed.add_field(
                name="Strike Expiry",
                value=f"This strike will automatically expire on **{expiry_date.strftime('%d %B %Y')}** "
                      f"(in {30 * strike_number} days) if no further strikes are issued.",
                inline=False
            )

            # Current status
            status_text = f"You currently have **{strike_number}** active strike(s)."
            if strike_number == 1:
                status_text += "\nThis is your first strike - please review the server rules to avoid further action."
            elif strike_number == 2:
                status_text += "\n**This is your final warning.** One more strike will result in a ban."

            embed.add_field(name="Current Status", value=status_text, inline=False)

            # Warning for 3rd strike
            if strike_number >= 3:
                embed.add_field(
                    name="🚫 BAN IMMINENT",
                    value="You have reached **3 strikes** and are now subject to a ban.\n"
                          "If you believe this is unfair, you may appeal by opening a ticket in the server.",
                    inline=False
                )

            # Appeal info with reference
            appeal_text = "Please review and follow the server rules to avoid further strikes.\n"
            if reference_id:
                appeal_text += f"\n**To appeal:** Open a ticket and provide your Reference ID: `{reference_id}`"
            embed.add_field(
                name="📋 Server Guidelines",
                value=appeal_text,
                inline=False
            )

            embed.set_footer(text=f"{guild.name} • Moderation System")
            if guild.icon:
                embed.set_thumbnail(url=guild.icon.url)

            await member.send(embed=embed)

        except discord.Forbidden:
            logger.warning(f"Could not DM user {user_id} about strike")
        except Exception as e:
            logger.error(f"Error sending strike notification: {e}")

    @app_commands.command(
        name="strikelist",
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
        name="ban",
        description="Directly ban a player (without needing 3 strikes)"
    )
    @app_commands.guild_only()
    async def direct_ban(self, interaction: discord.Interaction):
        """Directly ban a player - opens a modal form."""

        if not await require_admin(interaction):
            return

        guild_id = interaction.guild_id
        GuildQueries.get_or_create(guild_id, interaction.guild.name)

        # Check if feature is enabled
        if not GuildQueries.is_feature_enabled(guild_id, 'strikes'):
            await interaction.response.send_message(
                "Strike/ban system is not enabled on this server.",
                ephemeral=True
            )
            return

        # Show the ban modal
        modal = DirectBanModal(self)
        await interaction.response.send_modal(modal)

    async def _process_direct_ban(self, interaction: discord.Interaction,
                                   player_name: str, in_game_id: str, reason: str):
        """Process a direct ban after modal submission."""
        try:
            guild_id = interaction.guild_id

            # Check if player is already banned
            if StrikeQueries.is_banned(guild_id, in_game_id):
                await interaction.followup.send(
                    f"**{player_name}** (`{in_game_id}`) is already banned.",
                    ephemeral=True
                )
                return

            # Get linked Discord user if exists
            linked_player = PlayerQueries.get_by_player_id(guild_id, in_game_id)
            user_id = linked_player['user_id'] if linked_player else None

            # Add the ban (show confirmation for in-game status)
            view = DirectBanConfirmView(
                cog=self,
                guild_id=guild_id,
                player_name=player_name,
                in_game_id=in_game_id,
                reason=reason,
                banned_by=interaction.user,
                user_id=user_id
            )

            await interaction.followup.send(
                f"Ban **{player_name}** (`{in_game_id}`)?\n"
                f"**Reason:** {reason}\n\n"
                f"Has this player been banned in-game?",
                view=view
            )

        except Exception as e:
            logger.error(f"Error processing ban: {e}", exc_info=True)
            await interaction.followup.send(
                "An error occurred while processing the ban.",
                ephemeral=True
            )

    async def _send_direct_ban_notification(self, guild: discord.Guild, user_id: int,
                                            player_name: str, in_game_id: str,
                                            reason: str, admin_name: str,
                                            reference_id: str = None):
        """Send DM notification for direct ban."""
        try:
            member = guild.get_member(user_id)
            if not member:
                return

            from datetime import datetime
            now = datetime.now()

            embed = discord.Embed(
                title="🚫 You Have Been Banned",
                description=f"You have been banned from **{guild.name}**",
                color=discord.Color.dark_red(),
                timestamp=now
            )

            embed.add_field(name="Reason", value=reason, inline=False)
            embed.add_field(name="Banned On", value=now.strftime("%d %B %Y at %H:%M"), inline=True)
            embed.add_field(name="Banned By", value=admin_name, inline=True)
            embed.add_field(name="Player ID", value=f"`{in_game_id}`", inline=True)

            if reference_id:
                embed.add_field(name="Reference ID", value=f"`{reference_id}`", inline=True)

            embed.add_field(
                name="📋 What This Means",
                value="• You have been banned from the game server\n"
                      "• You will not be able to rejoin until unbanned\n"
                      "• This ban is logged in our moderation system",
                inline=False
            )

            appeal_text = "If you believe this ban was issued in error, you may appeal.\n"
            if reference_id:
                appeal_text += f"\n**Your Reference ID:** `{reference_id}`\n"
                appeal_text += "Use this ID when opening an appeal ticket."

            embed.add_field(
                name="⚖️ Appeal Process",
                value=appeal_text,
                inline=False
            )

            embed.set_footer(text=f"{guild.name} • Moderation System")
            if guild.icon:
                embed.set_thumbnail(url=guild.icon.url)

            await member.send(embed=embed)

        except discord.Forbidden:
            logger.warning(f"Could not DM user {user_id} about direct ban")
        except Exception as e:
            logger.error(f"Error sending direct ban notification: {e}")

    @app_commands.command(
        name="wipehistory",
        description="Completely delete all strike and ban records for a player"
    )
    @app_commands.guild_only()
    @app_commands.describe(
        in_game_id="The player's Alderon ID (XXX-XXX-XXX)"
    )
    async def wipe_history(self, interaction: discord.Interaction, in_game_id: str):
        """Completely wipe all records for a player - opens confirmation modal."""

        if not await require_admin(interaction):
            return

        try:
            guild_id = interaction.guild_id

            # Get current records to show what will be deleted
            all_strikes = StrikeQueries.get_player_strikes(guild_id, in_game_id)
            ban = StrikeQueries.get_ban(guild_id, in_game_id)

            if not all_strikes and not ban:
                await interaction.response.send_message(
                    f"No records found for player `{in_game_id}`.",
                    ephemeral=True
                )
                return

            player_name = all_strikes[-1]['player_name'] if all_strikes else ban['player_name']

            # Show confirmation
            modal = WipeHistoryConfirmModal(
                guild_id=guild_id,
                player_name=player_name,
                in_game_id=in_game_id,
                strike_count=len(all_strikes),
                has_ban=ban is not None
            )
            await interaction.response.send_modal(modal)

        except Exception as e:
            logger.error(f"Error in /wipehistory: {e}", exc_info=True)
            await interaction.response.send_message(
                "An error occurred.",
                ephemeral=True
            )

    @app_commands.command(
        name="banlist",
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


class AddStrikeModal(discord.ui.Modal, title="Add Strike"):
    """Modal for adding a strike to a player."""

    player_name = discord.ui.TextInput(
        label="Player Name",
        placeholder="Enter the player's in-game name",
        required=True,
        max_length=100
    )

    in_game_id = discord.ui.TextInput(
        label="Alderon ID",
        placeholder="XXX-XXX-XXX",
        required=True,
        max_length=20
    )

    reason = discord.ui.TextInput(
        label="Reason for Strike",
        placeholder="Describe the rule violation...",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=500
    )

    def __init__(self, cog):
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        await self.cog._process_strike(
            interaction,
            self.player_name.value,
            self.in_game_id.value.strip(),
            self.reason.value
        )


class DirectBanModal(discord.ui.Modal, title="Direct Ban"):
    """Modal for directly banning a player."""

    player_name = discord.ui.TextInput(
        label="Player Name",
        placeholder="Enter the player's in-game name",
        required=True,
        max_length=100
    )

    in_game_id = discord.ui.TextInput(
        label="Alderon ID",
        placeholder="XXX-XXX-XXX",
        required=True,
        max_length=20
    )

    reason = discord.ui.TextInput(
        label="Reason for Ban",
        placeholder="Describe why this player is being banned...",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=500
    )

    def __init__(self, cog):
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        await self.cog._process_direct_ban(
            interaction,
            self.player_name.value,
            self.in_game_id.value.strip(),
            self.reason.value
        )


class DirectBanConfirmView(discord.ui.View):
    """View for confirming in-game ban status for direct bans."""

    def __init__(self, cog, guild_id: int, player_name: str, in_game_id: str,
                 reason: str, banned_by: discord.User, user_id: int | None):
        super().__init__(timeout=300)
        self.cog = cog
        self.guild_id = guild_id
        self.player_name = player_name
        self.in_game_id = in_game_id
        self.reason = reason
        self.banned_by = banned_by
        self.user_id = user_id

    async def _complete_ban(self, interaction: discord.Interaction, banned_in_game: bool):
        """Complete the ban process."""
        # Add the ban
        ban = StrikeQueries.add_ban(
            guild_id=self.guild_id,
            player_name=self.player_name,
            in_game_id=self.in_game_id,
            reason=self.reason,
            banned_by_id=self.banned_by.id,
            banned_by_name=str(self.banned_by),
            user_id=self.user_id,
            banned_in_game=banned_in_game
        )

        # Log to audit
        AuditQueries.log(
            guild_id=self.guild_id,
            action_type=AuditQueries.ACTION_BAN,
            performed_by_id=self.banned_by.id,
            performed_by_name=str(self.banned_by),
            target_user_id=self.user_id,
            target_player_name=self.player_name,
            details={
                'in_game_id': self.in_game_id,
                'reason': self.reason,
                'in_game': banned_in_game,
                'direct_ban': True
            }
        )

        # Create response embed
        embed = discord.Embed(
            title="Player Banned",
            color=discord.Color.dark_red()
        )
        embed.add_field(name="Player", value=self.player_name, inline=True)
        embed.add_field(name="Alderon ID", value=f"`{self.in_game_id}`", inline=True)
        embed.add_field(name="In-Game Ban", value="Yes" if banned_in_game else "Pending", inline=True)
        embed.add_field(name="Reason", value=self.reason, inline=False)
        embed.add_field(name="Banned By", value=self.banned_by.mention, inline=True)

        if ban.get('reference_id'):
            embed.add_field(name="Reference ID", value=f"`{ban['reference_id']}`", inline=True)

        embed.set_footer(text="Direct ban - no strikes required")

        await interaction.response.edit_message(content=None, embed=embed, view=None)

        # DM the user if linked and feature enabled
        if self.user_id and GuildQueries.is_feature_enabled(self.guild_id, 'dm_notifications'):
            await self.cog._send_direct_ban_notification(
                interaction.guild, self.user_id, self.player_name, self.in_game_id,
                self.reason, str(self.banned_by), ban.get('reference_id')
            )

    @discord.ui.button(label="Yes, banned in-game", style=discord.ButtonStyle.danger)
    async def confirm_in_game(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._complete_ban(interaction, banned_in_game=True)

    @discord.ui.button(label="Not yet", style=discord.ButtonStyle.secondary)
    async def pending_in_game(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._complete_ban(interaction, banned_in_game=False)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel_ban(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="Ban cancelled.", view=None)


class WipeHistoryConfirmModal(discord.ui.Modal, title="Confirm History Wipe"):
    """Confirmation modal for wiping player history."""

    confirmation = discord.ui.TextInput(
        label="Type CONFIRM to proceed",
        placeholder="CONFIRM",
        required=True,
        max_length=10
    )

    def __init__(self, guild_id: int, player_name: str, in_game_id: str,
                 strike_count: int, has_ban: bool):
        super().__init__()
        self.guild_id = guild_id
        self.player_name = player_name
        self.in_game_id = in_game_id
        self.strike_count = strike_count
        self.has_ban = has_ban

        # Update the title to show what will be deleted
        ban_text = " + BAN" if has_ban else ""
        self.title = f"Wipe {strike_count} strikes{ban_text}?"

    async def on_submit(self, interaction: discord.Interaction):
        if self.confirmation.value.upper() != "CONFIRM":
            await interaction.response.send_message(
                "Wipe cancelled. You must type CONFIRM to proceed.",
                ephemeral=True
            )
            return

        # Perform the wipe
        result = StrikeQueries.wipe_player_history(self.guild_id, self.in_game_id)

        # Log to audit
        AuditQueries.log(
            guild_id=self.guild_id,
            action_type='history_wiped',
            performed_by_id=interaction.user.id,
            performed_by_name=str(interaction.user),
            target_player_name=self.player_name,
            details={
                'in_game_id': self.in_game_id,
                'strikes_deleted': result['strikes_deleted'],
                'bans_deleted': result['bans_deleted']
            }
        )

        embed = discord.Embed(
            title="History Wiped",
            description=f"All records for **{self.player_name}** have been permanently deleted.",
            color=discord.Color.green()
        )
        embed.add_field(name="Alderon ID", value=f"`{self.in_game_id}`", inline=True)
        embed.add_field(name="Strikes Deleted", value=str(result['strikes_deleted']), inline=True)
        embed.add_field(name="Bans Deleted", value=str(result['bans_deleted']), inline=True)
        embed.add_field(name="Wiped By", value=interaction.user.mention, inline=False)
        embed.set_footer(text="This action cannot be undone")

        await interaction.response.send_message(embed=embed)


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

    async def _send_ban_notification(self, guild: discord.Guild, reference_id: str = None):
        """Send ban notification DM to the user."""
        if not self.user_id:
            return

        try:
            member = guild.get_member(self.user_id)
            if not member:
                return

            from datetime import datetime
            now = datetime.now()

            embed = discord.Embed(
                title="🚫 You Have Been Banned",
                description=f"You have been banned from **{guild.name}**",
                color=discord.Color.dark_red(),
                timestamp=now
            )

            embed.add_field(name="Reason", value=self.reason, inline=False)
            embed.add_field(name="Banned On", value=now.strftime("%d %B %Y at %H:%M"), inline=True)
            embed.add_field(name="Banned By", value=str(self.banned_by), inline=True)
            embed.add_field(name="Player ID", value=f"`{self.in_game_id}`", inline=True)

            # Reference ID for appeals
            if reference_id:
                embed.add_field(name="Reference ID", value=f"`{reference_id}`", inline=True)

            embed.add_field(
                name="📋 What This Means",
                value="• You have been banned from the game server\n"
                      "• You will not be able to rejoin until unbanned\n"
                      "• This ban is logged in our moderation system",
                inline=False
            )

            # Appeal process with reference ID
            appeal_text = "If you believe this ban was issued in error, you may appeal.\n"
            appeal_text += "**To appeal:** Open a ticket in the server (if you still have access) "
            appeal_text += "or contact a staff member directly.\n\n"
            if reference_id:
                appeal_text += f"**Your Reference ID:** `{reference_id}`\n"
                appeal_text += "Use this ID when opening an appeal ticket.\n\n"
            appeal_text += "Please provide:\n"
            appeal_text += "• Your Player ID\n"
            appeal_text += "• Reason you believe the ban is unfair\n"
            appeal_text += "• Any evidence to support your case"

            embed.add_field(
                name="⚖️ Appeal Process",
                value=appeal_text,
                inline=False
            )

            embed.set_footer(text=f"{guild.name} • Moderation System")
            if guild.icon:
                embed.set_thumbnail(url=guild.icon.url)

            await member.send(embed=embed)
            logger.info(f"Sent ban notification to user {self.user_id}")

        except discord.Forbidden:
            logger.warning(f"Could not DM user {self.user_id} about ban")
        except Exception as e:
            logger.error(f"Error sending ban notification: {e}")

    @discord.ui.button(label="Yes, banned in-game", style=discord.ButtonStyle.danger)
    async def confirm_ban(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Confirm the in-game ban."""

        # Add ban record
        ban = StrikeQueries.add_ban(
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

        # Send ban notification if DM notifications enabled
        if GuildQueries.is_feature_enabled(self.guild_id, 'dm_notifications'):
            await self._send_ban_notification(interaction.guild, reference_id=ban.get('reference_id'))

        await interaction.response.edit_message(
            content=f"✅ **{self.player_name}** (`{self.in_game_id}`) has been recorded as banned.",
            view=None
        )

    @discord.ui.button(label="Not yet", style=discord.ButtonStyle.secondary)
    async def pending_ban(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Mark ban as pending."""

        ban = StrikeQueries.add_ban(
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

        # Send ban notification if DM notifications enabled
        if GuildQueries.is_feature_enabled(self.guild_id, 'dm_notifications'):
            await self._send_ban_notification(interaction.guild, reference_id=ban.get('reference_id'))

        await interaction.response.edit_message(
            content=f"📋 **{self.player_name}** (`{self.in_game_id}`) has been recorded. "
                    f"Remember to ban them in-game!",
            view=None
        )


async def setup(bot: commands.Bot):
    """Load the StrikeCommands cog."""
    await bot.add_cog(StrikeCommands(bot))
