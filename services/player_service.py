# services/player_service.py
"""
Player Service - Core player linking/lookup logic
Shared between slash commands and panel commands.
"""

import discord
import logging
from database.queries import PlayerQueries, GuildQueries

logger = logging.getLogger(__name__)


async def link_alderon_id(interaction: discord.Interaction, player_id: str, player_name: str):
    """Link a user's Alderon ID."""
    try:
        guild_id = interaction.guild_id
        user_id = interaction.user.id

        # Check if already linked
        existing_player = PlayerQueries.get_by_user(guild_id, user_id)
        if existing_player and existing_player.get('alderon_id'):
            await interaction.response.send_message(
                f"You already have an Alderon ID linked: `{existing_player['alderon_id']}`\n"
                "Contact an admin if you need to change it.",
                ephemeral=True
            )
            return

        # Link the ID
        PlayerQueries.link_alderon(guild_id, user_id, player_id, player_name)

        embed = discord.Embed(
            title="✅ Alderon ID Linked",
            description=f"Your Alderon ID has been linked successfully!",
            color=discord.Color.green()
        )
        embed.add_field(name="Alderon ID", value=f"`{player_id}`", inline=True)
        embed.add_field(name="Player Name", value=player_name, inline=True)
        embed.set_footer(text="Your ID is now locked. Contact an admin to change it.")

        await interaction.response.send_message(embed=embed, ephemeral=True)

    except Exception as e:
        logger.error(f"Error linking Alderon ID: {e}", exc_info=True)
        await interaction.response.send_message(
            "An error occurred while linking your Alderon ID.",
            ephemeral=True
        )


async def link_steam_id(interaction: discord.Interaction, steam_id: str):
    """Link a user's Steam ID."""
    try:
        guild_id = interaction.guild_id
        user_id = interaction.user.id

        # Check if already linked
        existing_player = PlayerQueries.get_by_user(guild_id, user_id)
        if existing_player and existing_player.get('steam_id'):
            await interaction.response.send_message(
                f"You already have a Steam ID linked: `{existing_player['steam_id']}`\n"
                "Contact an admin if you need to change it.",
                ephemeral=True
            )
            return

        # Parse Steam ID (handle URLs and raw IDs)
        parsed_steam_id = _parse_steam_id(steam_id)
        if not parsed_steam_id:
            await interaction.response.send_message(
                "❌ Invalid Steam ID format. Please provide a valid Steam ID or profile URL.",
                ephemeral=True
            )
            return

        # Link the ID
        PlayerQueries.link_steam(guild_id, user_id, parsed_steam_id)

        embed = discord.Embed(
            title="✅ Steam ID Linked",
            description=f"Your Steam ID has been linked successfully!",
            color=discord.Color.green()
        )
        embed.add_field(name="Steam ID", value=f"`{parsed_steam_id}`", inline=True)
        embed.set_footer(text="Your ID is now locked. Contact an admin to change it.")

        await interaction.response.send_message(embed=embed, ephemeral=True)

    except Exception as e:
        logger.error(f"Error linking Steam ID: {e}", exc_info=True)
        await interaction.response.send_message(
            "An error occurred while linking your Steam ID.",
            ephemeral=True
        )


async def lookup_player(interaction: discord.Interaction, query: str):
    """Look up a player by Discord username/mention, Steam ID, or Alderon ID."""
    try:
        guild_id = interaction.guild_id

        # Try to parse as Discord user
        user = None
        if query.startswith('<@') and query.endswith('>'):
            # Discord mention
            user_id = int(query[2:-1].replace('!', ''))
            try:
                user = await interaction.client.fetch_user(user_id)
            except:
                pass
        elif query.isdigit():
            # Discord ID
            try:
                user = await interaction.client.fetch_user(int(query))
            except:
                pass
        else:
            # Search guild members by username/display name
            guild = interaction.guild
            if guild:
                query_lower = query.lower()
                for member in guild.members:
                    # Check username, display name, and global name
                    if (member.name.lower() == query_lower or
                        member.display_name.lower() == query_lower or
                        (member.global_name and member.global_name.lower() == query_lower)):
                        user = member
                        break
                    # Also check for partial matches
                    if (query_lower in member.name.lower() or
                        query_lower in member.display_name.lower() or
                        (member.global_name and query_lower in member.global_name.lower())):
                        user = member
                        break

        # Search database
        player = None
        if user:
            player = PlayerQueries.get_by_user(guild_id, user.id)
        else:
            # Try as Steam ID or Alderon ID
            player = PlayerQueries.get_by_player_id(guild_id, query)

        # If no player record but we found a Discord user, that's still valid
        # (user exists in Discord but hasn't linked IDs yet)
        if not player and not user:
            await interaction.response.send_message(
                f"No player found matching: `{query}`",
                ephemeral=True
            )
            return

        # Build detailed result embed (matching "View My IDs" format)
        embed = discord.Embed(
            title="Player Lookup Results",
            color=discord.Color.blue()
        )

        # Get Discord user for display
        discord_user = user  # Use the user we already found
        if not discord_user and player and player.get('user_id'):
            # Fallback: get user from player record
            try:
                discord_user = await interaction.client.fetch_user(player['user_id'])
            except:
                pass

        # Set Discord avatar as thumbnail
        if discord_user:
            embed.set_thumbnail(url=discord_user.display_avatar.url)

        has_ids = False
        steam_avatar_url = None

        # Discord info with verification status
        if discord_user:
            discord_verified = "✅" if player and player.get('discord_verified') else ""
            embed.add_field(
                name=f"Discord {discord_verified}",
                value=f"{discord_user.mention}\n**Username:** @{discord_user.name}\n**Discord ID:** `{discord_user.id}`",
                inline=False
            )
        elif player and player.get('user_id'):
            # Fallback if user not found
            embed.add_field(
                name="Discord",
                value=f"**Discord ID:** `{player['user_id']}`",
                inline=False
            )

        # Steam info with verification status
        if player and player.get('steam_id'):
            has_ids = True
            # Try to fetch Steam avatar if API is configured
            try:
                from services.steam_api import SteamAPI
                if SteamAPI.is_configured():
                    steam_data = await SteamAPI.get_player_summary(player['steam_id'])
                    if steam_data and steam_data.get('avatarmedium'):
                        steam_avatar_url = steam_data['avatarmedium']
            except Exception:
                pass  # Don't fail if we can't get avatar

            steam_verified = "✅" if player.get('steam_verified') else ""
            steam_value = f"**Steam Name:** {player.get('steam_name', 'Unknown')}\n**Steam ID:** `{player['steam_id']}`"
            if steam_avatar_url:
                steam_value += f"\n[View Profile](https://steamcommunity.com/profiles/{player['steam_id']})"
            embed.add_field(
                name=f"Steam {steam_verified}",
                value=steam_value,
                inline=False
            )
        else:
            embed.add_field(
                name="Steam",
                value="*Not linked*",
                inline=False
            )

        # Alderon info with verification status
        if player and player.get('player_id'):
            has_ids = True
            alderon_verified = "✅" if player.get('alderon_verified') else ""
            embed.add_field(
                name=f"Alderon {alderon_verified}",
                value=f"**Player Name:** {player.get('player_name', 'Unknown')}\n**Alderon ID:** `{player['player_id']}`",
                inline=False
            )
        else:
            embed.add_field(
                name="Alderon",
                value="*Not linked*",
                inline=False
            )

        # Set Steam avatar as image if available (shows at bottom)
        if steam_avatar_url:
            embed.set_image(url=steam_avatar_url)

        # Footer based on link status
        if has_ids:
            embed.set_footer(text="Player information • IDs are locked")
        else:
            embed.set_footer(text="Player information • No IDs linked")

        await interaction.response.send_message(embed=embed, ephemeral=True)

    except Exception as e:
        logger.error(f"Error looking up player: {e}", exc_info=True)
        await interaction.response.send_message(
            "An error occurred while looking up the player.",
            ephemeral=True
        )


async def unlink_player_id(interaction: discord.Interaction, user: discord.User, id_type: str = "both"):
    """Unlink a player's Steam or Alderon ID (admin only)."""
    try:
        guild_id = interaction.guild_id

        # Get player
        player = PlayerQueries.get_by_user(guild_id, user.id)
        if not player:
            await interaction.response.send_message(
                f"{user.mention} has no linked IDs.",
                ephemeral=True
            )
            return

        # Unlink based on type
        if id_type == "steam":
            PlayerQueries.unlink_steam(guild_id, user.id)
            unlinked = "Steam ID"
        elif id_type == "alderon":
            PlayerQueries.unlink_alderon(guild_id, user.id)
            unlinked = "Alderon ID"
        else:  # both
            PlayerQueries.unlink_steam(guild_id, user.id)
            PlayerQueries.unlink_alderon(guild_id, user.id)
            unlinked = "Steam ID and Alderon ID"

        embed = discord.Embed(
            title="✅ Player Unlinked",
            description=f"Unlinked {unlinked} for {user.mention}",
            color=discord.Color.green()
        )
        embed.add_field(name="Unlinked by", value=interaction.user.mention, inline=True)

        await interaction.response.send_message(embed=embed)

    except Exception as e:
        logger.error(f"Error unlinking player: {e}", exc_info=True)
        await interaction.response.send_message(
            "An error occurred while unlinking the player.",
            ephemeral=True
        )


def _parse_steam_id(steam_input: str) -> str | None:
    """Parse Steam ID from various formats."""
    steam_input = steam_input.strip()

    # Already a 17-digit Steam ID
    if steam_input.isdigit() and len(steam_input) == 17:
        return steam_input

    # Steam profile URL
    if "steamcommunity.com" in steam_input:
        # Extract ID from URL
        parts = steam_input.rstrip('/').split('/')
        if len(parts) > 0:
            potential_id = parts[-1]
            if potential_id.isdigit() and len(potential_id) == 17:
                return potential_id

    return None
