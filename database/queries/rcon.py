# database/queries/rcon.py
"""
Database queries for RCON, Pterodactyl, and log monitoring.

Handles:
- RCON server configuration
- Pterodactyl connections and servers
- SFTP log configuration
- Verification codes
- Command audit logs
- Guild settings

Note: Sensitive credentials (passwords, API keys) are stored as plain text.
Database security should be handled at the infrastructure level.
"""

from database.connection import get_cursor
import logging
import secrets
import string
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)


class RCONServerQueries:
    """Database operations for RCON server management."""

    @staticmethod
    def add_server(guild_id: int, server_name: str, game_type: str,
                   host: str, port: int, password: str) -> int:
        """
        Add a new RCON server configuration.

        Returns:
            The new server's ID
        """
        with get_cursor() as cursor:
            # Check if this is the first server (make it default)
            cursor.execute(
                "SELECT COUNT(*) as count FROM rcon_servers WHERE guild_id = %s",
                (guild_id,)
            )
            is_first = cursor.fetchone()['count'] == 0

            cursor.execute(
                """INSERT INTO rcon_servers
                   (guild_id, server_name, game_type, host, port, password, is_default)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                (guild_id, server_name, game_type, host, port, password, is_first)
            )
            server_id = cursor.lastrowid
            logger.info(f"Added RCON server '{server_name}' for guild {guild_id}")
            return server_id

    @staticmethod
    def get_server(server_id: int, guild_id: int) -> Optional[dict]:
        """Get a specific RCON server."""
        with get_cursor() as cursor:
            cursor.execute(
                """SELECT * FROM rcon_servers
                   WHERE id = %s AND guild_id = %s""",
                (server_id, guild_id)
            )
            return cursor.fetchone()

    @staticmethod
    def get_servers(guild_id: int, active_only: bool = True) -> list:
        """Get all RCON servers for a guild."""
        with get_cursor() as cursor:
            query = "SELECT * FROM rcon_servers WHERE guild_id = %s"
            if active_only:
                query += " AND is_active = TRUE"
            query += " ORDER BY is_default DESC, server_name"

            cursor.execute(query, (guild_id,))
            return cursor.fetchall() or []

    @staticmethod
    def get_default_server(guild_id: int) -> Optional[dict]:
        """Get the default RCON server for a guild."""
        with get_cursor() as cursor:
            cursor.execute(
                """SELECT * FROM rcon_servers
                   WHERE guild_id = %s AND is_default = TRUE AND is_active = TRUE""",
                (guild_id,)
            )
            return cursor.fetchone()

    @staticmethod
    def get_server_by_name(guild_id: int, server_name: str) -> Optional[dict]:
        """Get RCON server by name."""
        with get_cursor() as cursor:
            cursor.execute(
                """SELECT * FROM rcon_servers
                   WHERE guild_id = %s AND server_name = %s""",
                (guild_id, server_name)
            )
            return cursor.fetchone()

    @staticmethod
    def set_default(guild_id: int, server_id: int) -> bool:
        """Set a server as the default for a guild."""
        with get_cursor() as cursor:
            # Unset current default
            cursor.execute(
                "UPDATE rcon_servers SET is_default = FALSE WHERE guild_id = %s",
                (guild_id,)
            )
            # Set new default
            cursor.execute(
                "UPDATE rcon_servers SET is_default = TRUE WHERE id = %s AND guild_id = %s",
                (server_id, guild_id)
            )
            return cursor.rowcount > 0

    @staticmethod
    def update_server(server_id: int, guild_id: int, **kwargs) -> bool:
        """Update server configuration. Supports: server_name, host, port, password, is_active."""
        if not kwargs:
            return False

        updates = []
        params = []

        valid_columns = ('server_name', 'host', 'port', 'password', 'is_active', 'game_type')
        for key, value in kwargs.items():
            if key in valid_columns:
                updates.append(f"{key} = %s")
                params.append(value)

        if not updates:
            return False

        params.extend([server_id, guild_id])
        with get_cursor() as cursor:
            cursor.execute(
                f"UPDATE rcon_servers SET {', '.join(updates)} WHERE id = %s AND guild_id = %s",
                params
            )
            return cursor.rowcount > 0

    @staticmethod
    def update_connection_status(server_id: int, success: bool, error: Optional[str] = None):
        """Update server's last connection status."""
        with get_cursor() as cursor:
            if success:
                cursor.execute(
                    "UPDATE rcon_servers SET last_connected_at = NOW(), last_error = NULL WHERE id = %s",
                    (server_id,)
                )
            else:
                cursor.execute(
                    "UPDATE rcon_servers SET last_error = %s WHERE id = %s",
                    (error, server_id)
                )

    @staticmethod
    def remove_server(server_id: int, guild_id: int) -> bool:
        """Remove an RCON server configuration."""
        with get_cursor() as cursor:
            cursor.execute(
                "DELETE FROM rcon_servers WHERE id = %s AND guild_id = %s",
                (server_id, guild_id)
            )
            deleted = cursor.rowcount > 0
            if deleted:
                logger.info(f"Removed RCON server {server_id} from guild {guild_id}")
            return deleted

    @staticmethod
    def count_servers(guild_id: int) -> int:
        """Count RCON servers for a guild."""
        with get_cursor() as cursor:
            cursor.execute(
                "SELECT COUNT(*) as count FROM rcon_servers WHERE guild_id = %s",
                (guild_id,)
            )
            return cursor.fetchone()['count']


class PterodactylQueries:
    """Database operations for Pterodactyl connections and servers."""

    @staticmethod
    def add_connection(guild_id: int, connection_name: str,
                       panel_url: str, api_key: str) -> int:
        """Add a new Pterodactyl connection."""
        with get_cursor() as cursor:
            cursor.execute(
                """INSERT INTO pterodactyl_connections
                   (guild_id, connection_name, panel_url, api_key)
                   VALUES (%s, %s, %s, %s)""",
                (guild_id, connection_name, panel_url, api_key)
            )
            connection_id = cursor.lastrowid
            logger.info(f"Added Pterodactyl connection '{connection_name}' for guild {guild_id}")
            return connection_id

    @staticmethod
    def get_connection(connection_id: int, guild_id: int) -> Optional[dict]:
        """Get a Pterodactyl connection."""
        with get_cursor() as cursor:
            cursor.execute(
                """SELECT * FROM pterodactyl_connections
                   WHERE id = %s AND guild_id = %s""",
                (connection_id, guild_id)
            )
            return cursor.fetchone()

    @staticmethod
    def get_connections(guild_id: int) -> list:
        """Get all Pterodactyl connections for a guild."""
        with get_cursor() as cursor:
            cursor.execute(
                """SELECT * FROM pterodactyl_connections
                   WHERE guild_id = %s AND is_active = TRUE
                   ORDER BY connection_name""",
                (guild_id,)
            )
            return cursor.fetchall() or []

    @staticmethod
    def remove_connection(connection_id: int, guild_id: int) -> bool:
        """Remove a Pterodactyl connection."""
        with get_cursor() as cursor:
            cursor.execute(
                "DELETE FROM pterodactyl_connections WHERE id = %s AND guild_id = %s",
                (connection_id, guild_id)
            )
            return cursor.rowcount > 0

    @staticmethod
    def update_connection_status(connection_id: int, success: bool, error: Optional[str] = None):
        """Update connection's last status."""
        with get_cursor() as cursor:
            if success:
                cursor.execute(
                    "UPDATE pterodactyl_connections SET last_connected_at = NOW(), last_error = NULL WHERE id = %s",
                    (connection_id,)
                )
            else:
                cursor.execute(
                    "UPDATE pterodactyl_connections SET last_error = %s WHERE id = %s",
                    (error, connection_id)
                )

    @staticmethod
    def add_discovered_server(connection_id: int, guild_id: int, server_id: str,
                              server_name: str, server_uuid: str = None,
                              game_type: str = 'unknown') -> int:
        """Add a server discovered from Pterodactyl API."""
        with get_cursor() as cursor:
            # Check if first server for this connection
            cursor.execute(
                "SELECT COUNT(*) as count FROM pterodactyl_servers WHERE connection_id = %s",
                (connection_id,)
            )
            is_first = cursor.fetchone()['count'] == 0

            cursor.execute(
                """INSERT INTO pterodactyl_servers
                   (connection_id, guild_id, server_id, server_name, server_uuid, game_type, is_default)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)
                   ON DUPLICATE KEY UPDATE
                       server_name = VALUES(server_name),
                       server_uuid = VALUES(server_uuid),
                       last_synced_at = NOW()""",
                (connection_id, guild_id, server_id, server_name, server_uuid, game_type, is_first)
            )
            return cursor.lastrowid

    @staticmethod
    def get_pterodactyl_servers(guild_id: int, connection_id: int = None) -> list:
        """Get Pterodactyl servers for a guild, optionally filtered by connection."""
        with get_cursor() as cursor:
            if connection_id:
                cursor.execute(
                    """SELECT ps.*, pc.panel_url, pc.api_key FROM pterodactyl_servers ps
                       JOIN pterodactyl_connections pc ON ps.connection_id = pc.id
                       WHERE ps.guild_id = %s AND ps.connection_id = %s AND ps.is_active = TRUE
                       ORDER BY ps.is_default DESC, ps.server_name""",
                    (guild_id, connection_id)
                )
            else:
                cursor.execute(
                    """SELECT ps.*, pc.panel_url, pc.api_key FROM pterodactyl_servers ps
                       JOIN pterodactyl_connections pc ON ps.connection_id = pc.id
                       WHERE ps.guild_id = %s AND ps.is_active = TRUE
                       ORDER BY ps.is_default DESC, ps.server_name""",
                    (guild_id,)
                )
            return cursor.fetchall() or []

    @staticmethod
    def get_server_with_connection(guild_id: int, server_identifier: str) -> Optional[dict]:
        """Get a Pterodactyl server by identifier (short ID) with its connection info."""
        with get_cursor() as cursor:
            cursor.execute(
                """SELECT ps.*, pc.panel_url, pc.api_key FROM pterodactyl_servers ps
                   JOIN pterodactyl_connections pc ON ps.connection_id = pc.id
                   WHERE ps.guild_id = %s AND ps.server_id = %s AND ps.is_active = TRUE""",
                (guild_id, server_identifier)
            )
            return cursor.fetchone()


class SFTPConfigQueries:
    """Database operations for SFTP log monitoring configuration."""

    @staticmethod
    def add_config(guild_id: int, config_name: str, host: str, port: int,
                   username: str, password: str, game_type: str = 'the_isle_evrima',
                   rcon_server_id: int = None, pterodactyl_server_id: int = None,
                   chat_log_path: str = None, kill_log_path: str = None,
                   admin_log_path: str = None) -> int:
        """Add SFTP configuration for log monitoring."""
        with get_cursor() as cursor:
            cursor.execute(
                """INSERT INTO server_sftp_config
                   (guild_id, config_name, host, port, username, password, game_type,
                    rcon_server_id, pterodactyl_server_id,
                    chat_log_path, kill_log_path, admin_log_path)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (guild_id, config_name, host, port, username, password, game_type,
                 rcon_server_id, pterodactyl_server_id,
                 chat_log_path, kill_log_path, admin_log_path)
            )
            logger.info(f"Added SFTP config '{config_name}' for guild {guild_id}")
            return cursor.lastrowid

    @staticmethod
    def get_config(config_id: int, guild_id: int) -> Optional[dict]:
        """Get SFTP config by ID."""
        with get_cursor() as cursor:
            cursor.execute(
                "SELECT * FROM server_sftp_config WHERE id = %s AND guild_id = %s",
                (config_id, guild_id)
            )
            return cursor.fetchone()

    @staticmethod
    def get_config_by_name(guild_id: int, config_name: str) -> Optional[dict]:
        """Get SFTP config by name."""
        with get_cursor() as cursor:
            cursor.execute(
                "SELECT * FROM server_sftp_config WHERE guild_id = %s AND config_name = %s",
                (guild_id, config_name)
            )
            return cursor.fetchone()

    @staticmethod
    def get_active_configs(guild_id: int) -> list:
        """Get all active SFTP configs for a guild."""
        with get_cursor() as cursor:
            cursor.execute(
                """SELECT * FROM server_sftp_config
                   WHERE guild_id = %s AND is_active = TRUE
                   ORDER BY config_name""",
                (guild_id,)
            )
            return cursor.fetchall() or []

    @staticmethod
    def update_log_path(config_id: int, guild_id: int, log_type: str, path: str) -> bool:
        """Update a log path. log_type: chat, kill, admin."""
        column_map = {
            'chat': 'chat_log_path',
            'kill': 'kill_log_path',
            'admin': 'admin_log_path'
        }
        if log_type not in column_map:
            return False

        with get_cursor() as cursor:
            cursor.execute(
                f"UPDATE server_sftp_config SET {column_map[log_type]} = %s WHERE id = %s AND guild_id = %s",
                (path, config_id, guild_id)
            )
            return cursor.rowcount > 0

    @staticmethod
    def remove_config(config_id: int, guild_id: int) -> bool:
        """Remove SFTP configuration."""
        with get_cursor() as cursor:
            cursor.execute(
                "DELETE FROM server_sftp_config WHERE id = %s AND guild_id = %s",
                (config_id, guild_id)
            )
            return cursor.rowcount > 0


class LogMonitorStateQueries:
    """Database operations for log monitor state tracking."""

    @staticmethod
    def get_state(sftp_config_id: int, log_type: str) -> Optional[dict]:
        """Get current monitor state for a log file."""
        with get_cursor() as cursor:
            cursor.execute(
                """SELECT * FROM log_monitor_state
                   WHERE sftp_config_id = %s AND log_type = %s""",
                (sftp_config_id, log_type)
            )
            return cursor.fetchone()

    @staticmethod
    def update_state(sftp_config_id: int, log_type: str, file_path: str,
                     position: int, line_hash: str = None):
        """Update or create monitor state."""
        with get_cursor() as cursor:
            cursor.execute(
                """INSERT INTO log_monitor_state
                   (sftp_config_id, log_type, file_path, last_position, last_line_hash, last_read_at)
                   VALUES (%s, %s, %s, %s, %s, NOW())
                   ON DUPLICATE KEY UPDATE
                       file_path = VALUES(file_path),
                       last_position = VALUES(last_position),
                       last_line_hash = VALUES(last_line_hash),
                       last_read_at = NOW()""",
                (sftp_config_id, log_type, file_path, position, line_hash)
            )


class LogChannelQueries:
    """Database operations for log channel assignments."""

    @staticmethod
    def get_channels(guild_id: int) -> Optional[dict]:
        """Get log channel assignments for a guild."""
        with get_cursor() as cursor:
            cursor.execute(
                "SELECT * FROM guild_log_channels WHERE guild_id = %s",
                (guild_id,)
            )
            return cursor.fetchone()

    @staticmethod
    def set_channel(guild_id: int, channel_type: str, channel_id: int):
        """Set a log channel. channel_type: chatlog, killfeed, adminlog, link, restart."""
        column_name = f"{channel_type}_channel_id"
        valid_columns = ['chatlog_channel_id', 'killfeed_channel_id', 'adminlog_channel_id',
                         'link_channel_id', 'restart_channel_id']

        if column_name not in valid_columns:
            raise ValueError(f"Invalid channel type: {channel_type}")

        with get_cursor() as cursor:
            cursor.execute(
                f"""INSERT INTO guild_log_channels (guild_id, {column_name})
                    VALUES (%s, %s)
                    ON DUPLICATE KEY UPDATE {column_name} = VALUES({column_name})""",
                (guild_id, channel_id)
            )


class VerificationCodeQueries:
    """Database operations for RCON verification codes."""

    @staticmethod
    def create_code(guild_id: int, user_id: int, game_type: str,
                    target_steam_id: str = None, target_alderon_id: str = None,
                    server_id: int = None, timeout_minutes: int = 10) -> str:
        """
        Create a new verification code.

        Returns:
            The generated verification code (6 characters, alphanumeric)
        """
        # Generate 6-character code
        code = ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(6))
        expires_at = datetime.now() + timedelta(minutes=timeout_minutes)

        with get_cursor() as cursor:
            # Delete any existing codes for this user
            cursor.execute(
                "DELETE FROM rcon_verification_codes WHERE guild_id = %s AND user_id = %s AND verified_at IS NULL",
                (guild_id, user_id)
            )

            cursor.execute(
                """INSERT INTO rcon_verification_codes
                   (guild_id, user_id, verification_code, game_type,
                    target_steam_id, target_alderon_id, server_id, expires_at)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                (guild_id, user_id, code, game_type,
                 target_steam_id, target_alderon_id, server_id, expires_at)
            )
            return code

    @staticmethod
    def verify_code(guild_id: int, code: str) -> Optional[dict]:
        """
        Verify a code and return the verification record if valid.
        Increments attempt counter. Returns None if invalid/expired.
        """
        with get_cursor() as cursor:
            cursor.execute(
                """SELECT * FROM rcon_verification_codes
                   WHERE guild_id = %s AND verification_code = %s
                   AND verified_at IS NULL AND expires_at > NOW()""",
                (guild_id, code)
            )
            record = cursor.fetchone()

            if not record:
                return None

            # Check attempts
            if record['attempts'] >= record['max_attempts']:
                return None

            # Increment attempts
            cursor.execute(
                "UPDATE rcon_verification_codes SET attempts = attempts + 1 WHERE id = %s",
                (record['id'],)
            )

            return record

    @staticmethod
    def mark_verified(code_id: int):
        """Mark a verification code as verified."""
        with get_cursor() as cursor:
            cursor.execute(
                "UPDATE rcon_verification_codes SET verified_at = NOW() WHERE id = %s",
                (code_id,)
            )

    @staticmethod
    def cleanup_expired():
        """Delete expired verification codes."""
        with get_cursor() as cursor:
            cursor.execute(
                "DELETE FROM rcon_verification_codes WHERE expires_at < NOW()"
            )
            return cursor.rowcount


class RCONCommandLogQueries:
    """Database operations for RCON command audit logs."""

    @staticmethod
    def log_command(guild_id: int, command_type: str, executed_by_id: int,
                    success: bool, server_id: int = None, target_player_id: str = None,
                    command_data: dict = None, response_message: str = None):
        """Log an RCON command execution."""
        import json
        with get_cursor() as cursor:
            cursor.execute(
                """INSERT INTO rcon_command_log
                   (guild_id, server_id, command_type, target_player_id,
                    executed_by_id, command_data, success, response_message)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                (guild_id, server_id, command_type, target_player_id,
                 executed_by_id, json.dumps(command_data) if command_data else None,
                 success, response_message)
            )

    @staticmethod
    def get_recent_commands(guild_id: int, limit: int = 50) -> list:
        """Get recent command logs for a guild."""
        with get_cursor() as cursor:
            cursor.execute(
                """SELECT cl.*, rs.server_name
                   FROM rcon_command_log cl
                   LEFT JOIN rcon_servers rs ON cl.server_id = rs.id
                   WHERE cl.guild_id = %s
                   ORDER BY cl.executed_at DESC
                   LIMIT %s""",
                (guild_id, limit)
            )
            return cursor.fetchall() or []


class GuildRCONSettingsQueries:
    """Database operations for guild RCON settings."""

    @staticmethod
    def get_settings(guild_id: int) -> Optional[dict]:
        """Get RCON settings for a guild."""
        with get_cursor() as cursor:
            cursor.execute(
                "SELECT * FROM guild_rcon_settings WHERE guild_id = %s",
                (guild_id,)
            )
            return cursor.fetchone()

    @staticmethod
    def get_or_create_settings(guild_id: int) -> dict:
        """Get or create RCON settings for a guild."""
        settings = GuildRCONSettingsQueries.get_settings(guild_id)
        if settings:
            return settings

        with get_cursor() as cursor:
            cursor.execute(
                "INSERT INTO guild_rcon_settings (guild_id) VALUES (%s)",
                (guild_id,)
            )
            return GuildRCONSettingsQueries.get_settings(guild_id)

    @staticmethod
    def update_settings(guild_id: int, **kwargs) -> bool:
        """Update RCON settings. Supports all columns except guild_id."""
        if not kwargs:
            return False

        valid_columns = [
            'auto_kick_enabled', 'auto_kick_strike_threshold',
            'auto_ban_enabled', 'auto_ban_strike_threshold',
            'verification_enabled', 'verification_timeout_minutes',
            'log_monitoring_enabled', 'log_poll_interval_seconds',
            'max_log_monitors', 'ptero_whitelist_role_id'
        ]

        updates = []
        params = []
        for key, value in kwargs.items():
            if key in valid_columns:
                updates.append(f"{key} = %s")
                params.append(value)

        if not updates:
            return False

        params.append(guild_id)
        with get_cursor() as cursor:
            cursor.execute(
                f"""INSERT INTO guild_rcon_settings (guild_id) VALUES (%s)
                    ON DUPLICATE KEY UPDATE {', '.join(updates)}""",
                [guild_id] + params[:-1]
            )
            return True
