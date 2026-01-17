# database/queries/strikes.py
"""Strike system database queries - replaces Trello integration"""

from database.connection import get_cursor
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class StrikeQueries:
    """Database operations for the strike system."""

    @staticmethod
    def add_strike(guild_id: int, player_name: str, in_game_id: str,
                   reason: str, admin_id: int, admin_name: str,
                   user_id: Optional[int] = None) -> dict:
        """
        Add a strike to a player. Automatically calculates strike number.
        Returns the created strike record with strike_number.
        """
        # Get current strike count
        current_count = StrikeQueries.get_strike_count(guild_id, in_game_id)
        strike_number = current_count + 1

        with get_cursor() as cursor:
            cursor.execute(
                """INSERT INTO strikes
                   (guild_id, user_id, player_name, in_game_id, reason,
                    admin_id, admin_name, strike_number)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                (guild_id, user_id, player_name, in_game_id, reason,
                 admin_id, admin_name, strike_number)
            )
            strike_id = cursor.lastrowid

            logger.info(f"Added strike #{strike_number} to {player_name} ({in_game_id}) "
                       f"in guild {guild_id} by {admin_name}")

            return {
                'id': strike_id,
                'guild_id': guild_id,
                'user_id': user_id,
                'player_name': player_name,
                'in_game_id': in_game_id,
                'reason': reason,
                'admin_id': admin_id,
                'admin_name': admin_name,
                'strike_number': strike_number,
                'is_active': True
            }

    @staticmethod
    def get_strike_count(guild_id: int, in_game_id: str) -> int:
        """Get the number of active strikes for a player."""
        with get_cursor() as cursor:
            cursor.execute(
                """SELECT COUNT(*) as count FROM strikes
                   WHERE guild_id = %s AND in_game_id = %s AND is_active = TRUE""",
                (guild_id, in_game_id)
            )
            result = cursor.fetchone()
            return result['count'] if result else 0

    @staticmethod
    def get_player_strikes(guild_id: int, in_game_id: str) -> list:
        """Get all strikes for a player (active and inactive)."""
        with get_cursor() as cursor:
            cursor.execute(
                """SELECT * FROM strikes
                   WHERE guild_id = %s AND in_game_id = %s
                   ORDER BY created_at ASC""",
                (guild_id, in_game_id)
            )
            return cursor.fetchall()

    @staticmethod
    def get_active_strikes(guild_id: int, in_game_id: str) -> list:
        """Get only active strikes for a player."""
        with get_cursor() as cursor:
            cursor.execute(
                """SELECT * FROM strikes
                   WHERE guild_id = %s AND in_game_id = %s AND is_active = TRUE
                   ORDER BY strike_number ASC""",
                (guild_id, in_game_id)
            )
            return cursor.fetchall()

    @staticmethod
    def remove_strike(strike_id: int) -> bool:
        """Mark a strike as inactive (soft delete). Returns True if updated."""
        with get_cursor() as cursor:
            cursor.execute(
                "UPDATE strikes SET is_active = FALSE WHERE id = %s",
                (strike_id,)
            )
            return cursor.rowcount > 0

    @staticmethod
    def clear_strikes(guild_id: int, in_game_id: str) -> int:
        """Clear all active strikes for a player. Returns number cleared."""
        with get_cursor() as cursor:
            cursor.execute(
                """UPDATE strikes SET is_active = FALSE
                   WHERE guild_id = %s AND in_game_id = %s AND is_active = TRUE""",
                (guild_id, in_game_id)
            )
            count = cursor.rowcount
            if count > 0:
                logger.info(f"Cleared {count} strikes for {in_game_id} in guild {guild_id}")
            return count

    @staticmethod
    def search_by_name(guild_id: int, player_name: str) -> list:
        """Search for players by name (partial match)."""
        with get_cursor() as cursor:
            cursor.execute(
                """SELECT DISTINCT player_name, in_game_id,
                   (SELECT COUNT(*) FROM strikes s2
                    WHERE s2.guild_id = strikes.guild_id
                    AND s2.in_game_id = strikes.in_game_id
                    AND s2.is_active = TRUE) as strike_count
                   FROM strikes
                   WHERE guild_id = %s AND player_name LIKE %s
                   LIMIT 10""",
                (guild_id, f"%{player_name}%")
            )
            return cursor.fetchall()

    @staticmethod
    def is_banned(guild_id: int, in_game_id: str) -> bool:
        """Check if a player is currently banned."""
        with get_cursor() as cursor:
            cursor.execute(
                """SELECT id FROM bans
                   WHERE guild_id = %s AND in_game_id = %s AND unbanned_at IS NULL""",
                (guild_id, in_game_id)
            )
            return cursor.fetchone() is not None

    @staticmethod
    def add_ban(guild_id: int, player_name: str, in_game_id: str,
                reason: str, banned_by_id: int, banned_by_name: str,
                user_id: Optional[int] = None, banned_in_game: bool = False) -> dict:
        """Add a ban record for a player."""
        with get_cursor() as cursor:
            cursor.execute(
                """INSERT INTO bans
                   (guild_id, user_id, player_name, in_game_id, reason,
                    banned_by_id, banned_by_name, banned_in_game)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                (guild_id, user_id, player_name, in_game_id, reason,
                 banned_by_id, banned_by_name, banned_in_game)
            )
            ban_id = cursor.lastrowid

            logger.info(f"Banned {player_name} ({in_game_id}) in guild {guild_id}")

            return {
                'id': ban_id,
                'guild_id': guild_id,
                'player_name': player_name,
                'in_game_id': in_game_id,
                'reason': reason,
                'banned_in_game': banned_in_game
            }

    @staticmethod
    def mark_banned_in_game(guild_id: int, in_game_id: str) -> bool:
        """Mark that a player has been banned in-game."""
        with get_cursor() as cursor:
            cursor.execute(
                """UPDATE bans SET banned_in_game = TRUE
                   WHERE guild_id = %s AND in_game_id = %s AND unbanned_at IS NULL""",
                (guild_id, in_game_id)
            )
            return cursor.rowcount > 0

    @staticmethod
    def unban(guild_id: int, in_game_id: str, unbanned_by_id: int) -> bool:
        """Unban a player. Returns True if a ban was lifted."""
        with get_cursor() as cursor:
            cursor.execute(
                """UPDATE bans SET unbanned_at = NOW(), unbanned_by_id = %s
                   WHERE guild_id = %s AND in_game_id = %s AND unbanned_at IS NULL""",
                (unbanned_by_id, guild_id, in_game_id)
            )
            unbanned = cursor.rowcount > 0
            if unbanned:
                logger.info(f"Unbanned {in_game_id} in guild {guild_id}")
            return unbanned

    @staticmethod
    def get_ban(guild_id: int, in_game_id: str) -> dict | None:
        """Get active ban record for a player."""
        with get_cursor() as cursor:
            cursor.execute(
                """SELECT * FROM bans
                   WHERE guild_id = %s AND in_game_id = %s AND unbanned_at IS NULL""",
                (guild_id, in_game_id)
            )
            return cursor.fetchone()

    @staticmethod
    def get_all_bans(guild_id: int, include_unbanned: bool = False) -> list:
        """Get all bans for a guild."""
        with get_cursor() as cursor:
            if include_unbanned:
                cursor.execute(
                    "SELECT * FROM bans WHERE guild_id = %s ORDER BY banned_at DESC",
                    (guild_id,)
                )
            else:
                cursor.execute(
                    """SELECT * FROM bans
                       WHERE guild_id = %s AND unbanned_at IS NULL
                       ORDER BY banned_at DESC""",
                    (guild_id,)
                )
            return cursor.fetchall()

    @staticmethod
    def get_recent_strikes(guild_id: int, limit: int = 10) -> list:
        """Get most recent strikes in a guild."""
        with get_cursor() as cursor:
            cursor.execute(
                """SELECT * FROM strikes
                   WHERE guild_id = %s
                   ORDER BY created_at DESC
                   LIMIT %s""",
                (guild_id, limit)
            )
            return cursor.fetchall()
