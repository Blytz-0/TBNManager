# database/queries/permissions.py
"""Permission system database queries for granular role-based access control."""

from database.connection import get_cursor
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class PermissionQueries:
    """Database operations for the permission system."""

    @staticmethod
    def get_role_permissions(guild_id: int, role_id: int) -> dict:
        """
        Get all permissions for a role as {command: bool}.
        Returns empty dict if role has no permissions configured.
        """
        with get_cursor() as cursor:
            cursor.execute(
                """SELECT command_name, allowed FROM guild_role_permissions
                   WHERE guild_id = %s AND role_id = %s""",
                (guild_id, role_id)
            )
            results = cursor.fetchall()
            return {row['command_name']: bool(row['allowed']) for row in results}

    @staticmethod
    def set_role_permissions(guild_id: int, role_id: int, permissions: dict):
        """
        Set multiple permissions at once.
        Uses INSERT ... ON DUPLICATE KEY UPDATE for efficiency.
        """
        with get_cursor() as cursor:
            for command_name, allowed in permissions.items():
                cursor.execute(
                    """INSERT INTO guild_role_permissions
                       (guild_id, role_id, command_name, allowed)
                       VALUES (%s, %s, %s, %s)
                       ON DUPLICATE KEY UPDATE allowed = %s""",
                    (guild_id, role_id, command_name, allowed, allowed)
                )
            logger.info(f"Updated {len(permissions)} permissions for role {role_id} in guild {guild_id}")

    @staticmethod
    def get_user_allowed_commands(guild_id: int, user_role_ids: list[int]) -> set:
        """
        Get all commands a user can access based on their roles.
        A user can use a command if ANY of their roles allows it.
        """
        if not user_role_ids:
            return set()

        with get_cursor() as cursor:
            # Use IN clause with placeholders
            placeholders = ','.join(['%s'] * len(user_role_ids))
            cursor.execute(
                f"""SELECT DISTINCT command_name FROM guild_role_permissions
                    WHERE guild_id = %s AND role_id IN ({placeholders}) AND allowed = TRUE""",
                (guild_id, *user_role_ids)
            )
            results = cursor.fetchall()
            return {row['command_name'] for row in results}

    @staticmethod
    def can_use_command(guild_id: int, user_role_ids: list[int], command: str) -> bool:
        """
        Check if user can use a specific command.
        Returns True if ANY of user's roles has permission for this command.
        """
        if not user_role_ids:
            return False

        with get_cursor() as cursor:
            placeholders = ','.join(['%s'] * len(user_role_ids))
            cursor.execute(
                f"""SELECT 1 FROM guild_role_permissions
                    WHERE guild_id = %s AND role_id IN ({placeholders})
                    AND command_name = %s AND allowed = TRUE
                    LIMIT 1""",
                (guild_id, *user_role_ids, command)
            )
            return cursor.fetchone() is not None

    @staticmethod
    def get_configured_roles(guild_id: int) -> list:
        """
        Get all roles that have been configured with permissions.
        Returns list of dicts with role_id and command_count.
        """
        with get_cursor() as cursor:
            cursor.execute(
                """SELECT role_id,
                   SUM(CASE WHEN allowed = TRUE THEN 1 ELSE 0 END) as allowed_count,
                   COUNT(*) as total_configured
                   FROM guild_role_permissions
                   WHERE guild_id = %s
                   GROUP BY role_id
                   ORDER BY allowed_count DESC""",
                (guild_id,)
            )
            return cursor.fetchall()

    @staticmethod
    def count_allowed_commands(guild_id: int, role_id: int) -> int:
        """Count how many commands a role has access to."""
        with get_cursor() as cursor:
            cursor.execute(
                """SELECT COUNT(*) as count FROM guild_role_permissions
                   WHERE guild_id = %s AND role_id = %s AND allowed = TRUE""",
                (guild_id, role_id)
            )
            result = cursor.fetchone()
            return result['count'] if result else 0

    @staticmethod
    def delete_role_permissions(guild_id: int, role_id: int) -> int:
        """
        Delete all permissions for a role (e.g., when role is deleted).
        Returns number of rows deleted.
        """
        with get_cursor() as cursor:
            cursor.execute(
                "DELETE FROM guild_role_permissions WHERE guild_id = %s AND role_id = %s",
                (guild_id, role_id)
            )
            count = cursor.rowcount
            if count > 0:
                logger.info(f"Deleted {count} permissions for deleted role {role_id} in guild {guild_id}")
            return count

    @staticmethod
    def copy_role_permissions(guild_id: int, source_role_id: int, target_role_id: int) -> int:
        """
        Copy permissions from one role to another.
        Useful for setting up similar roles.
        Returns number of permissions copied.
        """
        with get_cursor() as cursor:
            cursor.execute(
                """INSERT INTO guild_role_permissions (guild_id, role_id, command_name, allowed)
                   SELECT guild_id, %s, command_name, allowed
                   FROM guild_role_permissions
                   WHERE guild_id = %s AND role_id = %s
                   ON DUPLICATE KEY UPDATE allowed = VALUES(allowed)""",
                (target_role_id, guild_id, source_role_id)
            )
            return cursor.rowcount
