# services/permissions.py
"""
Permission checking for TBNManager

Handles role-based permissions with support for:
- Server owner (always has access)
- Discord Administrator permission
- Granular per-command permissions (new system)
- Legacy admin roles (fallback during transition)
"""

import discord
from database.queries import GuildQueries, PermissionQueries
import logging

logger = logging.getLogger(__name__)

# Default role names that grant admin access (fallback if no roles configured)
DEFAULT_ADMIN_ROLES = ['Owner', 'Headadmin', 'Admin', 'Moderator']


def has_admin_permission(member: discord.Member, guild_id: int) -> bool:
    """
    Check if a member has admin permissions.

    Admin access is granted if ANY of these are true:
    1. Member is the server owner
    2. Member has Discord Administrator permission
    3. Member has a role in the guild's configured admin roles
    4. Member has a role matching DEFAULT_ADMIN_ROLES (fallback)
    """

    # Server owner always has access
    if member.guild.owner_id == member.id:
        return True

    # Discord Administrator permission
    if member.guild_permissions.administrator:
        return True

    # Get configured admin roles from database
    try:
        admin_roles = GuildQueries.get_admin_roles(guild_id)
        if admin_roles:
            admin_role_ids = {r['role_id'] for r in admin_roles}
            if any(role.id in admin_role_ids for role in member.roles):
                return True
    except Exception as e:
        logger.warning(f"Could not check database admin roles: {e}")

    # Fallback to default role names
    member_role_names = {role.name for role in member.roles}
    if member_role_names.intersection(DEFAULT_ADMIN_ROLES):
        return True

    return False


def get_permission_level(member: discord.Member, guild_id: int) -> int:
    """
    Get the permission level for a member.

    Returns:
        0 = User (no special permissions)
        1 = Moderator
        2 = Admin
        3 = Owner
    """

    # Server owner
    if member.guild.owner_id == member.id:
        return 3

    # Discord Administrator
    if member.guild_permissions.administrator:
        return 3

    # Check configured roles
    try:
        admin_roles = GuildQueries.get_admin_roles(guild_id)
        if admin_roles:
            admin_role_map = {r['role_id']: r['permission_level'] for r in admin_roles}
            member_levels = [
                admin_role_map[role.id]
                for role in member.roles
                if role.id in admin_role_map
            ]
            if member_levels:
                return max(member_levels)
    except Exception as e:
        logger.warning(f"Could not check database permission levels: {e}")

    # Fallback check
    member_role_names = {role.name for role in member.roles}
    if 'Owner' in member_role_names:
        return 3
    if 'Headadmin' in member_role_names or 'Admin' in member_role_names:
        return 2
    if 'Moderator' in member_role_names:
        return 1

    return 0


async def require_admin(interaction: discord.Interaction,
                        min_level: int = 1,
                        ephemeral: bool = True) -> bool:
    """
    Check if the interaction user has admin permissions.
    Sends error message and returns False if not.

    Args:
        interaction: The Discord interaction
        min_level: Minimum permission level required (1=mod, 2=admin, 3=owner)
        ephemeral: Whether error message should be ephemeral

    Returns:
        True if user has permission, False otherwise
    """

    # Check if command is being used in a guild
    if not interaction.guild:
        await interaction.response.send_message(
            "This command can only be used in a server, not in DMs.",
            ephemeral=True
        )
        return False

    if interaction.user.bot:
        return False

    # In a guild, interaction.user is a Member, not User
    member = interaction.user
    level = get_permission_level(member, interaction.guild_id)

    if level >= min_level:
        return True

    # Permission denied
    level_names = {1: 'Moderator', 2: 'Admin', 3: 'Owner'}
    required = level_names.get(min_level, 'Admin')

    await interaction.response.send_message(
        f"You don't have permission to use this command. "
        f"Required: **{required}** or higher.",
        ephemeral=ephemeral
    )
    return False


async def require_owner(interaction: discord.Interaction) -> bool:
    """Shortcut for requiring owner-level permissions."""
    return await require_admin(interaction, min_level=3)


def check_feature_access(guild_id: int, feature_name: str,
                         is_premium_guild: bool = False) -> tuple[bool, str]:
    """
    Check if a feature is accessible for a guild.

    Returns:
        (allowed, reason) tuple
    """
    from config.settings import PREMIUM_FEATURES

    # Check if feature is enabled
    if not GuildQueries.is_feature_enabled(guild_id, feature_name):
        return False, "This feature is disabled on this server."

    # Check premium requirements
    if feature_name in PREMIUM_FEATURES and not is_premium_guild:
        return False, "This feature requires a premium subscription."

    return True, ""


async def require_permission(interaction: discord.Interaction,
                             command_name: str,
                             ephemeral: bool = True) -> bool:
    """
    Check if user has permission for a specific command using the new system.

    This checks:
    1. Server owner - always has full access
    2. Discord Administrator - always has full access
    3. Role-based permissions from guild_role_permissions table

    Args:
        interaction: The Discord interaction
        command_name: Name of the command being checked
        ephemeral: Whether error message should be ephemeral

    Returns:
        True if user has permission, False otherwise
    """
    # Check if command is being used in a guild
    if not interaction.guild:
        await interaction.response.send_message(
            "This command can only be used in a server, not in DMs.",
            ephemeral=True
        )
        return False

    if interaction.user.bot:
        return False

    guild_id = interaction.guild_id
    user = interaction.user

    # Server owner always has full access
    if user.id == interaction.guild.owner_id:
        return True

    # Discord Administrator permission = full access
    if user.guild_permissions.administrator:
        return True

    # Check role-based permissions from new system
    user_role_ids = [role.id for role in user.roles]

    try:
        if PermissionQueries.can_use_command(guild_id, user_role_ids, command_name):
            return True
    except Exception as e:
        logger.error(f"Error checking command permission: {e}")
        # On error, fall through to legacy check

    # Fallback to legacy permission system during transition
    # This allows existing setups to keep working
    level = get_permission_level(user, guild_id)
    if level >= 1:  # At least moderator level in old system
        return True

    # Permission denied
    await interaction.response.send_message(
        "You don't have permission to use this command.",
        ephemeral=ephemeral
    )
    return False


def get_user_allowed_commands(guild_id: int, member: discord.Member) -> set:
    """
    Get all commands a user can access based on their roles.

    Args:
        guild_id: The guild ID
        member: The Discord member

    Returns:
        Set of command names the user can access
    """
    from config.commands import get_all_commands

    # Server owner and admins see all
    if member.id == member.guild.owner_id or member.guild_permissions.administrator:
        return set(get_all_commands())

    user_role_ids = [role.id for role in member.roles]

    try:
        allowed = PermissionQueries.get_user_allowed_commands(guild_id, user_role_ids)

        # If new system has no permissions, fall back to legacy check
        if not allowed:
            level = get_permission_level(member, guild_id)
            if level >= 1:
                # Give legacy admins access to all commands
                return set(get_all_commands())

        return allowed
    except Exception as e:
        logger.error(f"Error getting allowed commands: {e}")
        return set()
