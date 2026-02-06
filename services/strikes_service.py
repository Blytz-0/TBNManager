# services/strikes_service.py
"""
Strikes Service - Core strike/ban processing logic
Shared between slash commands and panel commands.
"""

import discord
import logging
from database.queries import StrikeQueries, PlayerQueries, AuditQueries, GuildQueries

logger = logging.getLogger(__name__)


async def process_strike(interaction: discord.Interaction,
                        player_name: str, in_game_id: str, reason: str):
    """
    Process a strike after modal submission.

    Shared logic for both slash commands and panel commands.
    Returns: (success: bool, embed: discord.Embed | None, auto_ban_needed: bool, strike_data: dict)
    """
    try:
        guild_id = interaction.guild_id

        # Check if player is already banned
        if StrikeQueries.is_banned(guild_id, in_game_id):
            return (False, None, False, {
                'error': f"**{player_name}** (`{in_game_id}`) is already banned and cannot receive more strikes."
            })

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

        # Check if auto-ban needed (3rd strike)
        auto_ban_needed = (
            strike_number >= 3 and
            GuildQueries.is_feature_enabled(guild_id, 'auto_ban')
        )

        # DM the user if linked and feature enabled
        if user_id and GuildQueries.is_feature_enabled(guild_id, 'dm_notifications'):
            await send_strike_notification(
                interaction.guild, user_id, strike_number, reason,
                admin_name=str(interaction.user), in_game_id=in_game_id,
                reference_id=strike.get('reference_id')
            )

        return (True, embed, auto_ban_needed, {
            'strike_number': strike_number,
            'player_name': player_name,
            'in_game_id': in_game_id,
            'user_id': user_id,
            'reference_id': strike.get('reference_id')
        })

    except Exception as e:
        logger.error(f"Error processing strike: {e}", exc_info=True)
        return (False, None, False, {
            'error': "An error occurred while adding the strike. Please try again."
        })


async def send_strike_notification(guild: discord.Guild, user_id: int,
                                   strike_number: int, reason: str,
                                   admin_name: str = None, in_game_id: str = None,
                                   reference_id: str = None,
                                   steam_id: str = None, alderon_id: str = None):
    """Send DM notification to user about strike."""
    try:
        member = guild.get_member(user_id)
        if not member:
            return

        from datetime import datetime, timedelta
        import time

        now = datetime.now()
        expiry_date = now + timedelta(days=30 * strike_number)

        # Unix timestamps for Discord formatting
        now_timestamp = int(time.time())
        expiry_timestamp = int(expiry_date.timestamp())

        # Color based on strike number
        if strike_number == 1:
            color = discord.Color.yellow()
        elif strike_number == 2:
            color = discord.Color.orange()
        else:
            color = discord.Color.red()

        embed = discord.Embed(
            title=f"⚠️ Strike #{strike_number} Issued",
            description=f"You have received a strike on **{guild.name}**",
            color=color,
            timestamp=now
        )

        # Strike details
        embed.add_field(name="Reason", value=reason, inline=False)
        embed.add_field(name="Issued On", value=f"<t:{now_timestamp}:F>", inline=True)
        embed.add_field(name="Issued By", value=admin_name or "Staff", inline=True)

        # Show all linked IDs
        if steam_id or alderon_id:
            ids_text = []
            if alderon_id:
                ids_text.append(f"**Alderon:** `{alderon_id}`")
            if steam_id:
                ids_text.append(f"**Steam:** `{steam_id}`")
            if user_id:
                ids_text.append(f"**Discord:** `{user_id}`")

            embed.add_field(
                name="Player IDs",
                value="\n".join(ids_text),
                inline=False
            )

        # Reference ID for appeals
        if reference_id:
            embed.add_field(name="Reference ID", value=f"`{reference_id}`", inline=True)

        # Expiry info with Discord timestamp
        embed.add_field(
            name="Strike Expiry",
            value=f"This strike will automatically expire on <t:{expiry_timestamp}:D> "
                  f"(<t:{expiry_timestamp}:R>) if no further strikes are issued.",
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


def check_direct_ban_eligibility(guild_id: int, in_game_id: str, player_name: str):
    """
    Check if a player can be directly banned.
    Returns: (can_ban: bool, error_message: str | None, user_id: int | None)
    """
    # Check if player is already banned
    if StrikeQueries.is_banned(guild_id, in_game_id):
        return (False, f"**{player_name}** (`{in_game_id}`) is already banned.", None)

    # Get linked Discord user if exists
    linked_player = PlayerQueries.get_by_player_id(guild_id, in_game_id)
    user_id = linked_player['user_id'] if linked_player else None

    return (True, None, user_id)


async def send_direct_ban_notification(guild: discord.Guild, user_id: int,
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
            appeal_text += f"\n**To appeal:** Open a ticket in the server and provide your Reference ID: `{reference_id}`"
        embed.add_field(
            name="📌 Appeals",
            value=appeal_text,
            inline=False
        )

        embed.set_footer(text=f"{guild.name} • Moderation System")
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)

        await member.send(embed=embed)

    except discord.Forbidden:
        logger.warning(f"Could not DM user {user_id} about ban")
    except Exception as e:
        logger.error(f"Error sending ban notification: {e}")


# ==========================================
# VIEW/QUERY FUNCTIONS
# ==========================================

async def view_strikes(interaction: discord.Interaction, in_game_id: str):
    """View active strikes for a player."""
    try:
        guild_id = interaction.guild_id

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
                value="This player has no active strikes.\nUse Strike History to view past strikes.",
                inline=False
            )
        else:
            from datetime import datetime, timedelta
            for i, strike in enumerate(active_strikes, 1):
                # created_at is already a datetime object from database
                issued_date = strike['created_at']
                if isinstance(issued_date, str):
                    issued_date = datetime.fromisoformat(issued_date)
                expiry_date = issued_date + timedelta(days=30 * i)
                days_until_expiry = (expiry_date - datetime.now()).days

                embed.add_field(
                    name=f"Strike #{i}",
                    value=f"**Reason:** {strike['reason']}\n"
                          f"**Issued:** {issued_date.strftime('%Y-%m-%d')}\n"
                          f"**Expires in:** {days_until_expiry} days\n"
                          f"**Issued by:** {strike['admin_name']}",
                    inline=False
                )

            if expiry_info and expiry_info.get('next_expiry_date'):
                embed.set_footer(text=f"Next strike expires: {expiry_info['next_expiry_date']}")

        # Use followup if interaction already responded to (from modal defer), otherwise use response
        if interaction.response.is_done():
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message(embed=embed, ephemeral=True)

    except Exception as e:
        logger.error(f"Error viewing strikes: {e}", exc_info=True)
        if interaction.response.is_done():
            await interaction.followup.send(
                "An error occurred while retrieving strikes.",
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                "An error occurred while retrieving strikes.",
                ephemeral=True
            )


async def strike_history(interaction: discord.Interaction, in_game_id: str):
    """View full strike history for a player."""
    try:
        guild_id = interaction.guild_id

        # Get all strikes (active and expired)
        all_strikes = StrikeQueries.get_player_strikes(guild_id, in_game_id)

        if not all_strikes:
            await interaction.response.send_message(
                f"No strike history found for player with ID `{in_game_id}`.",
                ephemeral=True
            )
            return

        player_name = all_strikes[-1]['player_name']
        active_strikes = StrikeQueries.get_active_strikes(guild_id, in_game_id)
        active_count = len(active_strikes)

        embed = discord.Embed(
            title=f"Strike History for {player_name}",
            description=f"Alderon ID: `{in_game_id}`\n"
                       f"Active: **{active_count}** | Total: **{len(all_strikes)}**",
            color=discord.Color.blue()
        )

        # Show up to 10 most recent strikes
        for strike in all_strikes[-10:]:
            from datetime import datetime
            # created_at is already a datetime object from database
            issued_date = strike['created_at']
            if isinstance(issued_date, str):
                issued_date = datetime.fromisoformat(issued_date)

            # Determine status
            is_active = strike['is_active']
            status = "🟢 Active" if is_active else "⚫ Expired/Removed"

            # Build strike value with removal info if applicable
            strike_value = f"{status}\n**Reason:** {strike['reason']}\n**Issued By:** {strike['admin_name']}"

            # Add removal information if removed
            if not is_active and strike.get('removed_by_name'):
                strike_value += f"\n**Removed By:** {strike['removed_by_name']}"
                if strike.get('expired_at'):
                    removed_date = strike['expired_at']
                    if isinstance(removed_date, str):
                        removed_date = datetime.fromisoformat(removed_date)
                    strike_value += f" on {removed_date.strftime('%Y-%m-%d')}"

            embed.add_field(
                name=f"Strike - {issued_date.strftime('%Y-%m-%d')}",
                value=strike_value,
                inline=False
            )

        if len(all_strikes) > 10:
            embed.set_footer(text=f"Showing 10 of {len(all_strikes)} strikes")

        # Use followup if interaction already responded to, otherwise use response
        if interaction.response.is_done():
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message(embed=embed, ephemeral=True)

    except Exception as e:
        logger.error(f"Error viewing strike history: {e}", exc_info=True)
        if interaction.response.is_done():
            await interaction.followup.send(
                "An error occurred while retrieving strike history.",
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                "An error occurred while retrieving strike history.",
                ephemeral=True
            )


async def remove_strike(interaction: discord.Interaction, in_game_id: str, strike_number: int = None):
    """Remove a strike from a player."""
    try:
        guild_id = interaction.guild_id

        # Get active strikes
        active_strikes = StrikeQueries.get_active_strikes(guild_id, in_game_id)

        if not active_strikes:
            await interaction.response.send_message(
                f"No active strikes found for player with ID `{in_game_id}`.",
                ephemeral=True
            )
            return

        player_name = active_strikes[0]['player_name']

        # If strike_number not specified, remove most recent
        if strike_number is None:
            strike_to_remove = active_strikes[-1]
        else:
            if strike_number < 1 or strike_number > len(active_strikes):
                await interaction.response.send_message(
                    f"Invalid strike number. Player has {len(active_strikes)} active strike(s).",
                    ephemeral=True
                )
                return
            strike_to_remove = active_strikes[strike_number - 1]

        # Remove the strike
        StrikeQueries.remove_strike(
            strike_to_remove['id'],
            interaction.user.id,
            str(interaction.user)
        )

        # Log to audit
        AuditQueries.log(
            guild_id=guild_id,
            action_type=AuditQueries.ACTION_STRIKE_REMOVED,
            performed_by_id=interaction.user.id,
            performed_by_name=str(interaction.user),
            target_player_name=player_name,
            details={'in_game_id': in_game_id, 'removed_strike_id': strike_to_remove['id']}
        )

        embed = discord.Embed(
            title="Strike Removed",
            description=f"Removed strike from **{player_name}** (`{in_game_id}`)",
            color=discord.Color.green()
        )
        embed.add_field(name="Reason (removed strike)", value=strike_to_remove['reason'], inline=False)
        embed.add_field(name="Removed by", value=interaction.user.mention, inline=True)

        if interaction.response.is_done():
            await interaction.followup.send(embed=embed)
        else:
            await interaction.response.send_message(embed=embed)

    except Exception as e:
        logger.error(f"Error removing strike: {e}", exc_info=True)
        if interaction.response.is_done():
            await interaction.followup.send(
                "An error occurred while removing the strike.",
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                "An error occurred while removing the strike.",
                ephemeral=True
            )


async def clear_strikes(interaction: discord.Interaction, in_game_id: str):
    """Clear all active strikes for a player."""
    try:
        guild_id = interaction.guild_id

        # Get active strikes
        active_strikes = StrikeQueries.get_active_strikes(guild_id, in_game_id)

        if not active_strikes:
            await interaction.response.send_message(
                f"No active strikes found for player with ID `{in_game_id}`.",
                ephemeral=True
            )
            return

        player_name = active_strikes[0]['player_name']
        count = len(active_strikes)

        # Clear all strikes
        StrikeQueries.clear_strikes(
            guild_id,
            in_game_id,
            interaction.user.id,
            str(interaction.user)
        )

        # Log to audit
        AuditQueries.log(
            guild_id=guild_id,
            action_type=AuditQueries.ACTION_STRIKES_CLEARED,
            performed_by_id=interaction.user.id,
            performed_by_name=str(interaction.user),
            target_player_name=player_name,
            details={'in_game_id': in_game_id, 'cleared_count': count}
        )

        embed = discord.Embed(
            title="Strikes Cleared",
            description=f"Cleared **{count}** active strike(s) for **{player_name}** (`{in_game_id}`)",
            color=discord.Color.green()
        )
        embed.add_field(name="Cleared by", value=interaction.user.mention, inline=True)

        if interaction.response.is_done():
            await interaction.followup.send(embed=embed)
        else:
            await interaction.response.send_message(embed=embed)

    except Exception as e:
        logger.error(f"Error clearing strikes: {e}", exc_info=True)
        if interaction.response.is_done():
            await interaction.followup.send(
                "An error occurred while clearing strikes.",
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                "An error occurred while clearing strikes.",
                ephemeral=True
            )


async def unban_player(interaction: discord.Interaction, in_game_id: str):
    """Unban a player."""
    try:
        guild_id = interaction.guild_id

        # Check if player is banned
        if not StrikeQueries.is_banned(guild_id, in_game_id):
            await interaction.response.send_message(
                f"Player with ID `{in_game_id}` is not currently banned.",
                ephemeral=True
            )
            return

        # Get ban info
        ban_info = StrikeQueries.get_ban(guild_id, in_game_id)
        player_name = ban_info['player_name'] if ban_info else "Unknown"

        # Unban the player
        StrikeQueries.unban_player(guild_id, in_game_id)

        # Log to audit
        AuditQueries.log(
            guild_id=guild_id,
            action_type=AuditQueries.ACTION_UNBAN,
            performed_by_id=interaction.user.id,
            performed_by_name=str(interaction.user),
            target_player_name=player_name,
            details={'in_game_id': in_game_id}
        )

        embed = discord.Embed(
            title="Player Unbanned",
            description=f"**{player_name}** (`{in_game_id}`) has been unbanned.",
            color=discord.Color.green()
        )
        embed.add_field(name="Unbanned by", value=interaction.user.mention, inline=True)

        if interaction.response.is_done():
            await interaction.followup.send(embed=embed)
        else:
            await interaction.response.send_message(embed=embed)

    except Exception as e:
        logger.error(f"Error unbanning player: {e}", exc_info=True)
        if interaction.response.is_done():
            await interaction.followup.send(
                "An error occurred while unbanning the player.",
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                "An error occurred while unbanning the player.",
                ephemeral=True
            )


async def list_bans(interaction: discord.Interaction, show_unbanned: bool = False):
    """List all banned players."""
    try:
        guild_id = interaction.guild_id

        # Get bans
        bans = StrikeQueries.get_all_bans(guild_id, include_unbanned=show_unbanned)

        if not bans:
            await interaction.response.send_message(
                "No banned players found." if not show_unbanned else "No ban records found.",
                ephemeral=True
            )
            return

        embed = discord.Embed(
            title="Banned Players" if not show_unbanned else "Ban History",
            description=f"Total: **{len(bans)}** player(s)",
            color=discord.Color.red()
        )

        # Show up to 15 bans
        for ban in bans[:15]:
            from datetime import datetime
            # created_at is already a datetime object from database
            banned_date = ban['created_at']
            if isinstance(banned_date, str):
                banned_date = datetime.fromisoformat(banned_date)
            status = "🔴 Banned" if ban['active'] else "🟢 Unbanned"

            embed.add_field(
                name=f"{ban['player_name']} - {status}",
                value=f"**ID:** `{ban['in_game_id']}`\n"
                      f"**Reason:** {ban['reason']}\n"
                      f"**Date:** {banned_date.strftime('%Y-%m-%d')}\n"
                      f"**By:** {ban['banned_by_name']}",
                inline=False
            )

        if len(bans) > 15:
            embed.set_footer(text=f"Showing 15 of {len(bans)} bans")

        await interaction.response.send_message(embed=embed)

    except Exception as e:
        logger.error(f"Error listing bans: {e}", exc_info=True)
        await interaction.response.send_message(
            "An error occurred while retrieving bans.",
            ephemeral=True
        )


async def recent_strikes(interaction: discord.Interaction):
    """View recent strikes in the server (including removed ones)."""
    try:
        guild_id = interaction.guild_id

        # Get recent strikes (last 15, including removed ones)
        recent = StrikeQueries.get_recent_strikes(guild_id, limit=15)

        if not recent:
            await interaction.response.send_message(
                "No strikes found in this server.",
                ephemeral=True
            )
            return

        embed = discord.Embed(
            title="📋 Recent Strikes",
            description=f"Last {len(recent)} strike(s) issued in this server (including removed)",
            color=discord.Color.orange()
        )

        for strike in recent:
            from datetime import datetime
            from database.queries.players import PlayerQueries

            # created_at is already a datetime object from database
            issued_date = strike['created_at']
            if isinstance(issued_date, str):
                issued_date = datetime.fromisoformat(issued_date)

            # Convert to Unix timestamp for Discord format
            timestamp = int(issued_date.timestamp())

            # Get all linked IDs for this player
            linked_accounts = PlayerQueries.get_by_user(guild_id, strike['user_id'])

            # Build ID display with all linked accounts
            ids_display = []
            if linked_accounts:
                if linked_accounts.get('alderon_id'):
                    ids_display.append(f"🎮 Alderon: `{linked_accounts['alderon_id']}`")
                if linked_accounts.get('steam_id'):
                    ids_display.append(f"🔷 Steam: `{linked_accounts['steam_id']}`")
                ids_display.append(f"💬 Discord: <@{strike['user_id']}>")
            else:
                # Fallback to in_game_id if no linked accounts found
                ids_display.append(f"🎮 ID: `{strike['in_game_id']}`")

            # Determine if strike is removed
            is_removed = not strike['is_active']

            # Build strike field value
            ids_text = ' • '.join(ids_display)
            reason_text = strike['reason']

            # Apply strikethrough if removed
            if is_removed:
                ids_text = f"~~{ids_text}~~"
                reason_text = f"~~{reason_text}~~"

            field_value = (
                f"{ids_text}\n"
                f"**Reason:** {reason_text}\n"
                f"**Issued:** <t:{timestamp}:F> (<t:{timestamp}:R>)\n"
                f"**By:** {strike['admin_name']}"
            )

            # Add category and severity if available
            if strike.get('category'):
                category_text = strike['category']
                if is_removed:
                    category_text = f"~~{category_text}~~"
                field_value += f"\n**Category:** {category_text}"
            if strike.get('severity'):
                severity_text = strike['severity']
                if is_removed:
                    severity_text = f"~~{severity_text}~~"
                field_value += f"\n**Severity:** {severity_text}"

            # Show removal info if removed
            if is_removed:
                if strike.get('removed_by_name'):
                    field_value += f"\n🗑️ **Removed by:** {strike['removed_by_name']}"
                if strike.get('expired_at'):
                    removed_date = strike['expired_at']
                    if isinstance(removed_date, str):
                        removed_date = datetime.fromisoformat(removed_date)
                    removed_timestamp = int(removed_date.timestamp())
                    field_value += f" on <t:{removed_timestamp}:D>"

            # Add status emoji to title
            status_emoji = "❌" if is_removed else "⚠️"
            status_text = " (REMOVED)" if is_removed else ""

            embed.add_field(
                name=f"{status_emoji} {strike['player_name']} - Strike #{strike['strike_number']}{status_text}",
                value=field_value,
                inline=False
            )

        embed.set_footer(text="💡 Strikethrough = removed | Hover over timestamps for full date/time")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    except Exception as e:
        logger.error(f"Error viewing recent strikes: {e}", exc_info=True)
        await interaction.response.send_message(
            "An error occurred while retrieving recent strikes.",
            ephemeral=True
        )


async def wipe_history(interaction: discord.Interaction, in_game_id: str):
    """Wipe all history for a player (requires confirmation)."""
    try:
        guild_id = interaction.guild_id

        # Get player info
        all_strikes = StrikeQueries.get_player_strikes(guild_id, in_game_id)
        ban_info = StrikeQueries.get_ban(guild_id, in_game_id)

        if not all_strikes and not ban_info:
            await interaction.response.send_message(
                f"No records found for player with ID `{in_game_id}`.",
                ephemeral=True
            )
            return

        player_name = all_strikes[-1]['player_name'] if all_strikes else (ban_info['player_name'] if ban_info else "Unknown")
        strike_count = len(all_strikes)
        has_ban = ban_info is not None

        # Show confirmation modal
        from . import WipeHistoryConfirmModal
        modal = WipeHistoryConfirmModal(guild_id, player_name, in_game_id, strike_count, has_ban)
        await interaction.response.send_modal(modal)

    except Exception as e:
        logger.error(f"Error initiating wipe: {e}", exc_info=True)
        await interaction.response.send_message(
            "An error occurred.",
            ephemeral=True
        )


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

        try:
            # Wipe all records
            StrikeQueries.wipe_player_history(self.guild_id, self.in_game_id)

            # Log to audit
            AuditQueries.log(
                guild_id=self.guild_id,
                action_type=AuditQueries.ACTION_HISTORY_WIPED,
                performed_by_id=interaction.user.id,
                performed_by_name=str(interaction.user),
                target_player_name=self.player_name,
                details={
                    'in_game_id': self.in_game_id,
                    'strikes_wiped': self.strike_count,
                    'ban_wiped': self.has_ban
                }
            )

            ban_text = f" and ban record" if self.has_ban else ""
            embed = discord.Embed(
                title="History Wiped",
                description=f"Permanently deleted **{self.strike_count}** strike(s){ban_text} for "
                           f"**{self.player_name}** (`{self.in_game_id}`)",
                color=discord.Color.dark_gray()
            )
            embed.add_field(name="Wiped by", value=interaction.user.mention, inline=True)
            embed.set_footer(text="This action cannot be undone")

            await interaction.response.send_message(embed=embed)

        except Exception as e:
            logger.error(f"Error wiping history: {e}", exc_info=True)
            await interaction.response.send_message(
                "An error occurred while wiping history.",
                ephemeral=True
            )
