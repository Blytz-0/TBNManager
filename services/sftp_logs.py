# services/sftp_logs.py
"""
SFTP-based log file monitoring for game servers.

Supports reading and parsing game logs for:
- The Isle Evrima: Chat, kills, admin actions
- Path of Titans: Chat, kills, admin actions

Uses paramiko for SFTP connections with incremental reading
(only reads new lines since last poll).
"""

import asyncio
import hashlib
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional, Callable, Any

logger = logging.getLogger(__name__)

# Import enhanced parser
try:
    from services.log_parsers import (
        get_parser as get_enhanced_parser,
        LogType as EnhancedLogType,
        PlayerLoginEvent,
        PlayerLogoutEvent,
        PlayerChatEvent,
        AdminCommandEvent,
        RCONCommandEvent,
        PlayerDeathEvent
    )
    ENHANCED_PARSER_AVAILABLE = True
except ImportError:
    ENHANCED_PARSER_AVAILABLE = False
    logger.warning("Enhanced log parser not available")


class LogType(Enum):
    """Types of game logs."""
    CHAT = "chat"
    KILL = "kill"
    ADMIN = "admin"


class GameLogType(Enum):
    """Supported game log formats."""
    THE_ISLE_EVRIMA = "the_isle_evrima"
    PATH_OF_TITANS = "path_of_titans"


@dataclass
class LogEntry:
    """Parsed log entry."""
    log_type: LogType
    timestamp: datetime
    raw_line: str
    parsed_data: dict


@dataclass
class ChatLogEntry(LogEntry):
    """Parsed chat log entry."""
    player_name: str
    player_id: str
    message: str
    channel: str  # Global, Local, Group, etc.


@dataclass
class KillLogEntry(LogEntry):
    """Parsed kill log entry."""
    killer_name: str
    killer_id: str
    victim_name: str
    victim_id: str
    weapon: Optional[str] = None
    distance: Optional[float] = None


@dataclass
class AdminLogEntry(LogEntry):
    """Parsed admin action log entry."""
    admin_name: str
    admin_id: str
    action: str
    target: Optional[str] = None
    details: Optional[str] = None


class SFTPError(Exception):
    """Base exception for SFTP errors."""
    pass


class SFTPConnectionError(SFTPError):
    """Failed to connect to SFTP server."""
    pass


class SFTPAuthError(SFTPError):
    """SFTP authentication failed."""
    pass


class LogParser:
    """
    Base class for game log parsers.

    Override _parse_chat, _parse_kill, _parse_admin for specific games.
    """

    def __init__(self, game_type: GameLogType):
        self.game_type = game_type

    def parse_line(self, line: str, log_type: LogType) -> Optional[LogEntry]:
        """Parse a log line into a LogEntry."""
        line = line.strip()
        if not line:
            return None

        try:
            if log_type == LogType.CHAT:
                return self._parse_chat(line)
            elif log_type == LogType.KILL:
                return self._parse_kill(line)
            elif log_type == LogType.ADMIN:
                return self._parse_admin(line)
        except Exception as e:
            logger.debug(f"Failed to parse log line: {e}")
            return None

        return None

    def _parse_chat(self, line: str) -> Optional[ChatLogEntry]:
        """Parse a chat log line. Override in subclass."""
        return None

    def _parse_kill(self, line: str) -> Optional[KillLogEntry]:
        """Parse a kill log line. Override in subclass."""
        return None

    def _parse_admin(self, line: str) -> Optional[AdminLogEntry]:
        """Parse an admin log line. Override in subclass."""
        return None

    def _parse_timestamp(self, timestamp_str: str) -> datetime:
        """Parse timestamp from log line."""
        # Default format: [2024.01.22-15.30.45]
        try:
            clean = timestamp_str.strip('[]')
            return datetime.strptime(clean, "%Y.%m.%d-%H.%M.%S")
        except ValueError:
            return datetime.now()


class EvrimaLogParser(LogParser):
    """
    Log parser for The Isle Evrima unified log file.

    Reads a single log file and auto-detects log types:
    - Chat: LogTheIsleChatData: [timestamp] [Channel] [GROUP-id] PlayerName [SteamID]: message
    - Commands: LogTheIsleCommandData: [timestamp] Player [SteamID] used command: ...
    - Joins/Leaves: LogTheIsleJoinData: [timestamp] Player [SteamID] Joined/Left The Server
    - Kills: LogTheIsleKills: [timestamp] PlayerA [SteamID] killed PlayerB [SteamID]
    """

    # Regex patterns - Updated to match actual The Isle log format
    TIMESTAMP_PATTERN = re.compile(r'\[(\d{4}\.\d{2}\.\d{2}-\d{2}\.\d{2}\.\d{2}(?:\.\d{3})?)\]')

    # Chat: LogTheIsleChatData: [timestamp] [Spatial] [GROUP-id] PlayerName [SteamID]: message
    CHAT_PATTERN = re.compile(
        r'LogTheIsleChatData:\s*\[[\d.\-:]+\]\s*\[(\w+)\]\s*\[GROUP-\d+\]\s*(.+?)\s*\[(\d{17})\]:\s*(.+)$'
    )

    # Kill: LogTheIsleKills: [timestamp] PlayerA [SteamID] killed PlayerB [SteamID]
    KILL_PATTERN = re.compile(
        r'LogTheIsleKills:\s*\[[\d.\-:]+\]\s*(.+?)\s*\[(\d{17})\]\s*killed\s*(.+?)\s*\[(\d{17})\]'
    )

    # Admin commands: LogTheIsleCommandData: [timestamp] Player [SteamID] used command: CommandName
    ADMIN_PATTERN = re.compile(
        r'LogTheIsleCommandData:\s*\[[\d.\-:]+\]\s*(.+?)\s*\[(\d{17})\]\s*used command:\s*(.+)$'
    )

    # RCON commands: LogTheIsleCommandData: [timestamp] RCON Command Used [Action] : details
    RCON_PATTERN = re.compile(
        r'LogTheIsleCommandData:\s*\[[\d.\-:]+\]\s*RCON Command Used\s*\[([^\]]+)\]\s*:\s*(.*)$'
    )

    # Join: LogTheIsleJoinData: [timestamp] Player [SteamID] Joined The Server
    JOIN_PATTERN = re.compile(
        r'LogTheIsleJoinData:\s*\[[\d.\-:]+\]\s*(.+?)\s*\[(\d{17})\]\s*Joined The Server'
    )

    # Leave: LogTheIsleJoinData: [timestamp] Player [SteamID] Left The Server
    LEAVE_PATTERN = re.compile(
        r'LogTheIsleJoinData:\s*\[[\d.\-:]+\]\s*(.+?)\s*\[(\d{17})\]\s*Left The Server'
    )

    def __init__(self):
        super().__init__(GameLogType.THE_ISLE_EVRIMA)

    def parse_any_line(self, line: str) -> Optional[LogEntry]:
        """
        Parse any line from the unified log file.
        Auto-detects log type and routes to appropriate parser.
        """
        line = line.strip()
        if not line:
            return None

        # Detect log type from line content
        if 'LogTheIsleChatData:' in line:
            return self._parse_chat(line)
        elif 'LogTheIsleKills:' in line:
            return self._parse_kill(line)
        elif 'LogTheIsleCommandData:' in line:
            return self._parse_admin(line)
        elif 'LogTheIsleJoinData:' in line and ('Joined The Server' in line or 'Left The Server' in line):
            return self._parse_join_leave(line)

        return None

    def _parse_chat(self, line: str) -> Optional[ChatLogEntry]:
        """Parse Evrima chat log line."""
        ts_match = self.TIMESTAMP_PATTERN.search(line)
        chat_match = self.CHAT_PATTERN.search(line)

        if not chat_match:
            return None

        timestamp = self._parse_timestamp(ts_match.group(1)) if ts_match else datetime.now()
        channel = chat_match.group(1)  # Spatial, Admin, Global, etc.
        player_name = chat_match.group(2)
        player_id = chat_match.group(3)
        message = chat_match.group(4)

        return ChatLogEntry(
            log_type=LogType.CHAT,
            timestamp=timestamp,
            raw_line=line,
            parsed_data={},
            player_name=player_name,
            player_id=player_id,
            message=message,
            channel=channel
        )

    def _parse_kill(self, line: str) -> Optional[KillLogEntry]:
        """Parse Evrima kill log line."""
        ts_match = self.TIMESTAMP_PATTERN.search(line)
        kill_match = self.KILL_PATTERN.search(line)

        if not kill_match:
            return None

        timestamp = self._parse_timestamp(ts_match.group(1)) if ts_match else datetime.now()

        return KillLogEntry(
            log_type=LogType.KILL,
            timestamp=timestamp,
            raw_line=line,
            parsed_data={},
            killer_name=kill_match.group(1),
            killer_id=kill_match.group(2),
            victim_name=kill_match.group(3),
            victim_id=kill_match.group(4)
        )

    def _parse_admin(self, line: str) -> Optional[AdminLogEntry]:
        """Parse Evrima admin/command log line."""
        ts_match = self.TIMESTAMP_PATTERN.search(line)
        timestamp = self._parse_timestamp(ts_match.group(1)) if ts_match else datetime.now()

        # Try RCON command pattern first
        rcon_match = self.RCON_PATTERN.search(line)
        if rcon_match:
            action = rcon_match.group(1)  # e.g., "Announce", "Get Player List"
            details = rcon_match.group(2)

            return AdminLogEntry(
                log_type=LogType.ADMIN,
                timestamp=timestamp,
                raw_line=line,
                parsed_data={},
                admin_name="RCON",
                admin_id="RCON",
                action=action,
                target=None,
                details=details if details else action
            )

        # Try player command pattern
        admin_match = self.ADMIN_PATTERN.search(line)
        if not admin_match:
            return None

        player_name = admin_match.group(1)
        player_id = admin_match.group(2)
        command = admin_match.group(3)

        # Extract action from command (first part before "at:")
        action = command.split(' at:')[0] if ' at:' in command else command

        return AdminLogEntry(
            log_type=LogType.ADMIN,
            timestamp=timestamp,
            raw_line=line,
            parsed_data={},
            admin_name=player_name,
            admin_id=player_id,
            action=action,
            target=None,
            details=command
        )

    def _parse_join_leave(self, line: str) -> Optional[AdminLogEntry]:
        """Parse join/leave events as admin log entries."""
        ts_match = self.TIMESTAMP_PATTERN.search(line)
        timestamp = self._parse_timestamp(ts_match.group(1)) if ts_match else datetime.now()

        # Check for join
        join_match = self.JOIN_PATTERN.search(line)
        if join_match:
            player_name = join_match.group(1)
            player_id = join_match.group(2)

            return AdminLogEntry(
                log_type=LogType.ADMIN,
                timestamp=timestamp,
                raw_line=line,
                parsed_data={},
                admin_name=player_name,
                admin_id=player_id,
                action="Player Joined",
                target=None,
                details=f"{player_name} joined the server"
            )

        # Check for leave
        leave_match = self.LEAVE_PATTERN.search(line)
        if leave_match:
            player_name = leave_match.group(1)
            player_id = leave_match.group(2)

            return AdminLogEntry(
                log_type=LogType.ADMIN,
                timestamp=timestamp,
                raw_line=line,
                parsed_data={},
                admin_name=player_name,
                admin_id=player_id,
                action="Player Left",
                target=None,
                details=f"{player_name} left the server"
            )

        return None


class PathOfTitansLogParser(LogParser):
    """
    Log parser for Path of Titans.

    Log patterns vary but generally follow Source engine patterns.
    """

    TIMESTAMP_PATTERN = re.compile(r'\[(\d{4}\.\d{2}\.\d{2}-\d{2}\.\d{2}\.\d{2})\]')

    def __init__(self):
        super().__init__(GameLogType.PATH_OF_TITANS)

    def _parse_chat(self, line: str) -> Optional[ChatLogEntry]:
        """Parse PoT chat log line."""
        # Simplified - actual format may vary
        ts_match = self.TIMESTAMP_PATTERN.search(line)
        timestamp = self._parse_timestamp(ts_match.group(1)) if ts_match else datetime.now()

        # Try to extract chat data
        # Format: [Channel] PlayerName (AlderonID): Message
        chat_pattern = re.compile(r'\[(\w+)\]\s*(.+?)\s*\((\d{3}-\d{3}-\d{3})\):\s*(.+)$')
        match = chat_pattern.search(line)

        if match:
            return ChatLogEntry(
                log_type=LogType.CHAT,
                timestamp=timestamp,
                raw_line=line,
                parsed_data={},
                player_name=match.group(2),
                player_id=match.group(3),
                message=match.group(4),
                channel=match.group(1)
            )
        return None

    def _parse_kill(self, line: str) -> Optional[KillLogEntry]:
        """Parse PoT kill log line."""
        ts_match = self.TIMESTAMP_PATTERN.search(line)
        timestamp = self._parse_timestamp(ts_match.group(1)) if ts_match else datetime.now()

        # Format: PlayerA (ID) killed PlayerB (ID)
        kill_pattern = re.compile(
            r'(.+?)\s*\((\d{3}-\d{3}-\d{3})\)\s*killed\s*(.+?)\s*\((\d{3}-\d{3}-\d{3})\)'
        )
        match = kill_pattern.search(line)

        if match:
            return KillLogEntry(
                log_type=LogType.KILL,
                timestamp=timestamp,
                raw_line=line,
                parsed_data={},
                killer_name=match.group(1),
                killer_id=match.group(2),
                victim_name=match.group(3),
                victim_id=match.group(4)
            )
        return None

    def _parse_admin(self, line: str) -> Optional[AdminLogEntry]:
        """Parse PoT admin log line."""
        ts_match = self.TIMESTAMP_PATTERN.search(line)
        timestamp = self._parse_timestamp(ts_match.group(1)) if ts_match else datetime.now()

        # Format varies - try basic pattern
        admin_pattern = re.compile(r'Admin\s+(.+?)\s*\((\d{3}-\d{3}-\d{3})\):\s*(.+)$')
        match = admin_pattern.search(line)

        if match:
            command = match.group(3)
            parts = command.split()
            return AdminLogEntry(
                log_type=LogType.ADMIN,
                timestamp=timestamp,
                raw_line=line,
                parsed_data={},
                admin_name=match.group(1),
                admin_id=match.group(2),
                action=parts[0] if parts else command,
                target=parts[1] if len(parts) > 1 else None,
                details=command
            )
        return None


def get_log_parser(game_type: GameLogType | str):
    """
    Get the appropriate log parser for a game type.

    Prefers enhanced parser if available, falls back to legacy parser.
    """
    if isinstance(game_type, str):
        game_type = GameLogType(game_type)

    # Try to use enhanced parser first
    if ENHANCED_PARSER_AVAILABLE:
        try:
            game_type_str = game_type.value if hasattr(game_type, 'value') else str(game_type)
            enhanced_parser = get_enhanced_parser(game_type_str)
            logger.info(f"Using enhanced parser for {game_type_str}")
            return enhanced_parser
        except Exception as e:
            logger.warning(f"Failed to load enhanced parser, falling back to legacy: {e}")

    # Fall back to legacy parser
    if game_type == GameLogType.THE_ISLE_EVRIMA:
        return EvrimaLogParser()
    elif game_type == GameLogType.PATH_OF_TITANS:
        return PathOfTitansLogParser()
    else:
        raise ValueError(f"Unsupported game type: {game_type}")


class SFTPLogReader:
    """
    SFTP-based log file reader with incremental reading support.

    Connects to SFTP, reads only new lines since last position,
    and parses them using the appropriate game parser.
    """

    def __init__(self, host: str, port: int, username: str, password: str,
                 game_type: GameLogType, server_name: str = "Unknown Server"):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.game_type = game_type
        self.server_name = server_name  # For log identification
        self.parser = get_log_parser(game_type)
        self._transport = None
        self._sftp = None

    async def connect(self) -> bool:
        """Establish SFTP connection."""
        try:
            import paramiko
            import socket

            def _connect():
                # Create socket with timeout
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(30)  # 30 second timeout for socket operations
                sock.connect((self.host, self.port))

                # Create transport with longer timeout for slow servers
                self._transport = paramiko.Transport(sock)
                self._transport.banner_timeout = 30  # Increase from default 15s to 30s
                self._transport.auth_timeout = 30    # Increase auth timeout as well
                self._transport.connect(username=self.username, password=self.password)
                self._sftp = paramiko.SFTPClient.from_transport(self._transport)
                return True

            result = await asyncio.to_thread(_connect)
            logger.info(f"[{self.server_name}] SFTP connected to {self.host}:{self.port}")
            return result
        except ImportError:
            raise SFTPError("paramiko library not installed")
        except Exception as e:
            logger.error(f"SFTP connection failed: {e}")
            if "Authentication" in str(e):
                raise SFTPAuthError(f"Authentication failed: {e}")
            raise SFTPConnectionError(f"Connection failed: {e}")

    async def disconnect(self) -> None:
        """Close SFTP connection."""
        try:
            if self._sftp:
                await asyncio.to_thread(self._sftp.close)
                self._sftp = None
            if self._transport:
                await asyncio.to_thread(self._transport.close)
                self._transport = None
            logger.info("SFTP disconnected")
        except Exception as e:
            logger.error(f"Error disconnecting SFTP: {e}")

    async def read_new_lines(self, file_path: str, last_position: int = 0,
                             last_line_hash: Optional[str] = None) -> tuple[list[str], int, str]:
        """
        Read new lines from a log file since last position.

        Args:
            file_path: Path to the log file
            last_position: Byte position to start reading from
            last_line_hash: Hash of last read line (for verification)

        Returns:
            Tuple of (new_lines, new_position, new_last_line_hash)
        """
        if not self._sftp:
            await self.connect()

        def _read():
            try:
                # Check file size first
                stat = self._sftp.stat(file_path)
                file_size = stat.st_size

                # If file is smaller than last position, it was rotated
                if file_size < last_position:
                    last_position_adjusted = 0
                else:
                    last_position_adjusted = last_position

                # Read new content
                with self._sftp.open(file_path, 'r') as f:
                    f.seek(last_position_adjusted)
                    content = f.read()
                    new_position = f.tell()

                if isinstance(content, bytes):
                    content = content.decode('utf-8', errors='replace')

                lines = content.splitlines()
                if lines:
                    new_hash = hashlib.md5(lines[-1].encode()).hexdigest()
                else:
                    new_hash = ""

                return lines, new_position, new_hash
            except FileNotFoundError:
                return [], 0, ""
            except Exception as e:
                logger.error(f"Error reading log file {file_path}: {e}")
                return [], last_position, last_line_hash or ""

        return await asyncio.to_thread(_read)

    async def read_and_parse(self, file_path: str, log_type: LogType,
                             last_position: int = 0,
                             last_line_hash: Optional[str] = None) -> tuple[list[LogEntry], int, str]:
        """
        Read and parse new log entries.

        Returns:
            Tuple of (parsed_entries, new_position, new_last_line_hash)
        """
        lines, new_position, new_hash = await self.read_new_lines(
            file_path, last_position, last_line_hash
        )

        entries = []
        for line in lines:
            entry = self.parser.parse_line(line, log_type)
            if entry:
                entries.append(entry)

        return entries, new_position, new_hash

    async def read_and_parse_unified(self, file_path: str,
                                     last_position: int = 0,
                                     last_line_hash: Optional[str] = None) -> tuple[list[LogEntry], int, str]:
        """
        Read and parse new log entries from a unified log file.
        Auto-detects log type for each line (chat, kill, admin, etc.).

        Used for games like The Isle Evrima where all logs are in one file.

        Returns:
            Tuple of (parsed_entries, new_position, new_last_line_hash)
        """
        lines, new_position, new_hash = await self.read_new_lines(
            file_path, last_position, last_line_hash
        )

        logger.debug(f"Read {len(lines)} new lines from {file_path}")

        entries = []
        parsed_count = 0
        skipped_count = 0

        for line in lines:
            # Check if using enhanced parser (returns tuple) or legacy parser
            if ENHANCED_PARSER_AVAILABLE and hasattr(self.parser, 'parse_line'):
                # Enhanced parser: parse_line(line) returns (LogType, Event)
                try:
                    result = self.parser.parse_line(line)
                    if result and len(result) == 2:
                        log_type, event = result
                        if event:  # If event is not None
                            entry = event
                        else:
                            entry = None
                    else:
                        entry = None
                except TypeError:
                    # Fallback to legacy parser signature
                    entry = (self.parser.parse_line(line, LogType.CHAT) or
                            self.parser.parse_line(line, LogType.KILL) or
                            self.parser.parse_line(line, LogType.ADMIN))
            elif hasattr(self.parser, 'parse_any_line'):
                # Legacy Evrima parser has parse_any_line
                entry = self.parser.parse_any_line(line)
            else:
                # Fallback to trying each log type with legacy parser
                entry = (self.parser.parse_line(line, LogType.CHAT) or
                        self.parser.parse_line(line, LogType.KILL) or
                        self.parser.parse_line(line, LogType.ADMIN))

            if entry:
                entries.append(entry)
                parsed_count += 1
            else:
                skipped_count += 1
                if skipped_count <= 3:  # Only log first few skipped lines
                    logger.debug(f"Skipped line (no match): {line[:100]}")

        logger.info(f"[{self.server_name}] Parsed {parsed_count} entries, skipped {skipped_count} lines from {file_path}")

        return entries, new_position, new_hash

    async def test_connection(self) -> tuple[bool, str]:
        """Test SFTP connection."""
        try:
            await self.connect()
            await self.disconnect()
            return True, "Connection successful"
        except SFTPAuthError as e:
            return False, f"Authentication failed: {e}"
        except SFTPConnectionError as e:
            return False, f"Connection failed: {e}"
        except Exception as e:
            return False, f"Unexpected error: {e}"


class LogMonitor:
    """
    Background log monitor that polls files and invokes callbacks.

    Manages multiple log files for a single SFTP connection.
    """

    def __init__(self, sftp_reader: SFTPLogReader, unified_mode: bool = False, config_id: int = None):
        self.reader = sftp_reader
        self.unified_mode = unified_mode  # If True, one file contains all log types
        self.config_id = config_id  # SFTP config ID for saving state to database
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._file_states: dict[str, dict] = {}  # file_path -> {position, hash, log_type}
        self._callbacks: dict[LogType, list[Callable]] = {
            LogType.CHAT: [],
            LogType.KILL: [],
            LogType.ADMIN: []
        }

    def add_file(self, file_path: str, log_type: LogType = None,
                 initial_position: int = 0, initial_hash: str = "") -> None:
        """
        Add a file to monitor.

        Args:
            file_path: Path to log file
            log_type: Type of logs in this file (or None for unified mode)
            initial_position: Starting byte position
            initial_hash: Hash of last read line
        """
        self._file_states[file_path] = {
            'position': initial_position,
            'hash': initial_hash,
            'log_type': log_type,  # None for unified files
            'unified': log_type is None or self.unified_mode
        }

    def remove_file(self, file_path: str) -> None:
        """Remove a file from monitoring."""
        if file_path in self._file_states:
            del self._file_states[file_path]

    def on_log(self, log_type: LogType, callback: Callable[[LogEntry], Any]) -> None:
        """Register a callback for a log type."""
        self._callbacks[log_type].append(callback)

    async def start(self, poll_interval: int = 30) -> None:
        """Start the monitor loop."""
        if self._running:
            logger.warning("Monitor already running")
            return

        self._running = True
        logger.info(f"Starting log monitor with {len(self._file_states)} file(s), poll interval: {poll_interval}s")

        async def monitor_loop():
            try:
                logger.info("Monitor loop: Connecting to SFTP...")
                await self.reader.connect()
                logger.info("Monitor loop: Connected successfully, beginning poll loop")

                while self._running:
                    try:
                        await self._poll_all_files()
                    except Exception as e:
                        logger.error(f"Error in monitor loop: {e}", exc_info=True)
                    await asyncio.sleep(poll_interval)

                logger.info("Monitor loop: Stopping, disconnecting from SFTP")
                await self.reader.disconnect()
            except Exception as e:
                logger.error(f"Fatal error in monitor loop: {e}", exc_info=True)
                self._running = False

        self._task = asyncio.create_task(monitor_loop())
        logger.info("Monitor loop task created")

    async def stop(self) -> None:
        """Stop the monitor loop."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _poll_all_files(self) -> None:
        """Poll all monitored files for new entries."""
        for file_path, state in self._file_states.items():
            try:
                logger.debug(f"Polling file: {file_path} (position: {state['position']})")

                # Check if this is a unified file (all log types in one file)
                if state.get('unified', False) or self.unified_mode:
                    # Use unified parser that auto-detects log types
                    entries, new_position, new_hash = await self.reader.read_and_parse_unified(
                        file_path,
                        state['position'],
                        state['hash']
                    )
                    logger.debug(f"Unified mode: Read {len(entries)} entries from {file_path}")
                else:
                    # Use single-type parser
                    entries, new_position, new_hash = await self.reader.read_and_parse(
                        file_path,
                        state['log_type'],
                        state['position'],
                        state['hash']
                    )
                    logger.debug(f"Single-type mode: Read {len(entries)} entries from {file_path}")

                # Update state in memory
                state['position'] = new_position
                state['hash'] = new_hash

                logger.debug(f"New position: {new_position}")

                # Save position to database to persist across restarts
                if self.config_id and new_position > 0 and len(entries) > 0:
                    try:
                        from database.queries.rcon import LogMonitorStateQueries
                        # Determine log type for database storage
                        log_type_str = state.get('log_type')
                        if log_type_str:
                            log_type_value = log_type_str.value if hasattr(log_type_str, 'value') else str(log_type_str)
                        else:
                            log_type_value = 'admin'  # Default for unified mode

                        LogMonitorStateQueries.update_state(
                            sftp_config_id=self.config_id,
                            log_type=log_type_value,
                            file_path=file_path,
                            position=new_position,
                            line_hash=new_hash
                        )
                        logger.debug(f"[{self.reader.server_name}] Saved position {new_position} to database")
                    except Exception as e:
                        logger.warning(f"Failed to save file position to database: {e}")

                # Invoke callbacks for each entry based on its detected type
                for entry in entries:
                    # Determine the log type - handle both legacy and enhanced events
                    if hasattr(entry, 'log_type'):
                        # Legacy event (ChatLogEntry, KillLogEntry, AdminLogEntry)
                        log_type = entry.log_type
                    elif ENHANCED_PARSER_AVAILABLE:
                        # Enhanced event - map class type to LogType
                        if isinstance(entry, (PlayerLoginEvent, PlayerLogoutEvent)):
                            log_type = LogType.ADMIN  # Route login/logout to admin callbacks for now
                        elif isinstance(entry, PlayerChatEvent):
                            log_type = LogType.CHAT
                        elif isinstance(entry, (AdminCommandEvent, RCONCommandEvent)):
                            log_type = LogType.ADMIN  # Route both admin and RCON commands to admin callbacks
                        elif isinstance(entry, PlayerDeathEvent):
                            log_type = LogType.KILL
                        else:
                            logger.warning(f"Unknown enhanced event type: {type(entry)}")
                            continue
                    else:
                        logger.warning(f"Unknown event type: {type(entry)}")
                        continue

                    raw_preview = entry.raw_line[:100] if hasattr(entry, 'raw_line') else str(entry)[:100]
                    logger.debug(f"Processing entry: {log_type} - {raw_preview}")

                    for callback in self._callbacks[log_type]:
                        try:
                            result = callback(entry)
                            if asyncio.iscoroutine(result):
                                await result
                        except Exception as e:
                            logger.error(f"Callback error: {e}", exc_info=True)

            except Exception as e:
                logger.error(f"Error polling {file_path}: {e}", exc_info=True)

    def get_state(self, file_path: str) -> Optional[dict]:
        """Get current state for a file."""
        return self._file_states.get(file_path)

    @property
    def is_running(self) -> bool:
        """Check if monitor is running."""
        return self._running


class LogMonitorManager:
    """
    Manager for multiple log monitors across guilds.

    Handles creating, starting, stopping, and tracking monitors.
    """

    def __init__(self):
        self._monitors: dict[int, LogMonitor] = {}  # sftp_config_id -> monitor

    def create_monitor(self, config_id: int, host: str, port: int,
                       username: str, password: str,
                       game_type: GameLogType, unified_mode: bool = False,
                       server_name: str = "Unknown Server") -> LogMonitor:
        """
        Create a new log monitor.

        Args:
            config_id: SFTP configuration ID
            host: SFTP server host
            port: SFTP server port
            username: SFTP username
            password: SFTP password
            game_type: Game log format type
            unified_mode: If True, expects a single file with all log types
            server_name: Server name for log identification
        """
        reader = SFTPLogReader(host, port, username, password, game_type, server_name=server_name)
        monitor = LogMonitor(reader, unified_mode=unified_mode, config_id=config_id)
        self._monitors[config_id] = monitor
        return monitor

    def get_monitor(self, config_id: int) -> Optional[LogMonitor]:
        """Get an existing monitor."""
        return self._monitors.get(config_id)

    async def start_monitor(self, config_id: int, poll_interval: int = 30) -> bool:
        """Start a monitor."""
        monitor = self._monitors.get(config_id)
        if monitor and not monitor.is_running:
            await monitor.start(poll_interval)
            return True
        return False

    async def stop_monitor(self, config_id: int) -> bool:
        """Stop a monitor."""
        monitor = self._monitors.get(config_id)
        if monitor and monitor.is_running:
            await monitor.stop()
            return True
        return False

    async def remove_monitor(self, config_id: int) -> None:
        """Stop and remove a monitor."""
        await self.stop_monitor(config_id)
        if config_id in self._monitors:
            del self._monitors[config_id]

    def get_active_count(self) -> int:
        """Count active monitors."""
        return sum(1 for m in self._monitors.values() if m.is_running)

    async def stop_all(self) -> None:
        """Stop all monitors."""
        for config_id in list(self._monitors.keys()):
            await self.stop_monitor(config_id)


# Global manager instance
log_monitor_manager = LogMonitorManager()
