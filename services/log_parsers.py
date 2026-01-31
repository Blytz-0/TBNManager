"""
Log parsers for The Isle Evrima and Path of Titans.
Parses unified log files into structured events.
"""

import re
from enum import Enum
from dataclasses import dataclass
from typing import Optional
from datetime import datetime


class LogType(Enum):
    """Types of log events that can be parsed."""
    PLAYER_LOGIN = "player_login"
    PLAYER_LOGOUT = "player_logout"
    PLAYER_CHAT = "player_chat"
    ADMIN_COMMAND = "admin_command"
    RCON_COMMAND = "rcon_command"
    PLAYER_DEATH = "player_death"
    UNKNOWN = "unknown"


@dataclass
class PlayerLoginEvent:
    """Player joined the server."""
    timestamp: str
    player_name: str
    steam_id: str
    dinosaur: str
    gender: str  # "Male" or "Female"
    growth: float  # 0.0 to 1.0
    is_prime: bool = False
    raw_line: str = ""


@dataclass
class PlayerLogoutEvent:
    """Player left the server."""
    timestamp: str
    player_name: str
    steam_id: str
    dinosaur: str
    gender: str
    growth: float  # 0.0 to 1.0
    safe_logged: bool
    raw_line: str = ""


@dataclass
class PlayerChatEvent:
    """Player sent a chat message."""
    timestamp: str
    channel: str  # Global, Admin, Spatial, Logging
    player_name: str
    steam_id: str
    message: str
    raw_line: str = ""


@dataclass
class AdminCommandEvent:
    """Admin executed an in-game command."""
    timestamp: str
    admin_name: str
    admin_steam_id: str
    command: str
    target_name: Optional[str] = None
    target_class: Optional[str] = None
    target_gender: Optional[str] = None
    previous_value: Optional[str] = None
    new_value: Optional[str] = None
    raw_line: str = ""


@dataclass
class RCONCommandEvent:
    """RCON command executed from Discord."""
    timestamp: str
    command: str
    details: str
    executor_id: Optional[int] = None  # Discord user ID who executed the command
    executor_name: Optional[str] = None  # Discord username who executed the command
    raw_line: str = ""


@dataclass
class PlayerDeathEvent:
    """Player died."""
    timestamp: str
    victim_name: str
    victim_steam_id: str
    victim_class: str  # Dinosaur type (e.g., "Tyrannosaurus")
    victim_gender: str  # "Male" or "Female"
    victim_growth: float  # 0.0 to 1.0
    victim_is_prime: bool  # True if Prime variant
    cause_of_death: str  # e.g., "Died from Natural cause" or killer info
    victim_location: Optional[str] = None  # Future: coordinates
    killer_name: Optional[str] = None
    killer_steam_id: Optional[str] = None
    killer_class: Optional[str] = None  # Dinosaur type
    killer_gender: Optional[str] = None  # "Male" or "Female"
    killer_growth: Optional[float] = None  # 0.0 to 1.0
    killer_is_prime: bool = False  # True if Prime variant
    killer_location: Optional[str] = None  # Future: coordinates
    raw_line: str = ""


class TheIsleLogParser:
    """Parser for The Isle Evrima unified log file."""

    # Regex patterns for The Isle Evrima logs
    LOGIN_PATTERN = re.compile(
        r'\[(?P<timestamp>[^\]]+)\].*LogTheIsleJoinData:\s*\[[^\]]+\]\s+'
        r'(?P<player_name>\S+)\s+\[(?P<steam_id>\d+)\]\s+Joined The Server\.\s+'
        r'Save file found Dino:\s*(?P<dino>BP_\w+_C),\s*Gender:\s*(?P<gender>\w+),\s*Growth:\s*(?P<growth>[\d.]+)',
        re.IGNORECASE
    )

    LOGOUT_PATTERN = re.compile(
        r'\[(?P<timestamp>[^\]]+)\].*LogTheIsleJoinData:\s*\[[^\]]+\]\s+'
        r'(?P<player_name>\S+)\s+\[(?P<steam_id>\d+)\]\s+Left The Server\s*'
        r'(?P<safe_logged>whilebeing safelogged)?.*Was playing as:\s*(?P<dino>\w+),\s*'
        r'Gender:\s*(?P<gender>\w+),\s*Growth:\s*(?P<growth>[\d.]+)',
        re.IGNORECASE
    )

    CHAT_PATTERN = re.compile(
        r'\[(?P<timestamp>[^\]]+)\].*LogTheIsleChatData.*'
        r'\[(?P<channel>[^\]]+)\]\s+\[GROUP-\d+\]\s+(?P<player_name>[^\[]+)\s+'
        r'\[(?P<steam_id>\d+)\]:\s*(?P<message>.+)',
        re.IGNORECASE
    )

    COMMAND_PATTERN = re.compile(
        r'\[(?P<timestamp>[^\]]+)\].*LogTheIsleCommandData:\s*\[[^\]]+\]\s+'
        r'(?P<admin_name>\S+)\s+\[(?P<admin_steam_id>\d+)\]\s+used command:\s*'
        r'(?P<command>(?:[\w\s]+?)(?=\s+at:|$))'
        r'(?:\s+at:\s*(?P<target_name>[^,]+),\s+\[(?P<target_steam_id>\d+)\],\s+'
        r'Class:\s*(?P<target_class>\w+),\s*Gender:\s*(?P<target_gender>\w+),\s*'
        r'Previous value:\s*(?P<previous>[\d.]+%?),\s*New value:\s*(?P<new>[\d.]+%?))?',
        re.IGNORECASE
    )

    RCON_PATTERN = re.compile(
        r'\[(?P<timestamp>[^\]]+)\].*LogTheIsleCommandData.*'
        r'RCON Command Used\s+\[(?P<command>[^\]]+)\]\s*:\s*(?P<details>.*)',
        re.IGNORECASE
    )

    # Death/Kill pattern
    # Format: [timestamp][id]LogTheIsleKillData: [timestamp] Name [SteamID] Dino: Type, Gender, Growth - Cause
    DEATH_PATTERN = re.compile(
        r'\[(?P<timestamp>[^\]]+)\].*LogTheIsleKillData:\s*\[[^\]]+\]\s+'
        r'(?P<victim_name>\S+)\s+\[(?P<victim_steam_id>\d+)\]\s+'
        r'Dino:\s*(?P<victim_dino>(?:BP_)?\w+(?:_C)?),\s*'
        r'(?P<victim_gender>\w+),\s*(?P<victim_growth>[\d.]+)\s*-\s*'
        r'(?P<cause>.+)',
        re.IGNORECASE
    )

    def parse_line(self, line: str) -> tuple[LogType, Optional[object]]:
        """
        Parse a single log line and return log type + event object.

        Args:
            line: Raw log line from The Isle log file

        Returns:
            Tuple of (LogType, Event object or None)
        """
        line = line.strip()
        if not line:
            return (LogType.UNKNOWN, None)

        # Try PlayerLogin
        match = self.LOGIN_PATTERN.search(line)
        if match:
            dino_raw = match.group('dino')
            dino_clean = self._clean_dinosaur_name(dino_raw)
            is_prime = 'Prime' in dino_clean

            return (LogType.PLAYER_LOGIN, PlayerLoginEvent(
                timestamp=match.group('timestamp'),
                player_name=match.group('player_name').strip(),
                steam_id=match.group('steam_id'),
                dinosaur=dino_clean,
                gender=match.group('gender').capitalize(),
                growth=float(match.group('growth')),
                is_prime=is_prime,
                raw_line=line
            ))

        # Try PlayerLogout
        match = self.LOGOUT_PATTERN.search(line)
        if match:
            dino_clean = self._clean_dinosaur_name(match.group('dino'))

            return (LogType.PLAYER_LOGOUT, PlayerLogoutEvent(
                timestamp=match.group('timestamp'),
                player_name=match.group('player_name').strip(),
                steam_id=match.group('steam_id'),
                dinosaur=dino_clean,
                gender=match.group('gender').capitalize(),
                growth=float(match.group('growth')),
                safe_logged=bool(match.group('safe_logged')),
                raw_line=line
            ))

        # Try PlayerChat
        match = self.CHAT_PATTERN.search(line)
        if match:
            return (LogType.PLAYER_CHAT, PlayerChatEvent(
                timestamp=match.group('timestamp'),
                channel=match.group('channel').strip(),
                player_name=match.group('player_name').strip(),
                steam_id=match.group('steam_id'),
                message=match.group('message').strip(),
                raw_line=line
            ))

        # Try RCONCommand (check before AdminCommand since it's more specific)
        match = self.RCON_PATTERN.search(line)
        if match:
            return (LogType.RCON_COMMAND, RCONCommandEvent(
                timestamp=match.group('timestamp'),
                command=match.group('command').strip(),
                details=match.group('details').strip(),
                raw_line=line
            ))

        # Try AdminCommand
        match = self.COMMAND_PATTERN.search(line)
        if match:
            return (LogType.ADMIN_COMMAND, AdminCommandEvent(
                timestamp=match.group('timestamp'),
                admin_name=match.group('admin_name').strip(),
                admin_steam_id=match.group('admin_steam_id'),
                command=match.group('command').strip(),
                target_name=match.group('target_name').strip() if match.group('target_name') else None,
                target_class=match.group('target_class') if match.group('target_class') else None,
                target_gender=match.group('target_gender') if match.group('target_gender') else None,
                previous_value=match.group('previous') if match.group('previous') else None,
                new_value=match.group('new') if match.group('new') else None,
                raw_line=line
            ))

        # Try PlayerDeath
        match = self.DEATH_PATTERN.search(line)
        if match:
            victim_dino_raw = match.group('victim_dino')
            victim_dino_clean = self._clean_dinosaur_name(victim_dino_raw)
            victim_is_prime = 'Prime' in victim_dino_clean

            cause = match.group('cause').strip()

            # TODO: Parse killer info from cause if it's a player kill
            # For now, we only handle natural deaths
            # Future format might be: "Killed by PlayerName [SteamID] using DinoClass"

            return (LogType.PLAYER_DEATH, PlayerDeathEvent(
                timestamp=match.group('timestamp'),
                victim_name=match.group('victim_name').strip(),
                victim_steam_id=match.group('victim_steam_id'),
                victim_class=victim_dino_clean,
                victim_gender=match.group('victim_gender').capitalize(),
                victim_growth=float(match.group('victim_growth')),
                victim_is_prime=victim_is_prime,
                cause_of_death=cause,
                raw_line=line
            ))

        return (LogType.UNKNOWN, None)

    def _clean_dinosaur_name(self, dino_raw: str) -> str:
        """
        Clean dinosaur name by removing BP_ prefix and _C suffix.

        Examples:
            BP_Tyrannosaurus_C -> Tyrannosaurus
            BP_TyrannosaurusPrime_C -> Tyrannosaurus (Prime)
        """
        # Remove BP_ prefix and _C suffix
        cleaned = dino_raw.replace('BP_', '').replace('_C', '')

        # Handle Prime variants
        if 'Prime' in cleaned:
            cleaned = cleaned.replace('Prime', '').strip() + ' (Prime)'

        return cleaned

    def get_gender_symbol(self, gender: str) -> str:
        """Get Unicode symbol for gender."""
        if gender and gender.lower() == 'male':
            return '♂'
        elif gender and gender.lower() == 'female':
            return '♀'
        return ''


class PathOfTitansLogParser:
    """Parser for Path of Titans logs (future implementation)."""

    def parse_line(self, line: str) -> tuple[LogType, Optional[object]]:
        """Parse Path of Titans log format."""
        # Future implementation
        return (LogType.UNKNOWN, None)


def get_parser(game_type: str):
    """
    Get appropriate parser for game type.

    Args:
        game_type: "the_isle_evrima" or "path_of_titans"

    Returns:
        Parser instance
    """
    if game_type == "the_isle_evrima":
        return TheIsleLogParser()
    elif game_type == "path_of_titans":
        return PathOfTitansLogParser()
    else:
        raise ValueError(f"Unknown game type: {game_type}")
