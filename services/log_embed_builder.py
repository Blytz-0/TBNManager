"""
Discord embed builders for enhanced log events.
Creates rich, formatted embeds for player logins, logouts, chat, admin commands, and deaths.
"""

import discord
import re
from typing import Optional
from services.log_parsers import (
    PlayerLoginEvent, PlayerLogoutEvent, PlayerChatEvent,
    AdminCommandEvent, RCONCommandEvent, PlayerDeathEvent
)
from database.queries.players import PlayerQueries
from database.queries.rcon import SFTPConfigQueries
from services.game_ini_cache import GameIniAdminCache
import logging

logger = logging.getLogger(__name__)

# Cache for Game.ini admin lists (guild_id: set of steam_ids)
_game_ini_admin_cache = {}
_cache_timestamp = {}


async def check_game_ini_admin(guild_id: int, steam_id: str) -> bool:
    """
    Check if a Steam ID is in the Game.ini admin list.

    Returns:
        True if player is admin in Game.ini, False otherwise
    """
    try:
        # Check cache (refresh every 5 minutes)
        import time
        current_time = time.time()
        cache_key = guild_id

        if cache_key in _game_ini_admin_cache:
            if current_time - _cache_timestamp.get(cache_key, 0) < 300:  # 5 minutes
                return steam_id in _game_ini_admin_cache[cache_key]

        # Get SFTP config to find Game.ini path
        configs = SFTPConfigQueries.get_active_configs(guild_id)
        if not configs:
            return False

        # Try to read Game.ini from first active config
        # Game.ini path is typically stored in admin_log_path or as a separate field
        config = configs[0]
        game_ini_path = config.get('game_ini_path') or config.get('admin_log_path', '').replace('TheIsle.log', 'Config/LinuxServer/Game.ini')

        if not game_ini_path or 'Game.ini' not in game_ini_path:
            return False

        # Read Game.ini via SFTP
        import paramiko
        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(
                hostname=config['host'],
                port=config['port'],
                username=config['username'],
                password=config['password'],
                timeout=5
            )
            sftp = ssh.open_sftp()

            # Read Game.ini
            with sftp.open(game_ini_path, 'r') as f:
                content = f.read().decode('utf-8', errors='ignore')

            sftp.close()
            ssh.close()

            # Parse admin Steam IDs from Game.ini
            # Format: AdminsSteamIDs=76561198012345678
            admin_ids = set()
            for line in content.split('\n'):
                if line.strip().startswith('AdminsSteamIDs='):
                    steam_id_match = re.search(r'AdminsSteamIDs=(\d+)', line)
                    if steam_id_match:
                        admin_ids.add(steam_id_match.group(1))

            # Cache the result
            _game_ini_admin_cache[cache_key] = admin_ids
            _cache_timestamp[cache_key] = current_time

            return steam_id in admin_ids

        except Exception as e:
            logger.debug(f"Could not read Game.ini for admin check: {e}")
            return False

    except Exception as e:
        logger.debug(f"Error checking Game.ini admin status: {e}")
        return False


async def get_player_discord_role(guild: discord.Guild, steam_id: str) -> Optional[tuple[discord.Member, str]]:
    """
    Get Discord member and role for a Steam ID if linked.

    Returns:
        Tuple of (Member, role_name) or None if not linked
    """
    try:
        # Query player_ids table for Discord user_id
        player = PlayerQueries.get_player_by_steam_id(guild.id, steam_id)
        if not player or not player.get('user_id'):
            return None

        # Get Discord member
        member = guild.get_member(player['user_id'])
        if not member:
            return None

        # Get highest role (excluding @everyone)
        roles = sorted(member.roles, key=lambda r: r.position, reverse=True)
        for role in roles:
            if role.name != "@everyone":
                return (member, role.name)

        return (member, "Member")
    except Exception:
        return None


def is_admin_role(role_name: str) -> bool:
    """Check if a role name indicates admin status."""
    admin_keywords = ['owner', 'admin', 'moderator', 'mod', 'staff', 'co-owner', 'head']
    return any(keyword in role_name.lower() for keyword in admin_keywords)


async def check_if_admin(guild: Optional[discord.Guild], steam_id: str) -> bool:
    """
    Check if a Steam ID is an admin by checking both Discord role and Game.ini.

    Args:
        guild: Discord guild (optional)
        steam_id: Steam ID to check

    Returns:
        True if admin (either Discord role or Game.ini), False otherwise
    """
    # Check Discord role if guild provided
    if guild:
        result = await get_player_discord_role(guild, steam_id)
        if result:
            _, role_name = result
            if is_admin_role(role_name):
                return True

        # Check Game.ini cache
        if GameIniAdminCache.is_admin(guild.id, steam_id):
            return True

    return False


async def build_player_login_embed(
    event: PlayerLoginEvent,
    server_name: str,
    guild: Optional[discord.Guild] = None
) -> discord.Embed:
    """
    Build embed for player login event.

    Format:
        🟢 [Server Name] - Player Joined
        Player: Name (SteamID)
        Dinosaur: Type ♂/♀ (Growth%)
        Admin: Yes (Role) / No
        Timestamp: 2026.01.31-04.47.53
    """
    # Check if player is admin (check both Discord role and Game.ini cache)
    is_admin = await check_if_admin(guild, event.steam_id)

    # Get role name for display
    role_name = None
    if guild and is_admin:
        result = await get_player_discord_role(guild, event.steam_id)
        if result:
            _, role_name = result

    # Format dinosaur info
    gender_symbol = '♂' if event.gender.lower() == 'male' else '♀' if event.gender.lower() == 'female' else ''
    growth_pct = event.growth * 100
    dino_display = f"{event.dinosaur} {gender_symbol} ({growth_pct:.1f}%)"

    # Parse timestamp (remove milliseconds)
    timestamp_display = event.timestamp
    if ':' in timestamp_display:
        timestamp_display = timestamp_display.rsplit(':', 1)[0]

    # Build embed
    embed = discord.Embed(
        title=f"🟢 {server_name} - Player Joined",
        color=discord.Color.gold() if is_admin else discord.Color.green()
    )

    embed.add_field(
        name="Player",
        value=f"{event.player_name} (`{event.steam_id}`)",
        inline=False
    )
    embed.add_field(
        name="Dinosaur",
        value=dino_display,
        inline=False
    )

    if is_admin and role_name:
        embed.add_field(
            name="Admin",
            value=f"Yes ({role_name})",
            inline=False
        )
    elif is_admin:
        embed.add_field(
            name="Admin",
            value="Yes",
            inline=False
        )

    embed.add_field(
        name="Timestamp",
        value=timestamp_display,
        inline=False
    )

    return embed


async def build_player_logout_embed(
    event: PlayerLogoutEvent,
    server_name: str,
    guild: Optional[discord.Guild] = None
) -> discord.Embed:
    """
    Build embed for player logout event.

    Format:
        🔴 [Server Name] - Player Left
        Player: Name (SteamID)
        Dinosaur: Type ♂/♀ (Growth%)
        Safe Logged: Yes/No
        Timestamp: 2026.01.31-04.47.53
    """
    # Format dinosaur info
    gender_symbol = '♂' if event.gender.lower() == 'male' else '♀' if event.gender.lower() == 'female' else ''
    growth_pct = event.growth * 100
    dino_display = f"{event.dinosaur} {gender_symbol} ({growth_pct:.1f}%)"

    # Parse timestamp (remove milliseconds)
    timestamp_display = event.timestamp
    if ':' in timestamp_display:
        timestamp_display = timestamp_display.rsplit(':', 1)[0]

    # Build embed
    embed = discord.Embed(
        title=f"🔴 {server_name} - Player Left",
        color=discord.Color.red()
    )

    embed.add_field(
        name="Player",
        value=f"{event.player_name} (`{event.steam_id}`)",
        inline=False
    )
    embed.add_field(
        name="Dinosaur",
        value=dino_display,
        inline=False
    )
    embed.add_field(
        name="Safe Logged",
        value="Yes" if event.safe_logged else "No",
        inline=False
    )
    embed.add_field(
        name="Timestamp",
        value=timestamp_display,
        inline=False
    )

    return embed


async def build_player_chat_embed(
    event: PlayerChatEvent,
    guild: Optional[discord.Guild] = None
) -> discord.Embed:
    """
    Build embed for player chat event.

    Format:
        Channel: Local/Global/Admin
        PlayerName: Name
        SteamID: 76561198012345678
        Message: message text
        Admin: true/false
        Timestamp: 2026.01.31-04.47.53
    """
    # Check if player is admin (check both Discord role and Game.ini cache)
    is_admin = await check_if_admin(guild, event.steam_id)

    # Map channel names (Spatial → Local)
    channel_display = event.channel
    if event.channel.lower() == 'spatial':
        channel_display = 'Local'

    # Choose color based on channel
    channel_colors = {
        'global': discord.Color.blue(),
        'admin': discord.Color.gold(),
        'spatial': discord.Color.green(),
        'local': discord.Color.green(),
        'logging': discord.Color.light_gray(),
        'log': discord.Color.light_gray()
    }
    color = channel_colors.get(event.channel.lower(), discord.Color.blue())

    # Parse timestamp from event (format: "2026.01.31-04.47.53:825")
    # Extract just the date and time without milliseconds
    timestamp_display = event.timestamp
    if ':' in timestamp_display:
        timestamp_display = timestamp_display.rsplit(':', 1)[0]  # Remove milliseconds

    # Build embed with clean field layout
    embed = discord.Embed(
        color=color
    )

    embed.add_field(
        name="Channel",
        value=channel_display,
        inline=False
    )
    embed.add_field(
        name="PlayerName",
        value=event.player_name,
        inline=False
    )
    embed.add_field(
        name="Admin",
        value=str(is_admin).lower(),
        inline=False
    )
    embed.add_field(
        name="SteamID",
        value=event.steam_id,
        inline=False
    )
    embed.add_field(
        name="Message",
        value=event.message,
        inline=False
    )
    embed.add_field(
        name="Timestamp",
        value=timestamp_display,
        inline=False
    )

    return embed


async def build_admin_command_embed(
    event: AdminCommandEvent,
    server_name: str,
    guild: Optional[discord.Guild] = None
) -> discord.Embed:
    """
    Build embed for admin command event.

    Format:
        ⚡ [Server Name] - Admin Command
        Admin: Name (SteamID)
        Role: Co-Owner (if linked)
        Command: CommandName params
        Target: Name (Class ♂/♀)
        Previous: X% → New: Y%
        Timestamp: 2026.01.31-04.47.53
    """
    # Check if admin is linked to Discord
    role_name = None
    if guild:
        result = await get_player_discord_role(guild, event.admin_steam_id)
        if result:
            _, role_name = result

    # Parse timestamp (remove milliseconds)
    timestamp_display = event.timestamp
    if ':' in timestamp_display:
        timestamp_display = timestamp_display.rsplit(':', 1)[0]

    # Build embed
    embed = discord.Embed(
        title=f"⚡ {server_name} - Admin Command",
        color=discord.Color.gold()
    )

    # Admin info
    admin_value = f"{event.admin_name} (`{event.admin_steam_id}`)"
    embed.add_field(
        name="Admin",
        value=admin_value,
        inline=False
    )

    if role_name:
        embed.add_field(
            name="Role",
            value=role_name,
            inline=True
        )

    # Command info
    embed.add_field(
        name="Command",
        value=f"`{event.command}`",
        inline=False
    )

    # Target info (if available)
    if event.target_name and event.target_class:
        gender_symbol = '♂' if event.target_gender and event.target_gender.lower() == 'male' else '♀' if event.target_gender and event.target_gender.lower() == 'female' else ''
        target_display = f"{event.target_name} ({event.target_class} {gender_symbol})".strip()
        embed.add_field(
            name="Target",
            value=target_display,
            inline=False
        )

    # Before/after values (if available)
    if event.previous_value and event.new_value:
        embed.add_field(
            name="Change",
            value=f"{event.previous_value} → {event.new_value}",
            inline=False
        )

    embed.add_field(
        name="Timestamp",
        value=timestamp_display,
        inline=False
    )

    return embed


async def build_rcon_command_embed(
    event: RCONCommandEvent,
    server_name: str,
    guild: Optional[discord.Guild] = None
) -> discord.Embed:
    """
    Build embed for RCON command event.

    Format:
        🤖 [Server Name] - RCON Command
        Command: [CommandType]
        Details: Command details/arguments
        Executed By: Username (Role)
        Timestamp: 2026.01.31-04.47.53
    """
    # Parse timestamp (remove milliseconds)
    timestamp_display = event.timestamp
    if ':' in timestamp_display:
        timestamp_display = timestamp_display.rsplit(':', 1)[0]

    # Build embed
    embed = discord.Embed(
        title=f"🤖 {server_name} - RCON Command",
        color=discord.Color.purple()
    )

    embed.add_field(
        name="Command",
        value=f"`{event.command}`",
        inline=False
    )

    if event.details:
        # Limit details to 1024 characters to avoid embed limits
        details_text = event.details if len(event.details) <= 1024 else event.details[:1021] + "..."
        embed.add_field(
            name="Details",
            value=details_text,
            inline=False
        )

    # Add executor information if available
    if event.executor_id and event.executor_name:
        executor_display = event.executor_name

        # Try to get the user's role from Discord
        if guild and event.executor_id:
            try:
                member = guild.get_member(event.executor_id)
                if member:
                    # Get the highest role (excluding @everyone)
                    roles = [r for r in member.roles if r.name != "@everyone"]
                    if roles:
                        highest_role = max(roles, key=lambda r: r.position)
                        executor_display = f"{event.executor_name} ({highest_role.name})"
            except Exception:
                pass  # If we can't fetch the member, just use the name

        embed.add_field(
            name="Executed By",
            value=executor_display,
            inline=False
        )

    embed.add_field(
        name="Timestamp",
        value=timestamp_display,
        inline=False
    )

    embed.set_footer(text="Executed via Discord RCON")

    return embed


async def build_player_death_embed(
    event: PlayerDeathEvent,
    server_name: str,
    guild: Optional[discord.Guild] = None
) -> discord.Embed:
    """
    Build embed for player death event.

    Format:
        ☠️ [Server Name] - Player Death
        CauseOfDeath: Died from Natural cause / Killed by...
        VictimName: Name
        VictimSteamId: 76561198012345678
        VictimClass: Tyrannosaurus ♂
        IsVictimPrime: true/false
        VictimIsAdmin: true/false
        VictimGrowth: 72.8%
        VictimLocation: (future)

        (If killed by player)
        KillerName: Name
        KillerSteamId: 76561198012345678
        KillerClass: Carnotaurus ♀
        IsKillerPrime: true/false
        KillerIsAdmin: true/false
        KillerGrowth: 100%
        KillerLocation: (future)
        Timestamp: 2026.01.31-04.48.53
    """
    # Check if victim is admin (check both Discord role and Game.ini cache)
    victim_is_admin = await check_if_admin(guild, event.victim_steam_id)

    # Parse timestamp (remove milliseconds)
    timestamp_display = event.timestamp
    if ':' in timestamp_display:
        timestamp_display = timestamp_display.rsplit(':', 1)[0]

    # Build embed
    embed = discord.Embed(
        title=f"☠️ {server_name} - Player Death",
        color=discord.Color.dark_red()
    )

    # Cause of Death
    embed.add_field(
        name="CauseOfDeath",
        value=event.cause_of_death,
        inline=False
    )

    # Victim Name
    embed.add_field(
        name="VictimName",
        value=event.victim_name,
        inline=False
    )

    # Victim Steam ID
    embed.add_field(
        name="VictimSteamId",
        value=event.victim_steam_id,
        inline=False
    )

    # Victim Class (with gender symbol)
    gender_symbol = '♂' if event.victim_gender.lower() == 'male' else '♀' if event.victim_gender.lower() == 'female' else ''
    victim_class_display = f"{event.victim_class} {gender_symbol}".strip()
    embed.add_field(
        name="VictimClass",
        value=victim_class_display,
        inline=False
    )

    # Is Victim Prime
    embed.add_field(
        name="IsVictimPrime",
        value=str(event.victim_is_prime).lower(),
        inline=False
    )

    # Victim Is Admin
    embed.add_field(
        name="VictimIsAdmin",
        value=str(victim_is_admin).lower(),
        inline=False
    )

    # Victim Growth
    growth_pct = event.victim_growth * 100
    embed.add_field(
        name="VictimGrowth",
        value=f"{growth_pct:.1f}%",
        inline=False
    )

    # Victim Location (future)
    if event.victim_location:
        embed.add_field(
            name="VictimLocation",
            value=event.victim_location,
            inline=False
        )

    # Killer info (if available)
    if event.killer_name and event.killer_class:
        # Check if killer is admin (check both Discord role and Game.ini cache)
        killer_is_admin = False
        if guild and event.killer_steam_id:
            killer_is_admin = await check_if_admin(guild, event.killer_steam_id)

        # Killer Name
        embed.add_field(
            name="KillerName",
            value=event.killer_name,
            inline=False
        )

        # Killer Steam ID
        if event.killer_steam_id:
            embed.add_field(
                name="KillerSteamId",
                value=event.killer_steam_id,
                inline=False
            )

        # Killer Class (with gender symbol)
        killer_gender_symbol = '♂' if event.killer_gender and event.killer_gender.lower() == 'male' else '♀' if event.killer_gender and event.killer_gender.lower() == 'female' else ''
        killer_class_display = f"{event.killer_class} {killer_gender_symbol}".strip()
        embed.add_field(
            name="KillerClass",
            value=killer_class_display,
            inline=False
        )

        # Is Killer Prime
        embed.add_field(
            name="IsKillerPrime",
            value=str(event.killer_is_prime).lower(),
            inline=False
        )

        # Killer Is Admin
        embed.add_field(
            name="KillerIsAdmin",
            value=str(killer_is_admin).lower(),
            inline=False
        )

        # Killer Growth
        if event.killer_growth is not None:
            killer_growth_pct = event.killer_growth * 100
            embed.add_field(
                name="KillerGrowth",
                value=f"{killer_growth_pct:.1f}%",
                inline=False
            )

        # Killer Location (future)
        if event.killer_location:
            embed.add_field(
                name="KillerLocation",
                value=event.killer_location,
                inline=False
            )

    # Timestamp
    embed.add_field(
        name="Timestamp",
        value=timestamp_display,
        inline=False
    )

    return embed
