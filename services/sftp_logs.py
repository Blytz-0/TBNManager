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
    Log parser for The Isle Evrima.

    Log patterns:
    - Chat: [2024.01.22-15.30.45][LogTheIsleChatData]: [Global] [Group] PlayerName [76561198012345678]: Hello world
    - Kill: [2024.01.22-15.30.45][LogTheIsleKills]: PlayerA [76561198012345678] killed PlayerB [76561198087654321]
    - Admin: [2024.01.22-15.30.45][LogTheIsleAdmin]: Admin [76561198012345678] executed: /kick PlayerB
    """

    # Regex patterns
    TIMESTAMP_PATTERN = re.compile(r'\[(\d{4}\.\d{2}\.\d{2}-\d{2}\.\d{2}\.\d{2})\]')
    CHAT_PATTERN = re.compile(
        r'\[LogTheIsleChatData\]:\s*\[(\w+)\]\s*(?:\[(\w+)\])?\s*(.+?)\s*\[(\d{17})\]:\s*(.+)$'
    )
    KILL_PATTERN = re.compile(
        r'\[LogTheIsleKills\]:\s*(.+?)\s*\[(\d{17})\]\s*killed\s*(.+?)\s*\[(\d{17})\]'
    )
    ADMIN_PATTERN = re.compile(
        r'\[LogTheIsleAdmin\]:\s*(.+?)\s*\[(\d{17})\]\s*executed:\s*(.+)$'
    )

    def __init__(self):
        super().__init__(GameLogType.THE_ISLE_EVRIMA)

    def _parse_chat(self, line: str) -> Optional[ChatLogEntry]:
        """Parse Evrima chat log line."""
        ts_match = self.TIMESTAMP_PATTERN.search(line)
        chat_match = self.CHAT_PATTERN.search(line)

        if not chat_match:
            return None

        timestamp = self._parse_timestamp(ts_match.group(1)) if ts_match else datetime.now()
        channel = chat_match.group(1)
        group = chat_match.group(2) or ""
        player_name = chat_match.group(3)
        player_id = chat_match.group(4)
        message = chat_match.group(5)

        return ChatLogEntry(
            log_type=LogType.CHAT,
            timestamp=timestamp,
            raw_line=line,
            parsed_data={},
            player_name=player_name,
            player_id=player_id,
            message=message,
            channel=f"{channel} {group}".strip()
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
        """Parse Evrima admin log line."""
        ts_match = self.TIMESTAMP_PATTERN.search(line)
        admin_match = self.ADMIN_PATTERN.search(line)

        if not admin_match:
            return None

        timestamp = self._parse_timestamp(ts_match.group(1)) if ts_match else datetime.now()
        command = admin_match.group(3)

        # Try to extract target from command
        target = None
        parts = command.split()
        if len(parts) > 1:
            target = parts[1]

        return AdminLogEntry(
            log_type=LogType.ADMIN,
            timestamp=timestamp,
            raw_line=line,
            parsed_data={},
            admin_name=admin_match.group(1),
            admin_id=admin_match.group(2),
            action=parts[0] if parts else command,
            target=target,
            details=command
        )


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


def get_log_parser(game_type: GameLogType | str) -> LogParser:
    """Get the appropriate log parser for a game type."""
    if isinstance(game_type, str):
        game_type = GameLogType(game_type)

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
                 game_type: GameLogType):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.game_type = game_type
        self.parser = get_log_parser(game_type)
        self._transport = None
        self._sftp = None

    async def connect(self) -> bool:
        """Establish SFTP connection."""
        try:
            import paramiko

            def _connect():
                self._transport = paramiko.Transport((self.host, self.port))
                self._transport.connect(username=self.username, password=self.password)
                self._sftp = paramiko.SFTPClient.from_transport(self._transport)
                return True

            result = await asyncio.to_thread(_connect)
            logger.info(f"SFTP connected to {self.host}:{self.port}")
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

    def __init__(self, sftp_reader: SFTPLogReader):
        self.reader = sftp_reader
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._file_states: dict[str, dict] = {}  # file_path -> {position, hash, log_type}
        self._callbacks: dict[LogType, list[Callable]] = {
            LogType.CHAT: [],
            LogType.KILL: [],
            LogType.ADMIN: []
        }

    def add_file(self, file_path: str, log_type: LogType,
                 initial_position: int = 0, initial_hash: str = "") -> None:
        """Add a file to monitor."""
        self._file_states[file_path] = {
            'position': initial_position,
            'hash': initial_hash,
            'log_type': log_type
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
            return

        self._running = True

        async def monitor_loop():
            await self.reader.connect()
            while self._running:
                try:
                    await self._poll_all_files()
                except Exception as e:
                    logger.error(f"Error in monitor loop: {e}")
                await asyncio.sleep(poll_interval)
            await self.reader.disconnect()

        self._task = asyncio.create_task(monitor_loop())

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
                entries, new_position, new_hash = await self.reader.read_and_parse(
                    file_path,
                    state['log_type'],
                    state['position'],
                    state['hash']
                )

                # Update state
                state['position'] = new_position
                state['hash'] = new_hash

                # Invoke callbacks
                for entry in entries:
                    for callback in self._callbacks[entry.log_type]:
                        try:
                            result = callback(entry)
                            if asyncio.iscoroutine(result):
                                await result
                        except Exception as e:
                            logger.error(f"Callback error: {e}")

            except Exception as e:
                logger.error(f"Error polling {file_path}: {e}")

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
                       game_type: GameLogType) -> LogMonitor:
        """Create a new log monitor."""
        reader = SFTPLogReader(host, port, username, password, game_type)
        monitor = LogMonitor(reader)
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
