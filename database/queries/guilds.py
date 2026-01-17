# database/queries/guilds.py
"""Guild-related database queries"""

from database.connection import get_cursor
import logging

logger = logging.getLogger(__name__)


class GuildQueries:
    """Database operations for guild management."""

    @staticmethod
    def get_or_create(guild_id: int, guild_name: str) -> dict:
        """
        Get a guild from database, or create if it doesn't exist.
        Called when bot joins a server or on first interaction.
        """
        with get_cursor() as cursor:
            # Check if guild exists
            cursor.execute(
                "SELECT * FROM guilds WHERE guild_id = %s",
                (guild_id,)
            )
            guild = cursor.fetchone()

            if guild:
                # Update name if changed
                if guild['guild_name'] != guild_name:
                    cursor.execute(
                        "UPDATE guilds SET guild_name = %s WHERE guild_id = %s",
                        (guild_name, guild_id)
                    )
                    guild['guild_name'] = guild_name
                return guild

            # Create new guild
            cursor.execute(
                """INSERT INTO guilds (guild_id, guild_name)
                   VALUES (%s, %s)""",
                (guild_id, guild_name)
            )

            # Initialize default features
            GuildQueries._init_default_features(cursor, guild_id)

            logger.info(f"Created new guild record: {guild_name} ({guild_id})")

            return {
                'guild_id': guild_id,
                'guild_name': guild_name,
                'is_premium': False,
                'premium_until': None
            }

    @staticmethod
    def _init_default_features(cursor, guild_id: int):
        """Initialize default feature flags for a new guild."""
        cursor.execute(
            """INSERT INTO guild_features (guild_id, feature_name, enabled)
               SELECT %s, feature_name, default_enabled
               FROM feature_definitions
               WHERE is_premium = FALSE
               ON DUPLICATE KEY UPDATE enabled = enabled""",
            (guild_id,)
        )

    @staticmethod
    def get(guild_id: int) -> dict | None:
        """Get guild by ID."""
        with get_cursor() as cursor:
            cursor.execute(
                "SELECT * FROM guilds WHERE guild_id = %s",
                (guild_id,)
            )
            return cursor.fetchone()

    @staticmethod
    def is_feature_enabled(guild_id: int, feature_name: str) -> bool:
        """Check if a feature is enabled for a guild."""
        with get_cursor() as cursor:
            cursor.execute(
                """SELECT enabled FROM guild_features
                   WHERE guild_id = %s AND feature_name = %s""",
                (guild_id, feature_name)
            )
            result = cursor.fetchone()
            return result['enabled'] if result else True  # Default to enabled

    @staticmethod
    def set_feature(guild_id: int, feature_name: str, enabled: bool):
        """Enable or disable a feature for a guild."""
        with get_cursor() as cursor:
            cursor.execute(
                """INSERT INTO guild_features (guild_id, feature_name, enabled)
                   VALUES (%s, %s, %s)
                   ON DUPLICATE KEY UPDATE enabled = %s""",
                (guild_id, feature_name, enabled, enabled)
            )
            logger.info(f"Set feature {feature_name}={enabled} for guild {guild_id}")

    @staticmethod
    def set_admin_role(guild_id: int, role_id: int, permission_level: int = 1):
        """Add or update an admin role for a guild."""
        with get_cursor() as cursor:
            cursor.execute(
                """INSERT INTO guild_admin_roles (guild_id, role_id, permission_level)
                   VALUES (%s, %s, %s)
                   ON DUPLICATE KEY UPDATE permission_level = %s""",
                (guild_id, role_id, permission_level, permission_level)
            )

    @staticmethod
    def get_admin_roles(guild_id: int) -> list:
        """Get all admin roles for a guild."""
        with get_cursor() as cursor:
            cursor.execute(
                """SELECT role_id, permission_level FROM guild_admin_roles
                   WHERE guild_id = %s ORDER BY permission_level DESC""",
                (guild_id,)
            )
            return cursor.fetchall()

    @staticmethod
    def remove_admin_role(guild_id: int, role_id: int):
        """Remove an admin role from a guild."""
        with get_cursor() as cursor:
            cursor.execute(
                "DELETE FROM guild_admin_roles WHERE guild_id = %s AND role_id = %s",
                (guild_id, role_id)
            )

    @staticmethod
    def set_channel(guild_id: int, channel_type: str, channel_id: int):
        """Set a channel for a specific purpose (logs, announcements, etc.)."""
        with get_cursor() as cursor:
            cursor.execute(
                """INSERT INTO guild_channels (guild_id, channel_type, channel_id)
                   VALUES (%s, %s, %s)
                   ON DUPLICATE KEY UPDATE channel_id = %s""",
                (guild_id, channel_type, channel_id, channel_id)
            )

    @staticmethod
    def get_channel(guild_id: int, channel_type: str) -> int | None:
        """Get the channel ID for a specific purpose."""
        with get_cursor() as cursor:
            cursor.execute(
                """SELECT channel_id FROM guild_channels
                   WHERE guild_id = %s AND channel_type = %s""",
                (guild_id, channel_type)
            )
            result = cursor.fetchone()
            return result['channel_id'] if result else None

    @staticmethod
    def delete(guild_id: int):
        """Delete a guild and all related data (CASCADE)."""
        with get_cursor() as cursor:
            cursor.execute("DELETE FROM guilds WHERE guild_id = %s", (guild_id,))
            logger.info(f"Deleted guild {guild_id} and all related data")
