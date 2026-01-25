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
    allocation: dict  # ip, port, alias


@dataclass
class ServerResources:
    """Server resource utilization."""
    cpu_percent: float
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
                servers.append(ServerInfo(
                    server_id=attrs.get('identifier', ''),
                    name=attrs.get('name', 'Unknown'),
                    uuid=attrs.get('uuid', ''),
                    description=attrs.get('description', ''),
                    status=self._parse_status(attrs),
                    is_suspended=attrs.get('is_suspended', False),
                    node=attrs.get('node', 'Unknown'),
                    allocation=attrs.get('allocation', {})
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
            attrs = response.get('attributes', {})
            return ServerInfo(
                server_id=attrs.get('identifier', server_id),
                name=attrs.get('name', 'Unknown'),
                uuid=attrs.get('uuid', ''),
                description=attrs.get('description', ''),
                status=self._parse_status(attrs),
                is_suspended=attrs.get('is_suspended', False),
                node=attrs.get('node', 'Unknown'),
                allocation=attrs.get('allocation', {})
            )
        except Exception as e:
            logger.error(f"Failed to get server info: {e}")
            return None

    async def get_server_resources(self, server_id: str) -> Optional[ServerResources]:
        """Get server resource utilization."""
        try:
            client = await self._get_client()
            response = await asyncio.to_thread(
                client.client.servers.get_server_utilization,
                server_id
            )
            attrs = response.get('attributes', {})
            resources = attrs.get('resources', {})
            return ServerResources(
                cpu_percent=resources.get('cpu_absolute', 0),
                memory_bytes=resources.get('memory_bytes', 0),
                memory_limit_bytes=attrs.get('limits', {}).get('memory', 0) * 1024 * 1024,
                disk_bytes=resources.get('disk_bytes', 0),
                disk_limit_bytes=attrs.get('limits', {}).get('disk', 0) * 1024 * 1024,
                network_rx_bytes=resources.get('network_rx_bytes', 0),
                network_tx_bytes=resources.get('network_tx_bytes', 0),
                uptime_seconds=resources.get('uptime', 0)
            )
        except Exception as e:
            logger.error(f"Failed to get server resources: {e}")
            return None

    # ==========================================
    # FILE OPERATIONS
    # ==========================================

    async def list_files(self, server_id: str, directory: str = "/") -> list[FileInfo]:
        """
        List files in a directory.

        Args:
            server_id: Server identifier
            directory: Directory path (default: root)
        """
        try:
            client = await self._get_client()
            response = await asyncio.to_thread(
                client.client.servers.files.list_files,
                server_id,
                directory
            )

            files = []
            for file_data in response.get('data', []):
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
            logger.error(f"Failed to list files: {e}")
            return []

    async def read_file(self, server_id: str, file_path: str) -> Optional[str]:
        """
        Read file contents.

        Args:
            server_id: Server identifier
            file_path: Path to the file
        """
        try:
            client = await self._get_client()
            content = await asyncio.to_thread(
                client.client.servers.files.get_file_contents,
                server_id,
                file_path
            )
            return content
        except Exception as e:
            logger.error(f"Failed to read file: {e}")
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
            client = await self._get_client()
            response = await asyncio.to_thread(
                client.client.servers.files.download_file,
                server_id,
                file_path
            )
            return response.get('attributes', {}).get('url')
        except Exception as e:
            logger.error(f"Failed to get download URL: {e}")
            return None

    async def delete_file(self, server_id: str, file_path: str) -> PteroResponse:
        """Delete a file or directory."""
        try:
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
