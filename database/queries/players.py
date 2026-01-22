# database/queries/players.py
"""Player linking database queries for the passport system.

Supports linking Discord users to:
- Alderon ID (Path of Titans)
- Steam ID (The Isle and other games)
- Both IDs simultaneously
"""

from database.connection import get_cursor
import logging

logger = logging.getLogger(__name__)


class PlayerQueries:
    """Database operations for player ID linking."""

    # ==========================================
    # ALDERON ID LINKING
    # ==========================================

    @staticmethod
    def link_alderon(guild_id: int, user_id: int, username: str,
                     player_id: str, player_name: str) -> bool:
        """
        Link a Discord user to an Alderon player ID.
        Creates record if not exists, updates Alderon fields if exists.
        Returns True if successful.
        """
        with get_cursor() as cursor:
            cursor.execute(
                """INSERT INTO players (guild_id, user_id, username, player_id, player_name)
                   VALUES (%s, %s, %s, %s, %s)
                   ON DUPLICATE KEY UPDATE
                       player_id = VALUES(player_id),
                       player_name = VALUES(player_name),
                       username = VALUES(username)""",
                (guild_id, user_id, username, player_id, player_name)
            )
            logger.info(f"Linked Alderon ID {player_id} for {username} in guild {guild_id}")
            return True

    @staticmethod
    def get_by_player_id(guild_id: int, player_id: str) -> dict | None:
        """Get player info by Alderon player ID."""
        with get_cursor() as cursor:
            cursor.execute(
                """SELECT * FROM players
                   WHERE guild_id = %s AND player_id = %s""",
                (guild_id, player_id)
            )
            return cursor.fetchone()

    @staticmethod
    def clear_alderon(guild_id: int, user_id: int) -> bool:
        """Clear Alderon ID from a user's record (admin unlock)."""
        with get_cursor() as cursor:
            cursor.execute(
                """UPDATE players
                   SET player_id = NULL, player_name = NULL
                   WHERE guild_id = %s AND user_id = %s""",
                (guild_id, user_id)
            )
            if cursor.rowcount > 0:
                logger.info(f"Cleared Alderon ID for user {user_id} in guild {guild_id}")
                return True
            return False

    # ==========================================
    # STEAM ID LINKING
    # ==========================================

    @staticmethod
    def link_steam(guild_id: int, user_id: int, username: str,
                   steam_id: str, steam_name: str) -> bool:
        """
        Link a Discord user to a Steam ID.
        Creates record if not exists, updates Steam fields if exists.
        Returns True if successful.
        """
        with get_cursor() as cursor:
            cursor.execute(
                """INSERT INTO players (guild_id, user_id, username, steam_id, steam_name,
                                        verification_method, verified_at)
                   VALUES (%s, %s, %s, %s, %s, 'steam_api', NOW())
                   ON DUPLICATE KEY UPDATE
                       steam_id = VALUES(steam_id),
                       steam_name = VALUES(steam_name),
                       username = VALUES(username),
                       verification_method = 'steam_api',
                       verified_at = NOW()""",
                (guild_id, user_id, username, steam_id, steam_name)
            )
            logger.info(f"Linked Steam ID {steam_id} for {username} in guild {guild_id}")
            return True

    @staticmethod
    def get_by_steam_id(guild_id: int, steam_id: str) -> dict | None:
        """Get player info by Steam ID."""
        with get_cursor() as cursor:
            cursor.execute(
                """SELECT * FROM players
                   WHERE guild_id = %s AND steam_id = %s""",
                (guild_id, steam_id)
            )
            return cursor.fetchone()

    @staticmethod
    def clear_steam(guild_id: int, user_id: int) -> bool:
        """Clear Steam ID from a user's record (admin unlock)."""
        with get_cursor() as cursor:
            cursor.execute(
                """UPDATE players
                   SET steam_id = NULL, steam_name = NULL
                   WHERE guild_id = %s AND user_id = %s""",
                (guild_id, user_id)
            )
            if cursor.rowcount > 0:
                logger.info(f"Cleared Steam ID for user {user_id} in guild {guild_id}")
                return True
            return False

    # ==========================================
    # GENERAL QUERIES
    # ==========================================

    @staticmethod
    def get_by_user(guild_id: int, user_id: int) -> dict | None:
        """Get all linked IDs for a Discord user."""
        with get_cursor() as cursor:
            cursor.execute(
                """SELECT * FROM players
                   WHERE guild_id = %s AND user_id = %s""",
                (guild_id, user_id)
            )
            return cursor.fetchone()

    @staticmethod
    def get_by_username(guild_id: int, username: str) -> dict | None:
        """Get player info by Discord username."""
        with get_cursor() as cursor:
            cursor.execute(
                """SELECT * FROM players
                   WHERE guild_id = %s AND username = %s""",
                (guild_id, username)
            )
            return cursor.fetchone()

    @staticmethod
    def search(guild_id: int, query: str) -> list:
        """
        Search for players by partial name or ID match.
        Searches: Discord username, Alderon name/ID, Steam name/ID.
        Returns list of matching players (max 10).
        """
        search_pattern = f"%{query}%"
        with get_cursor() as cursor:
            cursor.execute(
                """SELECT * FROM players
                   WHERE guild_id = %s
                   AND (player_name LIKE %s
                        OR player_id LIKE %s
                        OR steam_name LIKE %s
                        OR steam_id LIKE %s
                        OR username LIKE %s)
                   LIMIT 10""",
                (guild_id, search_pattern, search_pattern, search_pattern,
                 search_pattern, search_pattern)
            )
            return cursor.fetchall()

    @staticmethod
    def ensure_record(guild_id: int, user_id: int, username: str) -> bool:
        """
        Ensure a player record exists for a user (create if needed).
        Used when we need a record but don't have any IDs yet.
        """
        with get_cursor() as cursor:
            cursor.execute(
                """INSERT INTO players (guild_id, user_id, username)
                   VALUES (%s, %s, %s)
                   ON DUPLICATE KEY UPDATE username = VALUES(username)""",
                (guild_id, user_id, username)
            )
            return True

    @staticmethod
    def unlink(guild_id: int, user_id: int) -> bool:
        """Remove entire player record. Returns True if a record was deleted."""
        with get_cursor() as cursor:
            cursor.execute(
                """DELETE FROM players
                   WHERE guild_id = %s AND user_id = %s""",
                (guild_id, user_id)
            )
            deleted = cursor.rowcount > 0
            if deleted:
                logger.info(f"Deleted player record for {user_id} in guild {guild_id}")
            return deleted

    @staticmethod
    def get_all(guild_id: int, limit: int = 100, offset: int = 0) -> list:
        """Get all linked players for a guild with pagination."""
        with get_cursor() as cursor:
            cursor.execute(
                """SELECT * FROM players
                   WHERE guild_id = %s
                   ORDER BY created_at DESC
                   LIMIT %s OFFSET %s""",
                (guild_id, limit, offset)
            )
            return cursor.fetchall()

    @staticmethod
    def count(guild_id: int) -> int:
        """Count total linked players in a guild."""
        with get_cursor() as cursor:
            cursor.execute(
                "SELECT COUNT(*) as count FROM players WHERE guild_id = %s",
                (guild_id,)
            )
            result = cursor.fetchone()
            return result['count'] if result else 0

    # ==========================================
    # BACKWARD COMPATIBILITY
    # ==========================================

    @staticmethod
    def link_player(guild_id: int, user_id: int, username: str,
                    player_id: str, player_name: str) -> bool:
        """
        Legacy method - links Alderon ID.
        Deprecated: Use link_alderon() instead.
        """
        return PlayerQueries.link_alderon(guild_id, user_id, username, player_id, player_name)
