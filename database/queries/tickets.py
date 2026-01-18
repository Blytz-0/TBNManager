# database/queries/tickets.py
"""Ticket system database queries"""

from database.connection import get_cursor
from typing import Optional
from datetime import datetime
import json
import logging

logger = logging.getLogger(__name__)


class TicketQueries:
    """Database operations for the ticket system."""

    # ==========================================
    # TICKET PANEL OPERATIONS
    # ==========================================

    @staticmethod
    def create_panel(guild_id: int, channel_id: int, title: str = "Support Tickets",
                     description: str = None, button_label: str = "Open Ticket",
                     button_emoji: str = "🎫", ticket_category_id: int = None,
                     transcript_channel_id: int = None, support_role_id: int = None,
                     welcome_message: str = None) -> dict:
        """Create a new ticket panel."""
        with get_cursor() as cursor:
            cursor.execute(
                """INSERT INTO ticket_panels
                   (guild_id, channel_id, title, description, button_label,
                    button_emoji, ticket_category_id, transcript_channel_id,
                    support_role_id, welcome_message)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (guild_id, channel_id, title, description, button_label,
                 button_emoji, ticket_category_id, transcript_channel_id,
                 support_role_id, welcome_message)
            )
            panel_id = cursor.lastrowid
            logger.info(f"Created ticket panel {panel_id} in guild {guild_id}")
            return {
                'id': panel_id,
                'guild_id': guild_id,
                'channel_id': channel_id,
                'title': title
            }

    @staticmethod
    def update_panel_message(panel_id: int, message_id: int) -> bool:
        """Update the message ID for a panel after sending it."""
        with get_cursor() as cursor:
            cursor.execute(
                "UPDATE ticket_panels SET message_id = %s WHERE id = %s",
                (message_id, panel_id)
            )
            return cursor.rowcount > 0

    @staticmethod
    def get_panel(panel_id: int) -> dict | None:
        """Get a ticket panel by ID."""
        with get_cursor() as cursor:
            cursor.execute(
                "SELECT * FROM ticket_panels WHERE id = %s",
                (panel_id,)
            )
            return cursor.fetchone()

    @staticmethod
    def get_panel_by_message(message_id: int) -> dict | None:
        """Get a ticket panel by its message ID."""
        with get_cursor() as cursor:
            cursor.execute(
                "SELECT * FROM ticket_panels WHERE message_id = %s",
                (message_id,)
            )
            return cursor.fetchone()

    @staticmethod
    def get_guild_panels(guild_id: int) -> list:
        """Get all ticket panels for a guild."""
        with get_cursor() as cursor:
            cursor.execute(
                "SELECT * FROM ticket_panels WHERE guild_id = %s ORDER BY created_at DESC",
                (guild_id,)
            )
            return cursor.fetchall()

    @staticmethod
    def delete_panel(panel_id: int) -> bool:
        """Delete a ticket panel."""
        with get_cursor() as cursor:
            cursor.execute("DELETE FROM ticket_panels WHERE id = %s", (panel_id,))
            return cursor.rowcount > 0

    # ==========================================
    # TICKET OPERATIONS
    # ==========================================

    @staticmethod
    def create_ticket(guild_id: int, user_id: int, username: str,
                      channel_id: int = None, panel_id: int = None,
                      subject: str = None) -> dict:
        """Create a new ticket."""
        with get_cursor() as cursor:
            # Get next ticket number for this guild
            cursor.execute(
                "SELECT COALESCE(MAX(ticket_number), 0) + 1 FROM tickets WHERE guild_id = %s",
                (guild_id,)
            )
            ticket_number = cursor.fetchone()['COALESCE(MAX(ticket_number), 0) + 1']

            cursor.execute(
                """INSERT INTO tickets
                   (ticket_number, guild_id, channel_id, user_id, username,
                    panel_id, subject, status)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, 'open')""",
                (ticket_number, guild_id, channel_id, user_id, username,
                 panel_id, subject)
            )
            ticket_id = cursor.lastrowid

            logger.info(f"Created ticket #{ticket_number} for {username} in guild {guild_id}")
            return {
                'id': ticket_id,
                'ticket_number': ticket_number,
                'guild_id': guild_id,
                'channel_id': channel_id,
                'user_id': user_id,
                'username': username,
                'status': 'open'
            }

    @staticmethod
    def update_ticket_channel(ticket_id: int, channel_id: int) -> bool:
        """Update the channel ID for a ticket after creating it."""
        with get_cursor() as cursor:
            cursor.execute(
                "UPDATE tickets SET channel_id = %s WHERE id = %s",
                (channel_id, ticket_id)
            )
            return cursor.rowcount > 0

    @staticmethod
    def get_ticket(ticket_id: int) -> dict | None:
        """Get a ticket by ID."""
        with get_cursor() as cursor:
            cursor.execute("SELECT * FROM tickets WHERE id = %s", (ticket_id,))
            return cursor.fetchone()

    @staticmethod
    def get_ticket_by_channel(channel_id: int) -> dict | None:
        """Get a ticket by its channel ID."""
        with get_cursor() as cursor:
            cursor.execute(
                "SELECT * FROM tickets WHERE channel_id = %s",
                (channel_id,)
            )
            return cursor.fetchone()

    @staticmethod
    def get_ticket_by_number(guild_id: int, ticket_number: int) -> dict | None:
        """Get a ticket by its guild-specific number."""
        with get_cursor() as cursor:
            cursor.execute(
                "SELECT * FROM tickets WHERE guild_id = %s AND ticket_number = %s",
                (guild_id, ticket_number)
            )
            return cursor.fetchone()

    @staticmethod
    def get_user_open_tickets(guild_id: int, user_id: int) -> list:
        """Get all open tickets for a user in a guild."""
        with get_cursor() as cursor:
            cursor.execute(
                """SELECT * FROM tickets
                   WHERE guild_id = %s AND user_id = %s AND status != 'closed'
                   ORDER BY opened_at DESC""",
                (guild_id, user_id)
            )
            return cursor.fetchall()

    @staticmethod
    def get_open_tickets(guild_id: int, limit: int = 50) -> list:
        """Get all open tickets for a guild."""
        with get_cursor() as cursor:
            cursor.execute(
                """SELECT * FROM tickets
                   WHERE guild_id = %s AND status != 'closed'
                   ORDER BY opened_at ASC
                   LIMIT %s""",
                (guild_id, limit)
            )
            return cursor.fetchall()

    @staticmethod
    def get_recent_tickets(guild_id: int, limit: int = 20) -> list:
        """Get recent tickets for a guild (including closed)."""
        with get_cursor() as cursor:
            cursor.execute(
                """SELECT * FROM tickets
                   WHERE guild_id = %s
                   ORDER BY opened_at DESC
                   LIMIT %s""",
                (guild_id, limit)
            )
            return cursor.fetchall()

    @staticmethod
    def claim_ticket(ticket_id: int, claimed_by_id: int, claimed_by_name: str) -> bool:
        """Claim a ticket."""
        with get_cursor() as cursor:
            cursor.execute(
                """UPDATE tickets
                   SET status = 'claimed', claimed_by_id = %s,
                       claimed_by_name = %s, claimed_at = NOW()
                   WHERE id = %s AND status = 'open'""",
                (claimed_by_id, claimed_by_name, ticket_id)
            )
            return cursor.rowcount > 0

    @staticmethod
    def unclaim_ticket(ticket_id: int) -> bool:
        """Unclaim a ticket."""
        with get_cursor() as cursor:
            cursor.execute(
                """UPDATE tickets
                   SET status = 'open', claimed_by_id = NULL,
                       claimed_by_name = NULL, claimed_at = NULL
                   WHERE id = %s AND status = 'claimed'""",
                (ticket_id,)
            )
            return cursor.rowcount > 0

    @staticmethod
    def close_ticket(ticket_id: int, closed_by_id: int, closed_by_name: str,
                     reason: str = None) -> bool:
        """Close a ticket."""
        with get_cursor() as cursor:
            cursor.execute(
                """UPDATE tickets
                   SET status = 'closed', closed_by_id = %s,
                       closed_by_name = %s, close_reason = %s, closed_at = NOW()
                   WHERE id = %s AND status != 'closed'""",
                (closed_by_id, closed_by_name, reason, ticket_id)
            )
            if cursor.rowcount > 0:
                logger.info(f"Closed ticket {ticket_id} by {closed_by_name}")
                return True
            return False

    @staticmethod
    def set_transcript(ticket_id: int, message_id: int) -> bool:
        """Mark ticket as having a transcript and store message ID."""
        with get_cursor() as cursor:
            cursor.execute(
                """UPDATE tickets
                   SET has_transcript = TRUE, transcript_message_id = %s
                   WHERE id = %s""",
                (message_id, ticket_id)
            )
            return cursor.rowcount > 0

    # ==========================================
    # TICKET MESSAGE OPERATIONS
    # ==========================================

    @staticmethod
    def add_message(ticket_id: int, message_id: int, user_id: int,
                    username: str, content: str = None,
                    attachments: list = None, embeds: list = None) -> dict:
        """Add a message to a ticket."""
        with get_cursor() as cursor:
            cursor.execute(
                """INSERT INTO ticket_messages
                   (ticket_id, message_id, user_id, username, content, attachments, embeds)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                (ticket_id, message_id, user_id, username, content,
                 json.dumps(attachments) if attachments else None,
                 json.dumps(embeds) if embeds else None)
            )
            return {
                'id': cursor.lastrowid,
                'ticket_id': ticket_id,
                'message_id': message_id,
                'content': content
            }

    @staticmethod
    def get_ticket_messages(ticket_id: int) -> list:
        """Get all messages for a ticket (for transcript)."""
        with get_cursor() as cursor:
            cursor.execute(
                """SELECT * FROM ticket_messages
                   WHERE ticket_id = %s AND deleted = FALSE
                   ORDER BY created_at ASC""",
                (ticket_id,)
            )
            messages = cursor.fetchall()
            # Parse JSON fields
            for msg in messages:
                if msg.get('attachments'):
                    msg['attachments'] = json.loads(msg['attachments'])
                if msg.get('embeds'):
                    msg['embeds'] = json.loads(msg['embeds'])
            return messages

    @staticmethod
    def mark_message_deleted(message_id: int) -> bool:
        """Mark a message as deleted."""
        with get_cursor() as cursor:
            cursor.execute(
                "UPDATE ticket_messages SET deleted = TRUE WHERE message_id = %s",
                (message_id,)
            )
            return cursor.rowcount > 0

    @staticmethod
    def update_message(message_id: int, content: str) -> bool:
        """Update a message content (for edits)."""
        with get_cursor() as cursor:
            cursor.execute(
                """UPDATE ticket_messages
                   SET content = %s, edited_at = NOW()
                   WHERE message_id = %s""",
                (content, message_id)
            )
            return cursor.rowcount > 0

    # ==========================================
    # TICKET PARTICIPANT OPERATIONS
    # ==========================================

    @staticmethod
    def add_participant(ticket_id: int, user_id: int, username: str,
                        added_by_id: int = None) -> bool:
        """Add a participant to a ticket."""
        with get_cursor() as cursor:
            try:
                cursor.execute(
                    """INSERT INTO ticket_participants
                       (ticket_id, user_id, username, added_by_id)
                       VALUES (%s, %s, %s, %s)""",
                    (ticket_id, user_id, username, added_by_id)
                )
                return True
            except Exception:
                return False  # Already exists

    @staticmethod
    def remove_participant(ticket_id: int, user_id: int) -> bool:
        """Remove a participant from a ticket."""
        with get_cursor() as cursor:
            cursor.execute(
                "DELETE FROM ticket_participants WHERE ticket_id = %s AND user_id = %s",
                (ticket_id, user_id)
            )
            return cursor.rowcount > 0

    @staticmethod
    def get_ticket_participants(ticket_id: int) -> list:
        """Get all participants in a ticket."""
        with get_cursor() as cursor:
            cursor.execute(
                "SELECT * FROM ticket_participants WHERE ticket_id = %s",
                (ticket_id,)
            )
            return cursor.fetchall()

    # ==========================================
    # STATISTICS
    # ==========================================

    @staticmethod
    def get_ticket_stats(guild_id: int) -> dict:
        """Get ticket statistics for a guild."""
        with get_cursor() as cursor:
            cursor.execute(
                """SELECT
                       COUNT(*) as total,
                       SUM(CASE WHEN status = 'open' THEN 1 ELSE 0 END) as open_count,
                       SUM(CASE WHEN status = 'claimed' THEN 1 ELSE 0 END) as claimed_count,
                       SUM(CASE WHEN status = 'closed' THEN 1 ELSE 0 END) as closed_count
                   FROM tickets WHERE guild_id = %s""",
                (guild_id,)
            )
            return cursor.fetchone()
