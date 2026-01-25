# cogs/player/linking.py
"""
Player ID Linking Commands (Passport System)

Allows users to link their Discord account to:
- Alderon ID (Path of Titans)
- Steam ID (The Isle and other games)
"""

import re
import discord
from discord import app_commands
from discord.ext import commands
from database.queries import PlayerQueries, GuildQueries, AuditQueries
from services.steam_api import SteamAPI, SteamAPIError
from services.permissions import require_permission
import logging

logger = logging.getLogger(__name__)


class PlayerLinking(commands.Cog):
    """Commands for linking Discord accounts to game IDs."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ==========================================
    # ALDERON ID LINKING
    # ==========================================

    @app_commands.command(
        name="alderonid",
        description="Link your Discord account to your Alderon ID"
    )
    @app_commands.guild_only()
    @app_commands.describe(
        playerid="Your Alderon ID in format XXX-XXX-XXX",
        playername="Your in-game player name"
    )
    async def link_alderon(self, interaction: discord.Interaction,
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
                    "This Alderon ID is already linked to another Discord user. "
                    "If this is your ID, please contact an admin.",
                    ephemeral=True
                )
                return

            # Check if user already has an Alderon ID linked (locked)
            current = PlayerQueries.get_by_user(interaction.guild_id, interaction.user.id)
            if current and current.get('player_id') and current['player_id'] != playerid:
                await interaction.response.send_message(
                    "You already have an Alderon ID linked to your account.\n"
                    "Your current ID is locked for security. To change it, please "
                    "contact an admin to unlock your account via `/unlinkid`.",
                    ephemeral=True
                )
                return

            # Link the player
            PlayerQueries.link_alderon(
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
                details={'player_id': playerid, 'player_name': playername, 'type': 'alderon'}
            )

            # Create success embed
            embed = discord.Embed(
                title="Alderon ID Linked",
                color=discord.Color.green()
            )
            embed.add_field(name="Discord User", value=interaction.user.mention, inline=True)
            embed.add_field(name="Alderon ID", value=f"`{playerid}`", inline=True)
            embed.add_field(name="Player Name", value=playername, inline=True)
            embed.set_footer(text="Your ID is now locked. Contact an admin to change it.")

            await interaction.response.send_message(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Error in /alderonid: {e}", exc_info=True)
            await interaction.response.send_message(
                "An error occurred while linking your player ID. Please try again later.",
                ephemeral=True
            )

    # ==========================================
    # STEAM ID LINKING
    # ==========================================

    @app_commands.command(
        name="linksteam",
        description="Link your Discord account to your Steam ID"
    )
    @app_commands.guild_only()
    @app_commands.describe(
        steam_id="Your Steam ID (17 digits), vanity URL, or profile link"
    )
    async def link_steam(self, interaction: discord.Interaction, steam_id: str):
        """Link Discord account to Steam ID."""

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

            # Check if Steam API is configured
            if not SteamAPI.is_configured():
                await interaction.response.send_message(
                    "Steam linking is not configured on this server. "
                    "Please contact the bot administrator.",
                    ephemeral=True
                )
                return

            # Check if user already has a Steam ID linked (locked)
            current = PlayerQueries.get_by_user(interaction.guild_id, interaction.user.id)
            if current and current.get('steam_id'):
                await interaction.response.send_message(
                    "You already have a Steam ID linked to your account.\n"
                    f"Your current Steam ID: `{current['steam_id']}`\n\n"
                    "Your ID is locked for security. To change it, please "
                    "contact an admin to unlock your account via `/unlinkid`.",
                    ephemeral=True
                )
                return

            # Defer response since Steam API call may take time
            await interaction.response.defer(ephemeral=True)

            # Validate and resolve Steam ID via API
            steam_data = await SteamAPI.validate_steam_id(steam_id)

            if not steam_data:
                await interaction.followup.send(
                    "Could not find a Steam account with that ID.\n"
                    "Please provide a valid:\n"
                    "- Steam ID (17 digits, e.g., `76561199003854357`)\n"
                    "- Vanity URL name (e.g., `gabelogannewell`)\n"
                    "- Profile URL (e.g., `https://steamcommunity.com/id/username`)",
                    ephemeral=True
                )
                return

            resolved_steam_id = steam_data['steam_id']
            steam_name = steam_data['personaname']

            # Check if this Steam ID is already linked to someone else
            existing = PlayerQueries.get_by_steam_id(interaction.guild_id, resolved_steam_id)
            if existing and existing['user_id'] != interaction.user.id:
                await interaction.followup.send(
                    "This Steam ID is already linked to another Discord user. "
                    "If this is your ID, please contact an admin.",
                    ephemeral=True
                )
                return

            # Link the Steam ID
            PlayerQueries.link_steam(
                guild_id=interaction.guild_id,
                user_id=interaction.user.id,
                username=str(interaction.user),
                steam_id=resolved_steam_id,
                steam_name=steam_name
            )

            # Log to audit
            AuditQueries.log(
                guild_id=interaction.guild_id,
                action_type=AuditQueries.ACTION_PLAYER_LINKED,
                performed_by_id=interaction.user.id,
                performed_by_name=str(interaction.user),
                target_user_id=interaction.user.id,
                details={'steam_id': resolved_steam_id, 'steam_name': steam_name, 'type': 'steam'}
            )

            # Create success embed
            embed = discord.Embed(
                title="Steam Account Linked",
                color=discord.Color.green()
            )
            embed.add_field(name="Discord User", value=interaction.user.mention, inline=True)
            embed.add_field(name="Steam Name", value=steam_name, inline=True)
            embed.add_field(name="Steam ID", value=f"`{resolved_steam_id}`", inline=True)

            if steam_data.get('avatarmedium'):
                embed.set_thumbnail(url=steam_data['avatarmedium'])

            embed.set_footer(text="Your ID is now locked. Contact an admin to change it.")

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Error in /linksteam: {e}", exc_info=True)
            if interaction.response.is_done():
                await interaction.followup.send(
                    "An error occurred while linking your Steam ID. Please try again later.",
                    ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    "An error occurred while linking your Steam ID. Please try again later.",
                    ephemeral=True
                )

    # ==========================================
    # ADMIN: UNLOCK ID
    # ==========================================

    @app_commands.command(
        name="unlinkid",
        description="[Admin] Unlock a user's linked ID so they can re-link"
    )
    @app_commands.guild_only()
    @app_commands.describe(
        user="The user whose ID to unlock",
        id_type="Which ID type to unlock"
    )
    @app_commands.choices(id_type=[
        app_commands.Choice(name="Steam ID", value="steam"),
        app_commands.Choice(name="Alderon ID", value="alderon"),
        app_commands.Choice(name="Both", value="both"),
    ])
    async def unlink_id(self, interaction: discord.Interaction,
                        user: discord.Member, id_type: str):
        """Admin command to unlock a user's linked ID."""

        # Check permission
        if not await require_permission(interaction, 'unlinkid'):
            return

        try:
            # Get current player data
            player = PlayerQueries.get_by_user(interaction.guild_id, user.id)

            if not player:
                await interaction.response.send_message(
                    f"{user.mention} doesn't have any linked IDs.",
                    ephemeral=True
                )
                return

            cleared = []

            if id_type in ('alderon', 'both'):
                if player.get('player_id'):
                    PlayerQueries.clear_alderon(interaction.guild_id, user.id)
                    cleared.append(f"Alderon ID: `{player['player_id']}`")

            if id_type in ('steam', 'both'):
                if player.get('steam_id'):
                    PlayerQueries.clear_steam(interaction.guild_id, user.id)
                    cleared.append(f"Steam ID: `{player['steam_id']}`")

            if not cleared:
                await interaction.response.send_message(
                    f"{user.mention} doesn't have a {id_type} ID linked.",
                    ephemeral=True
                )
                return

            # Log to audit
            AuditQueries.log(
                guild_id=interaction.guild_id,
                action_type=AuditQueries.ACTION_PLAYER_UNLINKED,
                performed_by_id=interaction.user.id,
                performed_by_name=str(interaction.user),
                target_user_id=user.id,
                details={'cleared': cleared, 'type': id_type}
            )

            embed = discord.Embed(
                title="ID Unlocked",
                description=f"The following ID(s) have been cleared for {user.mention}:",
                color=discord.Color.orange()
            )
            embed.add_field(name="Cleared", value="\n".join(cleared), inline=False)
            embed.set_footer(text=f"Unlocked by {interaction.user}")

            await interaction.response.send_message(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Error in /unlinkid: {e}", exc_info=True)
            await interaction.response.send_message(
                "An error occurred while unlinking the ID.",
                ephemeral=True
            )

    # ==========================================
    # LOOKUP COMMANDS
    # ==========================================

    @app_commands.command(
        name="playerid",
        description="Look up a player by Discord, Steam, or Alderon ID"
    )
    @app_commands.guild_only()
    @app_commands.describe(
        query="Discord username, Steam ID (17 digits), or Alderon ID (XXX-XXX-XXX)"
    )
    async def lookup_player(self, interaction: discord.Interaction, query: str):
        """Look up player info by any ID type."""

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

            player = None

            # Determine query type and search
            if re.match(r"^\d{3}-\d{3}-\d{3}$", query):
                # Alderon ID format
                player = PlayerQueries.get_by_player_id(interaction.guild_id, query)
            elif re.match(r"^\d{17}$", query):
                # Steam ID format (17 digits)
                player = PlayerQueries.get_by_steam_id(interaction.guild_id, query)
            else:
                # Try username
                player = PlayerQueries.get_by_username(interaction.guild_id, query)

            if not player:
                # Try search if exact match not found
                results = PlayerQueries.search(interaction.guild_id, query)
                if results:
                    if len(results) == 1:
                        # Single result - show full details like exact match
                        player = results[0]
                    else:
                        # Multiple results - show selection list
                        embed = discord.Embed(
                            title="Multiple Players Found",
                            description=f"Found {len(results)} matches for `{query}`.\nUse a specific ID for detailed info.",
                            color=discord.Color.blue()
                        )
                        for p in results[:5]:  # Show max 5
                            # Try to get Discord member
                            member = interaction.guild.get_member(p['user_id'])
                            display_name = member.display_name if member else p['username']

                            value_parts = []

                            # Discord info
                            if member:
                                value_parts.append(f"**Discord:** @{display_name} ({p['username']})")
                            else:
                                value_parts.append(f"**Discord:** {p['username']}")

                            # Alderon info
                            if p.get('player_id'):
                                alderon_name = p.get('player_name', 'Unknown')
                                value_parts.append(f"**Alderon:** {alderon_name} (`{p['player_id']}`)")

                            # Steam info
                            if p.get('steam_id'):
                                steam_name = p.get('steam_name', 'Unknown')
                                value_parts.append(f"**Steam:** {steam_name} (`{p['steam_id']}`)")

                            if not p.get('player_id') and not p.get('steam_id'):
                                value_parts.append("*No game IDs linked*")

                            # Use player_name, steam_name, or username as field title
                            field_name = p.get('player_name') or p.get('steam_name') or display_name
                            embed.add_field(
                                name=field_name,
                                value="\n".join(value_parts),
                                inline=False
                            )

                        embed.set_footer(text="Tip: Search by exact Steam ID (17 digits) or Alderon ID (XXX-XXX-XXX) for full details")
                        await interaction.response.send_message(embed=embed, ephemeral=True)
                        return
                else:
                    await interaction.response.send_message(
                        f"No player found matching `{query}`.",
                        ephemeral=True
                    )
                    return

            # Found exact match - build comprehensive embed
            embed = discord.Embed(
                title="Player Information",
                color=discord.Color.blue()
            )

            # Try to get Discord member for avatar and display name
            member = interaction.guild.get_member(player['user_id'])
            if member:
                embed.set_thumbnail(url=member.display_avatar.url)
                discord_value = f"@{member.display_name} ({player['username']})"
            else:
                discord_value = f"{player['username']} *(not in server)*"

            # Discord info
            embed.add_field(
                name="Discord",
                value=discord_value,
                inline=False
            )

            has_ids = False
            steam_avatar_url = None

            # Steam info
            if player.get('steam_id'):
                has_ids = True
                # Try to get Steam avatar
                if SteamAPI.is_configured():
                    try:
                        steam_data = await SteamAPI.get_player_summary(player['steam_id'])
                        if steam_data and steam_data.get('avatarmedium'):
                            steam_avatar_url = steam_data['avatarmedium']
                    except Exception:
                        pass

                steam_value = f"**Steam Name:** {player.get('steam_name', 'Unknown')}\n**Steam ID:** `{player['steam_id']}`"
                if steam_avatar_url:
                    steam_value += f"\n[View Profile](https://steamcommunity.com/profiles/{player['steam_id']})"
                embed.add_field(
                    name="Steam",
                    value=steam_value,
                    inline=False
                )

            # Alderon info
            if player.get('player_id'):
                has_ids = True
                embed.add_field(
                    name="Alderon",
                    value=f"**Player Name:** {player['player_name']}\n**Alderon ID:** `{player['player_id']}`",
                    inline=False
                )

            if not has_ids:
                embed.add_field(
                    name="Game IDs",
                    value="No game IDs linked",
                    inline=False
                )

            # Show Steam avatar at bottom if available
            if steam_avatar_url:
                embed.set_image(url=steam_avatar_url)

            # Footer with ID lock info
            if has_ids:
                embed.set_footer(text="IDs are locked. Use /unlinkid to allow changes.")

            await interaction.response.send_message(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Error in /playerid: {e}", exc_info=True)
            await interaction.response.send_message(
                "An error occurred while looking up player info.",
                ephemeral=True
            )

    @app_commands.command(
        name="myid",
        description="View your linked accounts"
    )
    @app_commands.guild_only()
    async def my_id(self, interaction: discord.Interaction):
        """View your own linked player info."""

        try:
            GuildQueries.get_or_create(interaction.guild_id, interaction.guild.name)

            player = PlayerQueries.get_by_user(interaction.guild_id, interaction.user.id)

            embed = discord.Embed(
                title="Your Linked Accounts",
                color=discord.Color.green()
            )

            # Set Discord avatar as main thumbnail
            embed.set_thumbnail(url=interaction.user.display_avatar.url)

            # Discord - always show
            # Get display name and username (username already includes dots if present)
            display_name = interaction.user.display_name
            username = interaction.user.name
            embed.add_field(
                name="Discord",
                value=f"@{display_name} ({username})",
                inline=False
            )

            has_ids = False
            steam_avatar_url = None

            # Steam info
            if player and player.get('steam_id'):
                has_ids = True
                # Fetch Steam avatar if we have the API configured
                if SteamAPI.is_configured():
                    try:
                        steam_data = await SteamAPI.get_player_summary(player['steam_id'])
                        if steam_data and steam_data.get('avatarmedium'):
                            steam_avatar_url = steam_data['avatarmedium']
                    except Exception:
                        pass  # Don't fail if we can't get avatar

                steam_value = f"**Steam Name:** {player.get('steam_name', 'Unknown')}\n**Steam ID:** `{player['steam_id']}`"
                if steam_avatar_url:
                    steam_value += f"\n[View Profile](https://steamcommunity.com/profiles/{player['steam_id']})"
                embed.add_field(
                    name="Steam",
                    value=steam_value,
                    inline=False
                )
            else:
                embed.add_field(
                    name="Steam",
                    value="Not linked\nUse `/linksteam` to link",
                    inline=False
                )

            # Alderon info
            if player and player.get('player_id'):
                has_ids = True
                embed.add_field(
                    name="Alderon",
                    value=f"**Player Name:** {player['player_name']}\n"
                          f"**Alderon ID:** `{player['player_id']}`",
                    inline=False
                )
            else:
                embed.add_field(
                    name="Alderon",
                    value="Not linked\nUse `/alderonid` to link",
                    inline=False
                )

            # Set Steam avatar as image if available (shows at bottom)
            if steam_avatar_url:
                embed.set_image(url=steam_avatar_url)

            if has_ids:
                embed.set_footer(text="IDs are locked. Contact an admin to change them.")
            else:
                embed.set_footer(text="Link your game accounts to get started!")

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
