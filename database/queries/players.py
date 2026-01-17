# database/queries/players.py
"""Player linking database queries"""

from database.connection import get_cursor
import logging

logger = logging.getLogger(__name__)


class PlayerQueries:
    """Database operations for player ID linking."""

    @staticmethod
    def link_player(guild_id: int, user_id: int, username: str,
                    player_id: str, player_name: str) -> bool:
        """
        Link a Discord user to an Alderon player ID.
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
            logger.info(f"Linked player {username} -> {player_id} in guild {guild_id}")
            return True

    @staticmethod
    def get_by_user(guild_id: int, user_id: int) -> dict | None:
        """Get player info by Discord user ID."""
        with get_cursor() as cursor:
            cursor.execute(
                """SELECT * FROM players
                   WHERE guild_id = %s AND user_id = %s""",
                (guild_id, user_id)
            )
            return cursor.fetchone()

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
        Returns list of matching players.
        """
        search_pattern = f"%{query}%"
        with get_cursor() as cursor:
            cursor.execute(
                """SELECT * FROM players
                   WHERE guild_id = %s
                   AND (player_name LIKE %s
                        OR player_id LIKE %s
                        OR username LIKE %s)
                   LIMIT 10""",
                (guild_id, search_pattern, search_pattern, search_pattern)
            )
            return cursor.fetchall()

    @staticmethod
    def unlink(guild_id: int, user_id: int) -> bool:
        """Remove player link. Returns True if a record was deleted."""
        with get_cursor() as cursor:
            cursor.execute(
                """DELETE FROM players
                   WHERE guild_id = %s AND user_id = %s""",
                (guild_id, user_id)
            )
            deleted = cursor.rowcount > 0
            if deleted:
                logger.info(f"Unlinked player {user_id} in guild {guild_id}")
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
