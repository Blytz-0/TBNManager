# services/pterodactyl.py
"""
Pterodactyl Panel API integration for game server management.

Provides:
- Server power control (start, stop, restart, kill)
- Server information and resource usage
- File operations (list, read, write, download)
- Console command execution
- Server discovery from API
"""

import asyncio
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


class PowerAction(Enum):
    """Server power actions."""
    START = "start"
    STOP = "stop"
    RESTART = "restart"
    KILL = "kill"


class ServerStatus(Enum):
    """Server power states."""
    RUNNING = "running"
    STARTING = "starting"
    STOPPING = "stopping"
    OFFLINE = "offline"
    UNKNOWN = "unknown"


@dataclass
class ServerInfo:
    """Pterodactyl server information."""
    server_id: str
    name: str
    uuid: str
    description: str
    status: ServerStatus
    is_suspended: bool
    node: str
    allocation: dict  # ip, port, alias (kept for backwards compatibility)
    ip: str
    port: int
    rcon_port: Optional[int] = None
    game_type: Optional[str] = None


@dataclass
class ServerResources:
    """Server resource utilization."""
    cpu_percent: float
    cpu_limit: int
    memory_bytes: int
    memory_limit_bytes: int
    disk_bytes: int
    disk_limit_bytes: int
    network_rx_bytes: int
    network_tx_bytes: int
    uptime_seconds: int


@dataclass
class FileInfo:
    """File or directory information."""
    name: str
    mode: str
    size: int
    is_file: bool
    is_symlink: bool
    is_editable: bool
    mimetype: str
    created_at: str
    modified_at: str


@dataclass
class PteroResponse:
    """Standardized response from Pterodactyl operations."""
    success: bool
    message: str
    data: Optional[dict] = None


class PterodactylError(Exception):
    """Base exception for Pterodactyl errors."""
    pass


class PterodactylAuthError(PterodactylError):
    """Authentication failed."""
    pass


class PterodactylNotFoundError(PterodactylError):
    """Resource not found."""
    pass


class PterodactylClient:
    """
    Pterodactyl Panel API client.

    Uses py-dactyl library for API communication.
    Supports both client API (user-scoped) and application API (admin).
    """

    def __init__(self, panel_url: str, api_key: str):
        """
        Initialize Pterodactyl client.

        Args:
            panel_url: Base URL of the Pterodactyl panel (e.g., https://panel.example.com)
            api_key: Client API key (ptlc_xxx) or Application API key (ptla_xxx)
        """
        self.panel_url = panel_url.rstrip('/')
        self.api_key = api_key
        self._client = None
        self._is_application_key = api_key.startswith('ptla_')

    async def _get_client(self):
        """Get or create the pydactyl client."""
        if self._client is None:
            try:
                from pydactyl import PterodactylClient as PyDactylClient

                self._client = PyDactylClient(self.panel_url, self.api_key)
                logger.info(f"Pterodactyl client created for {self.panel_url}")
            except ImportError:
                raise PterodactylError("py-dactyl library not installed")
        return self._client

    async def test_connection(self) -> PteroResponse:
        """Test connection and authentication."""
        try:
            client = await self._get_client()
            # Try to list servers to verify connection
            servers = await asyncio.to_thread(client.client.servers.list_servers)
            return PteroResponse(
                success=True,
                message=f"Connected successfully. Found {len(servers.get('data', []))} server(s).",
                data={"server_count": len(servers.get('data', []))}
            )
        except Exception as e:
            logger.error(f"Pterodactyl connection test failed: {e}")
            if "401" in str(e) or "403" in str(e):
                return PteroResponse(success=False, message="Authentication failed. Check your API key.")
            return PteroResponse(success=False, message=f"Connection failed: {e}")

    # ==========================================
    # SERVER DISCOVERY
    # ==========================================

    async def list_servers(self) -> list[ServerInfo]:
        """
        List all servers accessible with the API key.

        Returns:
            List of ServerInfo objects
        """
        try:
            client = await self._get_client()
            response = await asyncio.to_thread(client.client.servers.list_servers)

            servers = []
            for server_data in response.get('data', []):
                attrs = server_data.get('attributes', {})

                # Extract allocation (IP, port)
                allocation_data = attrs.get('allocation', {})
                ip = allocation_data.get('ip', 'Unknown')
                port = allocation_data.get('port', 0)

                servers.append(ServerInfo(
                    server_id=attrs.get('identifier', ''),
                    name=attrs.get('name', 'Unknown'),
                    uuid=attrs.get('uuid', ''),
                    description=attrs.get('description', ''),
                    status=self._parse_status(attrs),
                    is_suspended=attrs.get('is_suspended', False),
                    node=attrs.get('node', 'Unknown'),
                    allocation=allocation_data,
                    ip=ip,
                    port=port,
                    rcon_port=None,  # Not available in list view
                    game_type=None  # Not available in list view
                ))
            return servers
        except Exception as e:
            logger.error(f"Failed to list servers: {e}")
            return []

    def _parse_status(self, attrs: dict) -> ServerStatus:
        """Parse server status from attributes."""
        status = attrs.get('status', 'unknown')
        try:
            return ServerStatus(status)
        except ValueError:
            return ServerStatus.UNKNOWN

    # ==========================================
    # POWER CONTROL
    # ==========================================

    async def send_power_action(self, server_id: str, action: PowerAction) -> PteroResponse:
        """
        Send a power action to a server.

        Args:
            server_id: Server identifier
            action: PowerAction enum value
        """
        try:
            client = await self._get_client()
            await asyncio.to_thread(
                client.client.servers.send_power_action,
                server_id,
                action.value
            )
            return PteroResponse(
                success=True,
                message=f"Power action '{action.value}' sent to server",
                data={"server_id": server_id, "action": action.value}
            )
        except Exception as e:
            logger.error(f"Power action failed: {e}")
            return PteroResponse(success=False, message=f"Power action failed: {e}")

    async def start_server(self, server_id: str) -> PteroResponse:
        """Start a server."""
        return await self.send_power_action(server_id, PowerAction.START)

    async def stop_server(self, server_id: str) -> PteroResponse:
        """Stop a server."""
        return await self.send_power_action(server_id, PowerAction.STOP)

    async def restart_server(self, server_id: str) -> PteroResponse:
        """Restart a server."""
        return await self.send_power_action(server_id, PowerAction.RESTART)

    async def kill_server(self, server_id: str) -> PteroResponse:
        """Force kill a server."""
        return await self.send_power_action(server_id, PowerAction.KILL)

    # ==========================================
    # SERVER INFORMATION
    # ==========================================

    async def get_server_info(self, server_id: str) -> Optional[ServerInfo]:
        """Get server information."""
        try:
            client = await self._get_client()
            response = await asyncio.to_thread(
                client.client.servers.get_server,
                server_id
            )
            logger.debug(f"get_server_info response: {response}")

            # Client API returns data directly, Application API wraps in 'attributes'
            attrs = response.get('attributes', response)

            # Extract allocation (IP, port)
            allocation_data = attrs.get('relationships', {}).get('allocations', {}).get('data', [{}])[0].get('attributes', {}) if 'relationships' in attrs else attrs.get('allocation', {})
            ip = allocation_data.get('ip', 'Unknown')
            port = allocation_data.get('port', 0)

            # Extract RCON port from variables
            rcon_port = None
            variables_data = attrs.get('relationships', {}).get('variables', {}).get('data', [])
            for var in variables_data:
                var_attrs = var.get('attributes', {})
                if var_attrs.get('env_variable') == 'RCON_PORT':
                    try:
                        rcon_port = int(var_attrs.get('server_value', 0))
                    except (ValueError, TypeError):
                        pass
                    break

            # Detect game type from docker_image or egg
            game_type = None
            docker_image = attrs.get('docker_image', '').lower()

            if 'theisle' in docker_image or 'evrima' in docker_image:
                game_type = 'The Isle Evrima'
            elif 'pathoftitans' in docker_image or 'pot' in docker_image:
                game_type = 'Path of Titans'
            else:
                # Try to detect from egg name in relationships
                egg_data = attrs.get('relationships', {}).get('egg', {}).get('attributes', {})
                egg_name = egg_data.get('name', '').lower()
                if 'isle' in egg_name or 'evrima' in egg_name:
                    game_type = 'The Isle Evrima'
                elif 'path of titans' in egg_name or 'pot' in egg_name:
                    game_type = 'Path of Titans'

            return ServerInfo(
                server_id=attrs.get('identifier', server_id),
                name=attrs.get('name', 'Unknown'),
                uuid=attrs.get('uuid', ''),
                description=attrs.get('description', ''),
                status=self._parse_status(attrs),
                is_suspended=attrs.get('is_suspended', False),
                node=attrs.get('node', 'Unknown'),
                allocation=allocation_data,
                ip=ip,
                port=port,
                rcon_port=rcon_port,
                game_type=game_type
            )
        except Exception as e:
            logger.error(f"Failed to get server info: {e}", exc_info=True)
            return None

    async def get_server_resources(self, server_id: str) -> Optional[ServerResources]:
        """Get server resource utilization."""
        try:
            client = await self._get_client()
            response = await asyncio.to_thread(
                client.client.servers.get_server_utilization,
                server_id
            )
            logger.debug(f"get_server_utilization response: {response}")

            # Client API returns data directly, Application API wraps in 'attributes'
            attrs = response.get('attributes', response)
            resources = attrs.get('resources', {})

            # Get server info for limits (Client API resources endpoint doesn't include limits)
            server_info_response = await asyncio.to_thread(
                client.client.servers.get_server,
                server_id
            )
            server_attrs = server_info_response.get('attributes', server_info_response)
            limits = server_attrs.get('limits', {})

            # Uptime is returned in milliseconds, convert to seconds
            uptime_ms = resources.get('uptime', 0)
            uptime_seconds = uptime_ms // 1000 if uptime_ms > 0 else 0

            return ServerResources(
                cpu_percent=resources.get('cpu_absolute', 0),
                cpu_limit=limits.get('cpu', 0),
                memory_bytes=resources.get('memory_bytes', 0),
                memory_limit_bytes=limits.get('memory', 0) * 1024 * 1024,
                disk_bytes=resources.get('disk_bytes', 0),
                disk_limit_bytes=limits.get('disk', 0) * 1024 * 1024,
                network_rx_bytes=resources.get('network_rx_bytes', 0),
                network_tx_bytes=resources.get('network_tx_bytes', 0),
                uptime_seconds=uptime_seconds
            )
        except Exception as e:
            logger.error(f"Failed to get server resources: {e}", exc_info=True)
            return None

    # ==========================================
    # FILE OPERATIONS
    # ==========================================

    def _normalize_path(self, path: str) -> str:
        """
        Normalize file paths by removing spaces around slashes.

        Examples:
            "TheIsle / Saved / Config" -> "/TheIsle/Saved/Config"
            "TheIsle/Saved/Config" -> "/TheIsle/Saved/Config"
            " / TheIsle / Saved" -> "/TheIsle/Saved"

        Args:
            path: Input path with potential spaces

        Returns:
            Normalized path starting with /
        """
        # Remove spaces around slashes
        normalized = path.replace(' / ', '/').replace('/ ', '/').replace(' /', '/')

        # Ensure path starts with /
        if not normalized.startswith('/'):
            normalized = '/' + normalized

        return normalized

    async def list_files(self, server_id: str, directory: str = "/") -> list[FileInfo]:
        """
        List files in a directory.

        Args:
            server_id: Server identifier
            directory: Directory path (default: root)
        """
        try:
            # Normalize path to handle spaces around slashes
            directory = self._normalize_path(directory)

            client = await self._get_client()
            response = await asyncio.to_thread(
                client.client.servers.files.list_files,
                server_id,
                directory
            )
            logger.debug(f"list_files response for {server_id} at {directory}: {response}")

            files = []
            data = response.get('data', [])
            if not data:
                logger.warning(f"list_files returned no data for server {server_id} at {directory}")
                logger.warning(f"Full response: {response}")

            for file_data in data:
                attrs = file_data.get('attributes', {})
                files.append(FileInfo(
                    name=attrs.get('name', ''),
                    mode=attrs.get('mode', ''),
                    size=attrs.get('size', 0),
                    is_file=attrs.get('is_file', False),
                    is_symlink=attrs.get('is_symlink', False),
                    is_editable=attrs.get('is_editable', False),
                    mimetype=attrs.get('mimetype', ''),
                    created_at=attrs.get('created_at', ''),
                    modified_at=attrs.get('modified_at', '')
                ))
            return files
        except Exception as e:
            logger.error(f"Failed to list files in {directory}: {e}", exc_info=True)
            return []

    async def read_file(self, server_id: str, file_path: str) -> Optional[str]:
        """
        Read file contents.

        Args:
            server_id: Server identifier
            file_path: Path to the file
        """
        try:
            # Normalize path to handle spaces around slashes
            original_path = file_path
            file_path = self._normalize_path(file_path)

            logger.info(f"read_file: Original path: '{original_path}' -> Normalized: '{file_path}'")
            logger.info(f"read_file: server_id={server_id}")

            # WORKAROUND: py-dactyl's get_file_contents returns empty dict with Client API
            # Use download URL method + HTTP fetch instead
            logger.info(f"Using download URL workaround to fetch file contents")

            # Get signed download URL
            download_url = await self.get_download_url(server_id, file_path)
            if not download_url:
                logger.error(f"Failed to get download URL for file: '{file_path}'")
                return None

            logger.info(f"Got download URL, fetching content...")

            # Fetch file content from download URL
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.get(download_url) as resp:
                    if resp.status == 200:
                        content = await resp.text()
                        logger.info(f"SUCCESS: Fetched {len(content)} bytes from download URL")
                        return content
                    else:
                        logger.error(f"HTTP {resp.status} when fetching download URL")
                        return None

        except Exception as e:
            logger.error(f"EXCEPTION reading file '{file_path}': {e}", exc_info=True)
            logger.error(f"Exception type: {type(e).__name__}")
            return None

    async def write_file(self, server_id: str, file_path: str, content: str) -> PteroResponse:
        """
        Write content to a file.

        Args:
            server_id: Server identifier
            file_path: Path to the file
            content: Content to write
        """
        try:
            # Normalize path to handle spaces around slashes
            file_path = self._normalize_path(file_path)

            client = await self._get_client()
            await asyncio.to_thread(
                client.client.servers.files.write_file,
                server_id,
                file_path,
                content
            )
            return PteroResponse(
                success=True,
                message=f"File '{file_path}' saved successfully",
                data={"file_path": file_path, "size": len(content)}
            )
        except Exception as e:
            logger.error(f"Failed to write file: {e}")
            return PteroResponse(success=False, message=f"Failed to write file: {e}")

    async def get_download_url(self, server_id: str, file_path: str) -> Optional[str]:
        """
        Get a signed download URL for a file.

        Args:
            server_id: Server identifier
            file_path: Path to the file
        """
        try:
            # Normalize path to handle spaces around slashes
            file_path = self._normalize_path(file_path)

            client = await self._get_client()
            response = await asyncio.to_thread(
                client.client.servers.files.download_file,
                server_id,
                file_path
            )
            # API may return URL directly as string or wrapped in dict
            if isinstance(response, str):
                return response
            return response.get('attributes', {}).get('url')
        except Exception as e:
            logger.error(f"Failed to get download URL: {e}", exc_info=True)
            return None

    async def delete_file(self, server_id: str, file_path: str) -> PteroResponse:
        """Delete a file or directory."""
        try:
            # Normalize path to handle spaces around slashes
            file_path = self._normalize_path(file_path)

            client = await self._get_client()
            await asyncio.to_thread(
                client.client.servers.files.delete_files,
                server_id,
                file_path
            )
            return PteroResponse(
                success=True,
                message=f"Deleted '{file_path}'",
                data={"file_path": file_path}
            )
        except Exception as e:
            logger.error(f"Failed to delete file: {e}")
            return PteroResponse(success=False, message=f"Failed to delete file: {e}")

    # ==========================================
    # CONSOLE
    # ==========================================

    async def send_command(self, server_id: str, command: str) -> PteroResponse:
        """
        Send a command to the server console.

        Args:
            server_id: Server identifier
            command: Console command to execute
        """
        try:
            client = await self._get_client()
            await asyncio.to_thread(
                client.client.servers.send_console_command,
                server_id,
                command
            )
            return PteroResponse(
                success=True,
                message=f"Command sent: {command}",
                data={"command": command}
            )
        except Exception as e:
            logger.error(f"Failed to send console command: {e}")
            return PteroResponse(success=False, message=f"Failed to send command: {e}")


class PterodactylManager:
    """
    Manager for handling Pterodactyl operations across multiple connections.

    Caches clients and provides helper methods.
    """

    def __init__(self):
        self._clients: dict[int, PterodactylClient] = {}  # connection_id -> client

    def get_client(self, connection_id: int, panel_url: str, api_key: str) -> PterodactylClient:
        """Get or create a Pterodactyl client for a connection."""
        if connection_id not in self._clients:
            self._clients[connection_id] = PterodactylClient(panel_url, api_key)
        return self._clients[connection_id]

    def remove_client(self, connection_id: int) -> None:
        """Remove a cached client."""
        if connection_id in self._clients:
            del self._clients[connection_id]

    async def discover_servers(self, connection_id: int, panel_url: str,
                               api_key: str) -> list[ServerInfo]:
        """Discover all servers from a Pterodactyl connection."""
        client = self.get_client(connection_id, panel_url, api_key)
        return await client.list_servers()


# Global manager instance
pterodactyl_manager = PterodactylManager()
