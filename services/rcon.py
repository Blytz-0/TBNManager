# services/rcon.py
"""
RCON client implementations for game server management.

Supports:
- The Isle Evrima: Custom binary protocol via gamercon-async EvrimaRCON
- Path of Titans: Standard Source RCON via gamercon-async GameRCON

Both clients are async-compatible for use with discord.py.
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


class GameType(Enum):
    """Supported game types for RCON."""
    PATH_OF_TITANS = "path_of_titans"
    THE_ISLE_EVRIMA = "the_isle_evrima"


@dataclass
class RCONResponse:
    """Standardized response from RCON commands."""
    success: bool
    message: str
    data: Optional[dict] = None
    raw_response: Optional[str] = None


@dataclass
class PlayerInfo:
    """Player information from server player list."""
    player_id: str  # Steam ID or Alderon ID depending on game
    player_name: str
    is_online: bool = True
    dinosaur: Optional[str] = None
    gender: Optional[str] = None  # "Male" or "Female"
    growth: Optional[float] = None  # 0.0 to 1.0
    is_admin: bool = False
    is_prime_elder: bool = False


class RCONError(Exception):
    """Base exception for RCON errors."""
    pass


class RCONConnectionError(RCONError):
    """Failed to connect to RCON server."""
    pass


class RCONAuthError(RCONError):
    """RCON authentication failed."""
    pass


class RCONCommandError(RCONError):
    """RCON command execution failed."""
    pass


class BaseRCONClient(ABC):
    """Abstract base class for RCON clients."""

    def __init__(self, host: str, port: int, password: str):
        self.host = host
        self.port = port
        self.password = password
        self.game_type: GameType = None

    @abstractmethod
    async def connect(self) -> bool:
        """Establish connection to RCON server."""
        pass

    @abstractmethod
    async def disconnect(self) -> None:
        """Close connection to RCON server."""
        pass

    @abstractmethod
    async def kick(self, player_id: str, reason: str = "") -> RCONResponse:
        """Kick a player from the server."""
        pass

    @abstractmethod
    async def ban(self, player_id: str, reason: str = "") -> RCONResponse:
        """Ban a player from the server."""
        pass

    @abstractmethod
    async def unban(self, player_id: str) -> RCONResponse:
        """Unban a player from the server."""
        pass

    @abstractmethod
    async def announce(self, message: str) -> RCONResponse:
        """Send a server-wide announcement."""
        pass

    @abstractmethod
    async def dm(self, player_id: str, message: str) -> RCONResponse:
        """Send a direct message to a player."""
        pass

    @abstractmethod
    async def get_players(self) -> list[PlayerInfo]:
        """Get list of online players."""
        pass

    @abstractmethod
    async def save(self) -> RCONResponse:
        """Save the server state."""
        pass

    async def test_connection(self) -> RCONResponse:
        """Test RCON connection and authentication."""
        try:
            connected = await self.connect()
            if connected:
                await self.disconnect()
                return RCONResponse(
                    success=True,
                    message="Connection successful"
                )
            return RCONResponse(
                success=False,
                message="Connection failed"
            )
        except RCONAuthError as e:
            return RCONResponse(
                success=False,
                message=f"Authentication failed: {e}"
            )
        except RCONConnectionError as e:
            return RCONResponse(
                success=False,
                message=f"Connection error: {e}"
            )
        except Exception as e:
            return RCONResponse(
                success=False,
                message=f"Unexpected error: {e}"
            )


class EvrimaRCONClient(BaseRCONClient):
    """
    RCON client for The Isle Evrima.

    Uses custom binary protocol via gamercon-async library.
    All commands use send_command() with raw bytes:
    - Kick:        \\x02\\x30 + steam_id + \\x00
    - Ban:         \\x02\\x20 + steam_id + \\x00
    - Unban:       \\x02\\x21 + steam_id + \\x00
    - Announce:    \\x02\\x10 + message + \\x00
    - DM:          \\x02\\x11 + player_id + \\x00 + message + \\x00
    - Player List: \\x02\\x40\\x00
    - Save:        \\x02\\x50\\x00
    - Server Info: \\x02\\x12\\x00
    """

    def __init__(self, host: str, port: int, password: str):
        super().__init__(host, port, password)
        self.game_type = GameType.THE_ISLE_EVRIMA
        self._client = None

    async def connect(self) -> bool:
        """Connect to Evrima RCON server."""
        try:
            from gamercon_async import EvrimaRCON

            self._client = EvrimaRCON(self.host, self.port, self.password)
            await self._client.connect()
            logger.info(f"Evrima RCON client connected to {self.host}:{self.port}")
            return True
        except ImportError:
            raise RCONError("gamercon-async library not installed")
        except Exception as e:
            logger.error(f"Failed to connect Evrima RCON client: {e}")
            raise RCONConnectionError(f"Connection failed: {e}")

    async def disconnect(self) -> None:
        """Disconnect from Evrima RCON server."""
        self._client = None

    async def _send_command(self, command_bytes: bytes, retries: int = 2) -> str:
        """Send a raw binary command to the server.

        Args:
            command_bytes: The raw bytes to send
            retries: Number of retry attempts on failure

        Returns:
            The response string from the server
        """
        import asyncio
        last_error = None

        for attempt in range(retries + 1):
            client = None
            try:
                from gamercon_async import EvrimaRCON
                client = EvrimaRCON(self.host, self.port, self.password)
                await client.connect()

                # Small delay after connect to let the connection stabilize
                await asyncio.sleep(0.1)

                logger.debug(f"Evrima RCON connected, sending command: {command_bytes.hex()}")
                result = await client.send_command(command_bytes)
                logger.debug(f"Evrima RCON response: {result}")
                return result if result else ""
            except Exception as e:
                last_error = e
                logger.warning(f"Evrima RCON command failed (attempt {attempt + 1}/{retries + 1}): {e}")
                if attempt < retries:
                    await asyncio.sleep(0.5)  # Wait before retry
            finally:
                # Ensure we clean up the connection
                if client:
                    try:
                        if hasattr(client, 'close'):
                            await client.close()
                        elif hasattr(client, 'writer') and client.writer:
                            client.writer.close()
                            await client.writer.wait_closed()
                    except Exception:
                        pass  # Ignore cleanup errors

        logger.error(f"Evrima RCON command failed after {retries + 1} attempts: {last_error}")
        raise RCONCommandError(str(last_error))

    async def kick(self, player_id: str, reason: str = "") -> RCONResponse:
        """Kick a player by Steam ID."""
        try:
            # Kick: \x02\x30 + steam_id + \x00
            command = b'\x02\x30' + player_id.encode() + b'\x00'
            response = await self._send_command(command)
            return RCONResponse(
                success=True,
                message=f"Kicked player {player_id}",
                data={"player_id": player_id, "reason": reason},
                raw_response=response
            )
        except RCONCommandError as e:
            return RCONResponse(success=False, message=str(e))

    async def ban(self, player_id: str, reason: str = "") -> RCONResponse:
        """Ban a player by Steam ID."""
        try:
            # Ban: \x02\x20 + steam_id + \x00
            command = b'\x02\x20' + player_id.encode() + b'\x00'
            response = await self._send_command(command)
            return RCONResponse(
                success=True,
                message=f"Banned player {player_id}",
                data={"player_id": player_id, "reason": reason},
                raw_response=response
            )
        except RCONCommandError as e:
            return RCONResponse(success=False, message=str(e))

    async def unban(self, player_id: str) -> RCONResponse:
        """Unban a player by Steam ID."""
        try:
            # Unban: \x02\x21 + steam_id + \x00
            command = b'\x02\x21' + player_id.encode() + b'\x00'
            response = await self._send_command(command)
            return RCONResponse(
                success=True,
                message=f"Unbanned player {player_id}",
                data={"player_id": player_id},
                raw_response=response
            )
        except RCONCommandError as e:
            return RCONResponse(success=False, message=str(e))

    async def announce(self, message: str) -> RCONResponse:
        """Send a server-wide announcement."""
        try:
            # Announce: \x02\x10 + message + \x00
            command = b'\x02\x10' + message.encode() + b'\x00'
            response = await self._send_command(command)
            return RCONResponse(
                success=True,
                message="Announcement sent",
                data={"announcement": message},
                raw_response=response
            )
        except RCONCommandError as e:
            return RCONResponse(success=False, message=str(e))

    async def dm(self, player_id: str, message: str) -> RCONResponse:
        """Send a direct message to a player.

        Note: DM command format is experimental. The Isle Evrima's DM implementation
        appears to be incomplete/buggy in-game. Multiple formats attempted:
        - Format 1 (null-separated): player_id\x00message\x00
        - Format 2 (comma-separated): player_id,message\x00
        - Format 3 (space-separated): player_id message\x00
        """
        try:
            # Use comma-separated format (Format 2) which works in-game
            command = b'\x02\x11' + f'{player_id},{message}'.encode() + b'\x00'
            response = await self._send_command(command)
            return RCONResponse(
                success=True,
                message=f"Message sent to {player_id}",
                data={"player_id": player_id, "message": message},
                raw_response=response
            )
        except RCONCommandError as e:
            return RCONResponse(success=False, message=str(e))

    async def get_players(self) -> list[PlayerInfo]:
        """Get list of online players.

        According to official RCON protocol docs (v0.17.54):
        - RCON_GETPLAYERLIST (0x40) returns EOS ID and player's name
        - Response is comma delimited
        - Format: "PlayerList,EOS_ID1,Name1,EOS_ID2,Name2,..."
        """
        # Player List: \x02\x40\x00
        command = b'\x02\x40\x00'
        response = await self._send_command(command)

        # Enhanced debugging - show raw response with hex
        logger.info(f"Player list raw response: {repr(response)}")
        logger.info(f"Player list response length: {len(response)} chars")
        if response:
            try:
                logger.info(f"Player list response hex: {response.encode('utf-8', errors='replace').hex()}")
            except Exception as e:
                logger.warning(f"Could not encode response to hex: {e}")

        players = []
        if not response:
            logger.warning("Player list response is empty")
            return players

        # Check for common empty/error responses
        if response.strip() in ('', 'No players', 'Empty'):
            logger.info("Server returned no players indicator")
            return players

        # The actual format is newline-separated with trailing commas:
        # PlayerList
        # 76561199003854357,
        # Blytz,
        # 76561199003854358,
        # OtherPlayer,

        # Split by newlines and strip commas
        lines = [line.strip().rstrip(',').strip() for line in response.split('\n')]
        # Filter out empty lines and "PlayerList" header
        parts = [p for p in lines if p and p.lower() not in ('playerlist', 'players', 'player list')]
        logger.info(f"Split into {len(parts)} parts: {parts}")

        # Process pairs: ID, Name, ID, Name, ...
        i = 0
        while i < len(parts):
            if i + 1 < len(parts):
                # We expect ID followed by Name
                player_id = parts[i]
                player_name = parts[i + 1]

                # Verify the first part looks like an ID
                is_likely_id = (len(player_id) >= 15 and player_id.replace('-', '').isdigit()) or \
                              (player_id.isdigit() and len(player_id) >= 10)

                if is_likely_id:
                    logger.info(f"Found player: ID={player_id}, Name={player_name}")
                    players.append(PlayerInfo(
                        player_id=player_id,
                        player_name=player_name,
                        is_online=True
                    ))
                    i += 2
                else:
                    # Not an ID pattern, try swapping (Name, ID)
                    is_second_id = (len(player_name) >= 15 and player_name.replace('-', '').isdigit()) or \
                                  (player_name.isdigit() and len(player_name) >= 10)
                    if is_second_id:
                        logger.info(f"Found player (name first): ID={player_name}, Name={player_id}")
                        players.append(PlayerInfo(
                            player_id=player_name,
                            player_name=player_id,
                            is_online=True
                        ))
                        i += 2
                    else:
                        # Neither looks like an ID, skip this pair
                        logger.debug(f"Skipping non-ID pair: {player_id}, {player_name}")
                        i += 2
            else:
                # Odd number of parts, skip the last one
                logger.debug(f"Skipping trailing part: {parts[i]}")
                i += 1

        logger.info(f"Parsed {len(players)} players from response")

        # Enrich each player with detailed data (dino, gender, growth)
        for player in players:
            try:
                player_data = await self.get_player_data(player.player_id)
                if player_data:
                    player.dinosaur = player_data.get('dinosaur')
                    player.gender = player_data.get('gender')
                    player.growth = player_data.get('growth')
                    player.is_admin = player_data.get('is_admin', False)
                    player.is_prime_elder = player_data.get('is_prime_elder', False)
                    logger.info(f"Enriched {player.player_name}: {player.dinosaur}, {player.gender}, {player.growth}, prime={player.is_prime_elder}")
            except Exception as e:
                logger.warning(f"Could not get detailed data for {player.player_id}: {e}")

        return players

    async def save(self) -> RCONResponse:
        """Save the server state."""
        try:
            # Save: \x02\x50\x00
            command = b'\x02\x50\x00'
            response = await self._send_command(command)
            return RCONResponse(
                success=True,
                message="Server saved",
                raw_response=response
            )
        except RCONCommandError as e:
            return RCONResponse(success=False, message=str(e))

    async def get_server_info(self) -> Optional[dict]:
        """Get server information."""
        try:
            # Server Info: \x02\x12\x00
            command = b'\x02\x12\x00'
            response = await self._send_command(command)
            return {"raw": response} if response else None
        except RCONCommandError:
            return None

    async def wipe_corpses(self) -> RCONResponse:
        """
        Wipe all corpses from the server.

        NOTE: The game logs show empty brackets [] instead of the command name,
        but the command works correctly - this is just a cosmetic logging issue
        in The Isle Evrima.
        """
        try:
            # Wipe Corpses: \x02\x13\x00
            command = b'\x02\x13\x00'
            response = await self._send_command(command)
            return RCONResponse(
                success=True,
                message="All corpses wiped from server",
                raw_response=response
            )
        except RCONCommandError as e:
            return RCONResponse(success=False, message=str(e))

    async def update_playables(self, dino_list: str) -> RCONResponse:
        """Update list of allowed playable dinosaurs.

        Args:
            dino_list: Comma-separated list of dinosaur names
        """
        try:
            # Update Playables: \x02\x15 + dino_list + \x00
            command = b'\x02\x15' + dino_list.encode() + b'\x00'
            response = await self._send_command(command)
            return RCONResponse(
                success=True,
                message="Playables updated",
                data={"dino_list": dino_list},
                raw_response=response
            )
        except RCONCommandError as e:
            return RCONResponse(success=False, message=str(e))

    async def toggle_whitelist(self, enabled: bool) -> RCONResponse:
        """Toggle whitelist on/off.

        Args:
            enabled: True to enable whitelist, False to disable

        Note: The game logs show the inverse of what's sent (game bug), but the
        actual behavior is correct. Send 1 to enable, 0 to disable.
        """
        try:
            # Toggle Whitelist: \x02\x81 + (1 or 0) + \x00
            value = b'1' if enabled else b'0'
            command = b'\x02\x81' + value + b'\x00'
            response = await self._send_command(command)
            return RCONResponse(
                success=True,
                message=f"Whitelist {'enabled' if enabled else 'disabled'}",
                raw_response=response
            )
        except RCONCommandError as e:
            return RCONResponse(success=False, message=str(e))

    async def add_whitelist(self, player_ids: str) -> RCONResponse:
        """Add player IDs to whitelist.

        Args:
            player_ids: Comma-separated list of Steam IDs
        """
        try:
            # Add Whitelist IDs: \x02\x82 + player_ids + \x00
            command = b'\x02\x82' + player_ids.encode() + b'\x00'
            response = await self._send_command(command)
            return RCONResponse(
                success=True,
                message="Players added to whitelist",
                data={"player_ids": player_ids},
                raw_response=response
            )
        except RCONCommandError as e:
            return RCONResponse(success=False, message=str(e))

    async def remove_whitelist(self, player_ids: str) -> RCONResponse:
        """Remove player IDs from whitelist.

        Args:
            player_ids: Comma-separated list of Steam IDs
        """
        try:
            # Remove Whitelist IDs: \x02\x83 + player_ids + \x00
            command = b'\x02\x83' + player_ids.encode() + b'\x00'
            response = await self._send_command(command)
            return RCONResponse(
                success=True,
                message="Players removed from whitelist",
                data={"player_ids": player_ids},
                raw_response=response
            )
        except RCONCommandError as e:
            return RCONResponse(success=False, message=str(e))

    async def toggle_global_chat(self, enabled: bool) -> RCONResponse:
        """Toggle global chat on/off.

        Args:
            enabled: True to enable global chat, False to disable

        Note: The game logs show the inverse of what's sent (game bug), but the
        actual behavior is correct. Send 1 to enable, 0 to disable.
        """
        try:
            # Toggle Global Chat: \x02\x84 + (1 or 0) + \x00
            value = b'1' if enabled else b'0'
            command = b'\x02\x84' + value + b'\x00'
            response = await self._send_command(command)
            return RCONResponse(
                success=True,
                message=f"Global chat {'enabled' if enabled else 'disabled'}",
                raw_response=response
            )
        except RCONCommandError as e:
            return RCONResponse(success=False, message=str(e))

    async def toggle_humans(self, enabled: bool) -> RCONResponse:
        """Toggle human players on/off.

        Args:
            enabled: True to enable humans, False to disable

        Note: The game logs show the inverse of what's sent (game bug), but the
        actual behavior is correct. Send 1 to enable, 0 to disable.
        """
        try:
            # Toggle Humans: \x02\x86 + (1 or 0) + \x00
            value = b'1' if enabled else b'0'
            command = b'\x02\x86' + value + b'\x00'
            response = await self._send_command(command)
            return RCONResponse(
                success=True,
                message=f"Humans {'enabled' if enabled else 'disabled'}",
                raw_response=response
            )
        except RCONCommandError as e:
            return RCONResponse(success=False, message=str(e))

    async def toggle_ai(self, enabled: bool) -> RCONResponse:
        """Toggle AI on/off.

        Args:
            enabled: True to enable AI, False to disable

        Note: The game logs show the inverse of what's sent (game bug), but the
        actual behavior is correct. Send 1 to enable, 0 to disable.
        """
        try:
            # Toggle AI: \x02\x90 + (1 or 0) + \x00
            value = b'1' if enabled else b'0'
            command = b'\x02\x90' + value + b'\x00'
            response = await self._send_command(command)
            return RCONResponse(
                success=True,
                message=f"AI {'enabled' if enabled else 'disabled'}",
                raw_response=response
            )
        except RCONCommandError as e:
            return RCONResponse(success=False, message=str(e))

    async def disable_ai_classes(self, dino_list: str) -> RCONResponse:
        """Disable specific AI dinosaur classes.

        Args:
            dino_list: Comma-separated list of dinosaur names to disable
        """
        try:
            # Disable AI Classes: \x02\x91 + dino_list + \x00
            command = b'\x02\x91' + dino_list.encode() + b'\x00'
            response = await self._send_command(command)
            return RCONResponse(
                success=True,
                message="AI classes disabled",
                data={"dino_list": dino_list},
                raw_response=response
            )
        except RCONCommandError as e:
            return RCONResponse(success=False, message=str(e))

    async def set_ai_density(self, density: float) -> RCONResponse:
        """Set AI spawn density.

        Args:
            density: AI density value (typically 0.0 to 1.0)
        """
        try:
            # AI Density: \x02\x92 + density_string + \x00
            command = b'\x02\x92' + str(density).encode() + b'\x00'
            response = await self._send_command(command)
            return RCONResponse(
                success=True,
                message=f"AI density set to {density}",
                data={"density": density},
                raw_response=response
            )
        except RCONCommandError as e:
            return RCONResponse(success=False, message=str(e))

    async def get_player_data(self, player_id: str) -> Optional[dict]:
        """Get detailed player data by Steam ID.

        Returns dict with: dinosaur, gender, growth, is_admin, raw
        Response format appears to be newline-separated like player list.
        """
        try:
            # Player Data: \x02\x77 + player_id + \x00
            command = b'\x02\x77' + player_id.encode() + b'\x00'
            response = await self._send_command(command)

            if not response:
                return None

            logger.info(f"Player data for {player_id}: {repr(response)}")

            # Parse the response to extract dino, gender, growth
            # Format: Name: X, PlayerID: Y, Gender: Z, Class: Dinosaur, Growth: 0.29, ...
            data = {"raw": response}

            # The data is comma-separated key:value pairs
            # Split into key-value pairs
            import re

            # Extract key-value pairs using regex
            # Pattern: Key: Value (where value is everything until the next key or comma)
            pairs = re.findall(r'(\w+):\s*([^,\n]+)', response)

            for key, value in pairs:
                key_lower = key.lower()
                value = value.strip()

                if key_lower == 'class':
                    data['dinosaur'] = value
                elif key_lower == 'gender':
                    data['gender'] = value  # Already "Male" or "Female"
                elif key_lower == 'growth':
                    try:
                        data['growth'] = float(value)
                    except ValueError:
                        pass
                elif key_lower == 'primeelder':
                    data['is_prime_elder'] = value.lower() == 'true'
                elif key_lower == 'admin' or value.lower() == 'admin':
                    data['is_admin'] = True

            logger.info(f"Parsed player data: dino={data.get('dinosaur')}, gender={data.get('gender')}, growth={data.get('growth')}, prime_elder={data.get('is_prime_elder')}")
            return data
        except RCONCommandError:
            return None

    async def console(self, command: str) -> RCONResponse:
        """
        Send a raw console command to the server.

        This is a generic passthrough for any RCON command not explicitly supported.
        Note: The Isle Evrima doesn't have a generic "console command" protocol,
        so this attempts to send the command as-is. Use with caution.

        Args:
            command: Raw console command string
        """
        try:
            # Try sending as raw command - this may or may not work depending on the command
            command_bytes = command.encode() + b'\x00'
            response = await self._send_command(command_bytes)
            return RCONResponse(
                success=True,
                message=f"Command sent: {command}",
                data={"command": command},
                raw_response=response
            )
        except RCONCommandError as e:
            return RCONResponse(
                success=False,
                message=f"Console command failed: {e}"
            )


class PathOfTitansRCONClient(BaseRCONClient):
    """
    RCON client for Path of Titans.

    Uses standard Source RCON protocol via gamercon-async library.
    Commands are sent as text:
    - /kick <player> <reason>
    - /ban <player> <reason>
    - /unban <player>
    - /announce <message>
    - /whisper <player> <message>
    - /listplayers
    - /save
    """

    def __init__(self, host: str, port: int, password: str):
        super().__init__(host, port, password)
        self.game_type = GameType.PATH_OF_TITANS
        self._client = None

    async def connect(self) -> bool:
        """Connect to Path of Titans RCON server."""
        try:
            from gamercon_async import GameRCON

            self._client = GameRCON(self.host, self.port, self.password)
            logger.info(f"PoT RCON client created for {self.host}:{self.port}")
            return True
        except ImportError:
            raise RCONError("gamercon-async library not installed")
        except Exception as e:
            logger.error(f"Failed to create PoT RCON client: {e}")
            raise RCONConnectionError(f"Connection failed: {e}")

    async def disconnect(self) -> None:
        """Disconnect from Path of Titans RCON server."""
        self._client = None

    async def _execute(self, command: str) -> str:
        """Execute an RCON command."""
        if not self._client:
            await self.connect()

        try:
            result = await self._client.send(command)
            return result if result else ""
        except Exception as e:
            logger.error(f"PoT RCON command failed: {e}")
            raise RCONCommandError(str(e))

    async def kick(self, player_id: str, reason: str = "") -> RCONResponse:
        """Kick a player by Alderon ID."""
        try:
            cmd = f"/kick {player_id}"
            if reason:
                cmd += f" {reason}"
            response = await self._execute(cmd)
            return RCONResponse(
                success=True,
                message=f"Kicked player {player_id}",
                data={"player_id": player_id, "reason": reason},
                raw_response=response
            )
        except RCONCommandError as e:
            return RCONResponse(success=False, message=str(e))

    async def ban(self, player_id: str, reason: str = "") -> RCONResponse:
        """Ban a player by Alderon ID."""
        try:
            cmd = f"/ban {player_id}"
            if reason:
                cmd += f" {reason}"
            response = await self._execute(cmd)
            return RCONResponse(
                success=True,
                message=f"Banned player {player_id}",
                data={"player_id": player_id, "reason": reason},
                raw_response=response
            )
        except RCONCommandError as e:
            return RCONResponse(success=False, message=str(e))

    async def unban(self, player_id: str) -> RCONResponse:
        """Unban a player by Alderon ID."""
        try:
            response = await self._execute(f"/unban {player_id}")
            return RCONResponse(
                success=True,
                message=f"Unbanned player {player_id}",
                data={"player_id": player_id},
                raw_response=response
            )
        except RCONCommandError as e:
            return RCONResponse(success=False, message=str(e))

    async def announce(self, message: str) -> RCONResponse:
        """Send a server-wide announcement."""
        try:
            response = await self._execute(f"/announce {message}")
            return RCONResponse(
                success=True,
                message="Announcement sent",
                data={"announcement": message},
                raw_response=response
            )
        except RCONCommandError as e:
            return RCONResponse(success=False, message=str(e))

    async def dm(self, player_id: str, message: str) -> RCONResponse:
        """Send a direct message (whisper) to a player."""
        try:
            response = await self._execute(f"/whisper {player_id} {message}")
            return RCONResponse(
                success=True,
                message=f"Message sent to {player_id}",
                data={"player_id": player_id, "message": message},
                raw_response=response
            )
        except RCONCommandError as e:
            return RCONResponse(success=False, message=str(e))

    async def get_players(self) -> list[PlayerInfo]:
        """Get list of online players."""
        try:
            response = await self._execute("/listplayers")
            players = []
            if response:
                # Parse PoT player list format
                # Format: AlderonID, PlayerName
                for line in response.strip().split('\n'):
                    if line.strip() and ',' in line:
                        parts = line.split(',', 1)
                        if len(parts) >= 2:
                            players.append(PlayerInfo(
                                player_id=parts[0].strip(),
                                player_name=parts[1].strip(),
                                is_online=True
                            ))
                    elif line.strip():
                        players.append(PlayerInfo(
                            player_id=line.strip(),
                            player_name=line.strip(),
                            is_online=True
                        ))
            return players
        except RCONCommandError:
            return []

    async def save(self) -> RCONResponse:
        """Save the server state."""
        try:
            response = await self._execute("/save")
            return RCONResponse(
                success=True,
                message="Server saved",
                raw_response=response
            )
        except RCONCommandError as e:
            return RCONResponse(success=False, message=str(e))

    async def console(self, command: str) -> RCONResponse:
        """
        Send a raw console command to the server.

        For Path of Titans, commands should start with / (e.g., /help, /save, /announce).

        Args:
            command: Raw console command string
        """
        try:
            response = await self._execute(command)
            return RCONResponse(
                success=True,
                message=f"Command executed: {command}",
                data={"command": command},
                raw_response=response
            )
        except RCONCommandError as e:
            return RCONResponse(
                success=False,
                message=f"Console command failed: {e}"
            )


def get_rcon_client(game_type: GameType | str, host: str, port: int, password: str) -> BaseRCONClient:
    """
    Factory function to get the appropriate RCON client.

    Args:
        game_type: The game type (GameType enum or string)
        host: RCON server host
        port: RCON server port
        password: RCON password

    Returns:
        Appropriate RCON client instance
    """
    if isinstance(game_type, str):
        game_type = GameType(game_type)

    if game_type == GameType.THE_ISLE_EVRIMA:
        return EvrimaRCONClient(host, port, password)
    elif game_type == GameType.PATH_OF_TITANS:
        return PathOfTitansRCONClient(host, port, password)
    else:
        raise ValueError(f"Unsupported game type: {game_type}")


class RCONManager:
    """
    Manager for handling RCON operations across multiple servers.

    Provides methods for executing commands on specific servers or all servers.
    """

    def __init__(self):
        self._clients: dict[int, BaseRCONClient] = {}  # server_id -> client

    def get_client(self, server_id: int, game_type: GameType, host: str,
                   port: int, password: str) -> BaseRCONClient:
        """Get or create an RCON client for a server."""
        if server_id not in self._clients:
            self._clients[server_id] = get_rcon_client(game_type, host, port, password)
        return self._clients[server_id]

    def remove_client(self, server_id: int) -> None:
        """Remove a cached client."""
        if server_id in self._clients:
            del self._clients[server_id]

    async def execute_on_servers(
        self,
        servers: list[dict],
        command: str,
        *args,
        **kwargs
    ) -> dict[int, RCONResponse]:
        """
        Execute a command on multiple servers.

        Args:
            servers: List of server configs (id, game_type, host, port, password)
            command: Command method name (kick, ban, announce, etc.)
            *args: Arguments to pass to the command
            **kwargs: Keyword arguments to pass to the command

        Returns:
            Dict mapping server_id to RCONResponse
        """
        results = {}

        async def run_on_server(server: dict):
            try:
                client = self.get_client(
                    server['id'],
                    GameType(server['game_type']),
                    server['host'],
                    server['port'],
                    server['password']
                )
                method = getattr(client, command)
                response = await method(*args, **kwargs)

                # Update connection status in database
                from database.queries import RCONServerQueries
                RCONServerQueries.update_connection_status(
                    server['id'],
                    success=response.success,
                    error=response.message if not response.success else None
                )

                return server['id'], response
            except Exception as e:
                # Update connection status with error
                from database.queries import RCONServerQueries
                error_msg = f"Error on {server.get('server_name', 'Unknown')}: {e}"
                RCONServerQueries.update_connection_status(
                    server['id'],
                    success=False,
                    error=str(e)
                )

                return server['id'], RCONResponse(
                    success=False,
                    message=error_msg
                )

        # Execute on all servers concurrently
        tasks = [run_on_server(server) for server in servers]
        for coro in asyncio.as_completed(tasks):
            server_id, response = await coro
            results[server_id] = response

        return results


# Global manager instance
rcon_manager = RCONManager()
