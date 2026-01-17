# database/queries/audit.py
"""Audit log database queries"""

from database.connection import get_cursor
from typing import Optional
import json
import logging

logger = logging.getLogger(__name__)


class AuditQueries:
    """Database operations for audit logging."""

    # Action type constants
    ACTION_STRIKE_ADDED = 'strike_added'
    ACTION_STRIKE_REMOVED = 'strike_removed'
    ACTION_STRIKES_CLEARED = 'strikes_cleared'
    ACTION_BAN = 'ban'
    ACTION_UNBAN = 'unban'
    ACTION_BAN_INGAME = 'ban_ingame_confirmed'
    ACTION_PLAYER_LINKED = 'player_linked'
    ACTION_PLAYER_UNLINKED = 'player_unlinked'
    ACTION_CONFIG_CHANGE = 'config_change'
    ACTION_FEATURE_TOGGLE = 'feature_toggle'
    ACTION_ROLE_MESSAGE = 'role_message_created'

    @staticmethod
    def log(guild_id: int, action_type: str, performed_by_id: int,
            performed_by_name: str, target_user_id: Optional[int] = None,
            target_player_name: Optional[str] = None,
            details: Optional[dict] = None):
        """
        Log an action to the audit log.

        Args:
            guild_id: The Discord guild ID
            action_type: One of the ACTION_* constants
            performed_by_id: Discord ID of user who performed the action
            performed_by_name: Name of user who performed the action
            target_user_id: Discord ID of target user (if applicable)
            target_player_name: Player name of target (if applicable)
            details: Additional JSON details about the action
        """
        with get_cursor() as cursor:
            cursor.execute(
                """INSERT INTO audit_log
                   (guild_id, action_type, target_user_id, target_player_name,
                    performed_by_id, performed_by_name, details)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                (guild_id, action_type, target_user_id, target_player_name,
                 performed_by_id, performed_by_name,
                 json.dumps(details) if details else None)
            )
            logger.debug(f"Audit log: {action_type} by {performed_by_name} in guild {guild_id}")

    @staticmethod
    def get_recent(guild_id: int, limit: int = 50) -> list:
        """Get recent audit log entries for a guild."""
        with get_cursor() as cursor:
            cursor.execute(
                """SELECT * FROM audit_log
                   WHERE guild_id = %s
                   ORDER BY created_at DESC
                   LIMIT %s""",
                (guild_id, limit)
            )
            results = cursor.fetchall()

            # Parse JSON details
            for row in results:
                if row.get('details'):
                    try:
                        row['details'] = json.loads(row['details'])
                    except json.JSONDecodeError:
                        pass

            return results

    @staticmethod
    def get_by_action(guild_id: int, action_type: str, limit: int = 50) -> list:
        """Get audit entries filtered by action type."""
        with get_cursor() as cursor:
            cursor.execute(
                """SELECT * FROM audit_log
                   WHERE guild_id = %s AND action_type = %s
                   ORDER BY created_at DESC
                   LIMIT %s""",
                (guild_id, action_type, limit)
            )
            return cursor.fetchall()

    @staticmethod
    def get_by_user(guild_id: int, user_id: int, limit: int = 50) -> list:
        """Get audit entries for actions performed by a specific user."""
        with get_cursor() as cursor:
            cursor.execute(
                """SELECT * FROM audit_log
                   WHERE guild_id = %s AND performed_by_id = %s
                   ORDER BY created_at DESC
                   LIMIT %s""",
                (guild_id, user_id, limit)
            )
            return cursor.fetchall()

    @staticmethod
    def get_for_target(guild_id: int, target_user_id: int = None,
                       target_player_name: str = None, limit: int = 50) -> list:
        """Get audit entries for actions targeting a specific user/player."""
        with get_cursor() as cursor:
            if target_user_id:
                cursor.execute(
                    """SELECT * FROM audit_log
                       WHERE guild_id = %s AND target_user_id = %s
                       ORDER BY created_at DESC
                       LIMIT %s""",
                    (guild_id, target_user_id, limit)
                )
            elif target_player_name:
                cursor.execute(
                    """SELECT * FROM audit_log
                       WHERE guild_id = %s AND target_player_name = %s
                       ORDER BY created_at DESC
                       LIMIT %s""",
                    (guild_id, target_player_name, limit)
                )
            else:
                return []

            return cursor.fetchall()

    @staticmethod
    def search(guild_id: int, query: str, limit: int = 50) -> list:
        """Search audit log by player name or performer name."""
        search_pattern = f"%{query}%"
        with get_cursor() as cursor:
            cursor.execute(
                """SELECT * FROM audit_log
                   WHERE guild_id = %s
                   AND (target_player_name LIKE %s OR performed_by_name LIKE %s)
                   ORDER BY created_at DESC
                   LIMIT %s""",
                (guild_id, search_pattern, search_pattern, limit)
            )
            return cursor.fetchall()

    @staticmethod
    def count_actions(guild_id: int, action_type: str = None,
                      days: int = 30) -> int:
        """Count actions in the last N days, optionally filtered by type."""
        with get_cursor() as cursor:
            if action_type:
                cursor.execute(
                    """SELECT COUNT(*) as count FROM audit_log
                       WHERE guild_id = %s AND action_type = %s
                       AND created_at >= DATE_SUB(NOW(), INTERVAL %s DAY)""",
                    (guild_id, action_type, days)
                )
            else:
                cursor.execute(
                    """SELECT COUNT(*) as count FROM audit_log
                       WHERE guild_id = %s
                       AND created_at >= DATE_SUB(NOW(), INTERVAL %s DAY)""",
                    (guild_id, days)
                )

            result = cursor.fetchone()
            return result['count'] if result else 0
