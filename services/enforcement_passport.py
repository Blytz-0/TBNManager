# services/enforcement_passport.py
"""
Enforcement Passport Helper - Link enforcement actions to player passports

Provides passport-aware player lookup for the enforcement system.
Searches by any linked identifier (Discord, Steam, Alderon) and returns
complete passport information for global enforcement.
"""

import discord
import logging
from database.queries import PlayerQueries

logger = logging.getLogger(__name__)


async def lookup_player_for_enforcement(interaction: discord.Interaction, query: str):
    """
    Look up a player by any identifier for enforcement actions.

    Args:
        interaction: Discord interaction
        query: Search query (Discord username/mention/ID, Steam ID, or Alderon ID)

    Returns:
        dict with:
            - discord_user: discord.User object (or None)
            - player_record: Database player record (or None)
            - user_id: Discord user ID (primary identity)
            - steam_id: Linked Steam ID (or None)
            - alderon_id: Linked Alderon ID (or None)
            - player_name: In-game player name (or Discord username)
            - success: bool
            - error: str (if not successful)
    """
    try:
        guild_id = interaction.guild_id
        guild = interaction.guild

        # Try to parse as Discord user
        user = None
        if query.startswith('<@') and query.endswith('>'):
            # Discord mention
            user_id = int(query[2:-1].replace('!', ''))
            try:
                user = await interaction.client.fetch_user(user_id)
            except:
                pass
        elif query.isdigit() and len(query) > 15:
            # Discord ID (17-19 digits) or Steam ID (17 digits)
            if len(query) == 17:
                # Could be Steam ID - check database first
                player_record = PlayerQueries.get_by_steam_id(guild_id, query)
                if player_record and player_record.get('user_id'):
                    try:
                        user = await interaction.client.fetch_user(player_record['user_id'])
                    except:
                        pass

            # Try as Discord ID
            if not user:
                try:
                    user = await interaction.client.fetch_user(int(query))
                except:
                    pass
        else:
            # Search guild members by username/display name
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

        # Search database by any game ID
        player_record = None
        if user:
            # Found Discord user - get their linked accounts
            player_record = PlayerQueries.get_by_user(guild_id, user.id)
        else:
            # Try as Alderon ID or Steam ID
            player_record = PlayerQueries.get_by_player_id(guild_id, query)
            if not player_record:
                player_record = PlayerQueries.get_by_steam_id(guild_id, query)

            # If found player record, try to get Discord user
            if player_record and player_record.get('user_id'):
                try:
                    user = await interaction.client.fetch_user(player_record['user_id'])
                except:
                    pass

        # Build result
        if not player_record and not user:
            return {
                'success': False,
                'error': f"No player found matching: `{query}`\n\n"
                        f"**Tip:** Make sure the player has linked their IDs first.\n"
                        f"You can search by:\n"
                        f"• Discord username or @mention\n"
                        f"• Steam ID (17 digits)\n"
                        f"• Alderon ID (XXX-XXX-XXX)"
            }

        # Extract all identifiers
        user_id = user.id if user else (player_record.get('user_id') if player_record else None)
        steam_id = player_record.get('steam_id') if player_record else None
        alderon_id = player_record.get('player_id') if player_record else None

        # Determine player name (prefer in-game name, fallback to Discord)
        player_name = None
        if player_record:
            player_name = player_record.get('player_name') or player_record.get('steam_name')
        if not player_name and user:
            player_name = user.display_name
        if not player_name:
            player_name = "Unknown Player"

        return {
            'success': True,
            'discord_user': user,
            'player_record': player_record,
            'user_id': user_id,
            'steam_id': steam_id,
            'alderon_id': alderon_id,
            'player_name': player_name,
            'error': None
        }

    except Exception as e:
        logger.error(f"Error looking up player for enforcement: {e}", exc_info=True)
        return {
            'success': False,
            'error': "An error occurred while looking up the player. Please try again."
        }


def format_player_identity_embed(lookup_result: dict) -> discord.Embed:
    """
    Format a player's identity information for confirmation in modals.

    Shows all linked accounts so moderators can verify they're targeting the right player.
    """
    embed = discord.Embed(
        title="Player Identity",
        color=discord.Color.blue()
    )

    discord_user = lookup_result.get('discord_user')
    player_record = lookup_result.get('player_record')

    # Discord info
    if discord_user:
        embed.add_field(
            name="Discord",
            value=f"{discord_user.mention}\n**Username:** @{discord_user.name}\n**ID:** `{discord_user.id}`",
            inline=False
        )
        embed.set_thumbnail(url=discord_user.display_avatar.url)
    elif lookup_result.get('user_id'):
        embed.add_field(
            name="Discord",
            value=f"**ID:** `{lookup_result['user_id']}`\n*(User not in server)*",
            inline=False
        )
    else:
        embed.add_field(
            name="Discord",
            value="*Not linked*",
            inline=False
        )

    # Steam info
    if lookup_result.get('steam_id'):
        steam_name = player_record.get('steam_name', 'Unknown') if player_record else 'Unknown'
        embed.add_field(
            name="Steam",
            value=f"**Name:** {steam_name}\n**ID:** `{lookup_result['steam_id']}`",
            inline=False
        )
    else:
        embed.add_field(
            name="Steam",
            value="*Not linked*",
            inline=False
        )

    # Alderon info
    if lookup_result.get('alderon_id'):
        embed.add_field(
            name="Alderon (Path of Titans)",
            value=f"**Player Name:** {player_record.get('player_name', 'Unknown') if player_record else 'Unknown'}\n"
                  f"**ID:** `{lookup_result['alderon_id']}`",
            inline=False
        )
    else:
        embed.add_field(
            name="Alderon (Path of Titans)",
            value="*Not linked*",
            inline=False
        )

    embed.set_footer(text="Enforcement actions will apply to ALL linked accounts")

    return embed


def get_primary_game_id(lookup_result: dict, preferred_source: str = None) -> tuple[str, str]:
    """
    Get the primary game ID for backward compatibility with existing strike queries.

    Returns: (in_game_id, source_type)

    Priority:
    1. preferred_source (if specified and available)
    2. Alderon ID (Path of Titans)
    3. Steam ID (The Isle)
    4. Discord ID (fallback)
    """
    if preferred_source == 'alderon' and lookup_result.get('alderon_id'):
        return (lookup_result['alderon_id'], 'path_of_titans')
    if preferred_source == 'steam' and lookup_result.get('steam_id'):
        return (lookup_result['steam_id'], 'the_isle')

    # Default priority
    if lookup_result.get('alderon_id'):
        return (lookup_result['alderon_id'], 'path_of_titans')
    if lookup_result.get('steam_id'):
        return (lookup_result['steam_id'], 'the_isle')
    if lookup_result.get('user_id'):
        return (str(lookup_result['user_id']), 'discord')

    return (None, None)
