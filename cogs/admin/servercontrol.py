# cogs/admin/servercontrol.py
"""
Pterodactyl Server Control Commands (Premium)

Commands for managing game servers via Pterodactyl panel:
- Power control (start, stop, restart, kill)
- Server information and resources
- File operations (list, read, edit, download)
- Console command execution
"""

import discord
from discord import app_commands
from discord.ext import commands
from database.queries import (
    GuildQueries, PterodactylQueries, RCONCommandLogQueries
)
from services.permissions import require_permission
from services.pterodactyl import (
    PterodactylClient, pterodactyl_manager, PowerAction,
    ServerStatus, ServerInfo, ServerResources
)
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class PterodactylSetupModal(discord.ui.Modal, title="Configure Pterodactyl Connection"):
    """Modal for Pterodactyl connection setup."""

    connection_name = discord.ui.TextInput(
        label="Connection Name",
        placeholder="e.g., My Game Panel",
        required=True,
        max_length=100
    )

    panel_url = discord.ui.TextInput(
        label="Panel URL",
        placeholder="https://panel.example.com",
        required=True,
        max_length=255
    )

    api_key = discord.ui.TextInput(
        label="Client API Key",
        placeholder="Starts with ptlc_",
        required=True,
        max_length=100,
        style=discord.TextStyle.paragraph
    )

    def __init__(self, bot: commands.Bot):
        super().__init__()
        self.bot = bot

    async def on_submit(self, interaction: discord.Interaction):
        """Handle form submission."""
        await interaction.response.defer(ephemeral=True)

        try:
            GuildQueries.get_or_create(interaction.guild_id, interaction.guild.name)

            # Normalize panel URL
            panel_url = self.panel_url.value.strip()

            # Remove trailing slashes
            panel_url = panel_url.rstrip('/')

            # Remove /api/client, /admin/api, /api, /admin if present
            panel_url = panel_url.replace('/api/client', '').replace('/admin/api', '').replace('/api', '').replace('/admin', '')

            # Ensure https:// prefix
            if not panel_url.startswith(('http://', 'https://')):
                panel_url = f'https://{panel_url}'

            api_key = self.api_key.value.strip()

            # Validate API key format
            if api_key.startswith('ptla_'):
                await interaction.followup.send(
                    "❌ **Wrong API Key Type**\n\n"
                    "You provided an **Application API key** (ptla_), but you need a **Client API key** (ptlc_).\n\n"
                    "**How to get the correct key:**\n"
                    "1. Go to your Pterodactyl panel\n"
                    "2. Click your username (top right) → Account Settings\n"
                    "3. Go to **API Credentials** tab\n"
                    "4. Click **Create Client API Key**\n"
                    "5. Copy the key (starts with `ptlc_`)",
                    ephemeral=True
                )
                return
            elif not api_key.startswith('ptlc_'):
                await interaction.followup.send(
                    "⚠️ **API Key Format**\n\n"
                    "Client API keys should start with `ptlc_`. Are you sure this is the correct key?\n\n"
                    "**Where to find it:**\n"
                    "Account Settings → API Credentials → Create Client API Key",
                    ephemeral=True
                )
                return

            # Test connection first
            client = PterodactylClient(panel_url, api_key)
            test_result = await client.test_connection()

            if not test_result.success:
                error_msg = test_result.message

                # Provide helpful error messages
                if "403" in error_msg or "Forbidden" in error_msg:
                    await interaction.followup.send(
                        f"❌ **Authentication Failed**\n\n"
                        f"The API key was rejected by the panel.\n\n"
                        f"**Possible causes:**\n"
                        f"• Wrong API key\n"
                        f"• API key was deleted\n"
                        f"• Using Application API key instead of Client API key\n\n"
                        f"**Panel URL tried:** `{panel_url}`\n"
                        f"**Error:** {error_msg}",
                        ephemeral=True
                    )
                elif "404" in error_msg or "Not Found" in error_msg:
                    await interaction.followup.send(
                        f"❌ **Panel Not Found**\n\n"
                        f"Could not find the Pterodactyl API at this URL.\n\n"
                        f"**Panel URL tried:** `{panel_url}`\n\n"
                        f"**Make sure:**\n"
                        f"• The URL is correct (just the base domain)\n"
                        f"• The panel is running and accessible\n"
                        f"• You're using the correct protocol (https/http)\n\n"
                        f"**Error:** {error_msg}",
                        ephemeral=True
                    )
                else:
                    await interaction.followup.send(
                        f"❌ **Connection Failed**\n\n"
                        f"{error_msg}\n\n"
                        f"**Panel URL tried:** `{panel_url}`\n\n"
                        f"Please check your panel URL and API key.",
                        ephemeral=True
                    )
                return

            # Save connection
            connection_id = PterodactylQueries.add_connection(
                guild_id=interaction.guild_id,
                connection_name=self.connection_name.value,
                panel_url=panel_url,
                api_key=api_key
            )

            # Discover servers
            servers = await client.list_servers()

            # Save discovered servers
            for server in servers:
                PterodactylQueries.add_discovered_server(
                    connection_id=connection_id,
                    guild_id=interaction.guild_id,
                    server_id=server.server_id,
                    server_name=server.name,
                    server_uuid=server.uuid
                )

            embed = discord.Embed(
                title="✅ Pterodactyl Connection Added",
                description=f"Connection **{self.connection_name.value}** configured successfully!",
                color=discord.Color.green()
            )
            embed.add_field(name="Panel URL", value=f"`{panel_url}`", inline=False)
            embed.add_field(name="Servers Found", value=str(len(servers)), inline=True)

            if servers:
                server_list = "\n".join([f"• {s.name}" for s in servers[:5]])
                if len(servers) > 5:
                    server_list += f"\n... and {len(servers) - 5} more"
                embed.add_field(name="Discovered Servers", value=server_list, inline=False)
            else:
                embed.add_field(
                    name="⚠️ No Servers",
                    value="No servers found. This API key may not have access to any servers.",
                    inline=False
                )

            embed.set_footer(text="Use /server list to see all servers")

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Error setting up Pterodactyl: {e}", exc_info=True)
            await interaction.followup.send(
                f"❌ **Error**\n\nAn unexpected error occurred: {str(e)}",
                ephemeral=True
            )


class ServerControlCommands(commands.GroupCog, name="server"):
    """Pterodactyl server control commands."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        super().__init__()

    # ==========================================
    # CONNECTION SETUP
    # ==========================================

    @app_commands.command(name="setup", description="Configure Pterodactyl panel connection")
    @app_commands.guild_only()
    async def setup_connection(self, interaction: discord.Interaction):
        """Configure a new Pterodactyl panel connection."""
        if not await require_permission(interaction, 'server_setup'):
            return

        modal = PterodactylSetupModal(self.bot)
        await interaction.response.send_modal(modal)

    @app_commands.command(name="connections", description="List Pterodactyl connections")
    @app_commands.guild_only()
    async def list_connections(self, interaction: discord.Interaction):
        """List all Pterodactyl connections."""
        if not await require_permission(interaction, 'server_setup'):
            return

        try:
            connections = PterodactylQueries.get_connections(interaction.guild_id)

            if not connections:
                await interaction.response.send_message(
                    "No Pterodactyl connections configured. Use `/server setup` to add one.",
                    ephemeral=True
                )
                return

            embed = discord.Embed(
                title="Pterodactyl Connections",
                color=discord.Color.blue()
            )

            for conn in connections:
                servers = PterodactylQueries.get_pterodactyl_servers(
                    interaction.guild_id, conn['id']
                )
                last_conn = conn.get('last_connected_at')
                last_conn_str = last_conn.strftime("%Y-%m-%d %H:%M") if last_conn else "Never"

                embed.add_field(
                    name=conn['connection_name'],
                    value=f"**Panel:** {conn['panel_url']}\n"
                          f"**Servers:** {len(servers)}\n"
                          f"**Last Connected:** {last_conn_str}",
                    inline=False
                )

            await interaction.response.send_message(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Error listing connections: {e}", exc_info=True)
            await interaction.response.send_message(
                "An error occurred while listing connections.",
                ephemeral=True
            )

    # ==========================================
    # SERVER INFORMATION
    # ==========================================

    @app_commands.command(name="list", description="List all servers from Pterodactyl")
    @app_commands.guild_only()
    async def list_servers(self, interaction: discord.Interaction):
        """List all servers from Pterodactyl connections."""
        if not await require_permission(interaction, 'server_info'):
            return

        try:
            servers = PterodactylQueries.get_pterodactyl_servers(interaction.guild_id)

            if not servers:
                await interaction.response.send_message(
                    "No servers found. Configure a Pterodactyl connection with `/server setup`.",
                    ephemeral=True
                )
                return

            embed = discord.Embed(
                title="Game Servers",
                description=f"Found {len(servers)} server(s)",
                color=discord.Color.blue()
            )

            for server in servers[:10]:
                default = " (Default)" if server.get('is_default') else ""
                status = server.get('last_status', 'Unknown')
                embed.add_field(
                    name=f"{server['server_name']}{default}",
                    value=f"**ID:** `{server['server_id']}`\n**Status:** {status}",
                    inline=True
                )

            if len(servers) > 10:
                embed.set_footer(text=f"Showing 10 of {len(servers)} servers")

            await interaction.response.send_message(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Error listing servers: {e}", exc_info=True)
            await interaction.response.send_message(
                "An error occurred while listing servers.",
                ephemeral=True
            )

    @app_commands.command(name="info", description="Show server information and resources")
    @app_commands.guild_only()
    @app_commands.describe(server="Server to get info for")
    async def server_info(self, interaction: discord.Interaction, server: str):
        """Show detailed server information."""
        if not await require_permission(interaction, 'server_info'):
            return

        await interaction.response.defer(ephemeral=True)

        try:
            client, server_id = await self._get_client_for_server(
                interaction.guild_id, server
            )

            if not client:
                await interaction.followup.send(
                    f"Server `{server}` not found.",
                    ephemeral=True
                )
                return

            # Get server info and resources
            info = await client.get_server_info(server_id)
            resources = await client.get_server_resources(server_id)

            if not info:
                await interaction.followup.send(
                    "Failed to get server information.",
                    ephemeral=True
                )
                return

            embed = discord.Embed(
                title=f"Server: {info.name}",
                color=self._status_color(info.status)
            )

            embed.add_field(name="Status", value=info.status.value.title(), inline=True)
            embed.add_field(name="Node", value=info.node, inline=True)
            embed.add_field(name="Server ID", value=f"`{info.server_id}`", inline=True)

            if info.description:
                embed.add_field(name="Description", value=info.description, inline=False)

            if resources:
                # Format memory
                mem_used = resources.memory_bytes / (1024 * 1024)
                mem_limit = resources.memory_limit_bytes / (1024 * 1024)
                mem_pct = (mem_used / mem_limit * 100) if mem_limit > 0 else 0

                # Format disk
                disk_used = resources.disk_bytes / (1024 * 1024 * 1024)
                disk_limit = resources.disk_limit_bytes / (1024 * 1024 * 1024)

                # Format uptime
                uptime_hours = resources.uptime_seconds / 3600

                embed.add_field(
                    name="CPU",
                    value=f"{resources.cpu_percent:.1f}%",
                    inline=True
                )
                embed.add_field(
                    name="Memory",
                    value=f"{mem_used:.0f}/{mem_limit:.0f} MB ({mem_pct:.0f}%)",
                    inline=True
                )
                embed.add_field(
                    name="Disk",
                    value=f"{disk_used:.1f}/{disk_limit:.1f} GB",
                    inline=True
                )
                embed.add_field(
                    name="Uptime",
                    value=f"{uptime_hours:.1f} hours",
                    inline=True
                )

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Error getting server info: {e}", exc_info=True)
            await interaction.followup.send(
                f"An error occurred: {e}",
                ephemeral=True
            )

    # ==========================================
    # POWER CONTROL
    # ==========================================

    @app_commands.command(name="start", description="Start a game server")
    @app_commands.guild_only()
    @app_commands.describe(server="Server to start")
    async def start_server(self, interaction: discord.Interaction, server: str):
        """Start a server."""
        await self._power_action(interaction, server, PowerAction.START, 'server_start')

    @app_commands.command(name="stop", description="Stop a game server")
    @app_commands.guild_only()
    @app_commands.describe(server="Server to stop")
    async def stop_server(self, interaction: discord.Interaction, server: str):
        """Stop a server."""
        await self._power_action(interaction, server, PowerAction.STOP, 'server_stop')

    @app_commands.command(name="restart", description="Restart a game server")
    @app_commands.guild_only()
    @app_commands.describe(server="Server to restart")
    async def restart_server(self, interaction: discord.Interaction, server: str):
        """Restart a server."""
        await self._power_action(interaction, server, PowerAction.RESTART, 'server_restart')

    @app_commands.command(name="kill", description="Force kill a game server")
    @app_commands.guild_only()
    @app_commands.describe(server="Server to kill")
    async def kill_server(self, interaction: discord.Interaction, server: str):
        """Force kill a server."""
        await self._power_action(interaction, server, PowerAction.KILL, 'server_kill')

    async def _power_action(
        self,
        interaction: discord.Interaction,
        server: str,
        action: PowerAction,
        permission: str
    ):
        """Execute a power action on a server."""
        if not await require_permission(interaction, permission):
            return

        await interaction.response.defer(ephemeral=True)

        try:
            client, server_id = await self._get_client_for_server(
                interaction.guild_id, server
            )

            if not client:
                await interaction.followup.send(
                    f"Server `{server}` not found.",
                    ephemeral=True
                )
                return

            response = await client.send_power_action(server_id, action)

            if response.success:
                embed = discord.Embed(
                    title=f"Server {action.value.title()}",
                    description=f"Power action `{action.value}` sent to `{server}`",
                    color=discord.Color.green()
                )
            else:
                embed = discord.Embed(
                    title="Power Action Failed",
                    description=response.message,
                    color=discord.Color.red()
                )

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Error with power action: {e}", exc_info=True)
            await interaction.followup.send(
                f"An error occurred: {e}",
                ephemeral=True
            )

    # ==========================================
    # FILE OPERATIONS
    # ==========================================

    @app_commands.command(name="files", description="List files in a server directory")
    @app_commands.guild_only()
    @app_commands.describe(
        server="Server to browse",
        path="Directory path (default: /)"
    )
    async def list_files(
        self,
        interaction: discord.Interaction,
        server: str,
        path: str = "/"
    ):
        """List files in a server directory."""
        if not await require_permission(interaction, 'server_files'):
            return

        await interaction.response.defer(ephemeral=True)

        try:
            client, server_id = await self._get_client_for_server(
                interaction.guild_id, server
            )

            if not client:
                await interaction.followup.send(
                    f"Server `{server}` not found.",
                    ephemeral=True
                )
                return

            files = await client.list_files(server_id, path)

            if not files:
                await interaction.followup.send(
                    f"No files found in `{path}` or directory does not exist.",
                    ephemeral=True
                )
                return

            embed = discord.Embed(
                title=f"Files in {path}",
                description=f"Server: {server}",
                color=discord.Color.blue()
            )

            # Separate directories and files
            dirs = [f for f in files if not f.is_file]
            regular_files = [f for f in files if f.is_file]

            # Format directory list
            if dirs:
                dir_list = "\n".join([f"📁 {d.name}/" for d in dirs[:10]])
                if len(dirs) > 10:
                    dir_list += f"\n... and {len(dirs) - 10} more"
                embed.add_field(name="Directories", value=dir_list, inline=False)

            # Format file list
            if regular_files:
                file_list = "\n".join([
                    f"📄 {f.name} ({self._format_size(f.size)})"
                    for f in regular_files[:15]
                ])
                if len(regular_files) > 15:
                    file_list += f"\n... and {len(regular_files) - 15} more"
                embed.add_field(name="Files", value=file_list, inline=False)

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Error listing files: {e}", exc_info=True)
            await interaction.followup.send(
                f"An error occurred: {e}",
                ephemeral=True
            )

    @app_commands.command(name="readfile", description="Read contents of a file")
    @app_commands.guild_only()
    @app_commands.describe(
        server="Server to read from",
        path="File path to read"
    )
    async def read_file(
        self,
        interaction: discord.Interaction,
        server: str,
        path: str
    ):
        """Read file contents."""
        if not await require_permission(interaction, 'server_readfile'):
            return

        await interaction.response.defer(ephemeral=True)

        try:
            client, server_id = await self._get_client_for_server(
                interaction.guild_id, server
            )

            if not client:
                await interaction.followup.send(
                    f"Server `{server}` not found.",
                    ephemeral=True
                )
                return

            content = await client.read_file(server_id, path)

            if content is None:
                await interaction.followup.send(
                    f"Failed to read file `{path}`. File may not exist.",
                    ephemeral=True
                )
                return

            # Truncate if too long
            if len(content) > 1900:
                content = content[:1900] + "\n... (truncated)"

            embed = discord.Embed(
                title=f"File: {path.split('/')[-1]}",
                description=f"```\n{content}\n```",
                color=discord.Color.blue()
            )
            embed.set_footer(text=f"Server: {server}")

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Error reading file: {e}", exc_info=True)
            await interaction.followup.send(
                f"An error occurred: {e}",
                ephemeral=True
            )

    @app_commands.command(name="editfile", description="Edit a file on the server")
    @app_commands.guild_only()
    @app_commands.describe(
        server="Server to edit file on",
        path="File path to edit"
    )
    async def edit_file(
        self,
        interaction: discord.Interaction,
        server: str,
        path: str
    ):
        """Edit a file - opens a modal with current content."""
        if not await require_permission(interaction, 'server_editfile'):
            return

        try:
            client, server_id = await self._get_client_for_server(
                interaction.guild_id, server
            )

            if not client:
                await interaction.response.send_message(
                    f"Server `{server}` not found.",
                    ephemeral=True
                )
                return

            # Get current content
            content = await client.read_file(server_id, path)

            if content is None:
                content = ""  # New file

            # Truncate for modal (max 4000 chars)
            if len(content) > 4000:
                await interaction.response.send_message(
                    f"File is too large to edit in Discord ({len(content)} chars). "
                    "Max is 4000 characters. Use `/server download` instead.",
                    ephemeral=True
                )
                return

            # Show edit modal
            modal = FileEditModal(
                client=client,
                server_id=server_id,
                server_name=server,
                file_path=path,
                current_content=content
            )
            await interaction.response.send_modal(modal)

        except Exception as e:
            logger.error(f"Error preparing file edit: {e}", exc_info=True)
            await interaction.response.send_message(
                f"An error occurred: {e}",
                ephemeral=True
            )

    @app_commands.command(name="download", description="Get download link for a file")
    @app_commands.guild_only()
    @app_commands.describe(
        server="Server to download from",
        path="File path to download"
    )
    async def download_file(
        self,
        interaction: discord.Interaction,
        server: str,
        path: str
    ):
        """Get a download URL for a file."""
        if not await require_permission(interaction, 'server_download'):
            return

        await interaction.response.defer(ephemeral=True)

        try:
            client, server_id = await self._get_client_for_server(
                interaction.guild_id, server
            )

            if not client:
                await interaction.followup.send(
                    f"Server `{server}` not found.",
                    ephemeral=True
                )
                return

            url = await client.get_download_url(server_id, path)

            if not url:
                await interaction.followup.send(
                    f"Failed to get download link for `{path}`.",
                    ephemeral=True
                )
                return

            embed = discord.Embed(
                title="Download Ready",
                description=f"Click below to download `{path.split('/')[-1]}`",
                color=discord.Color.green()
            )
            embed.add_field(name="Server", value=server, inline=True)
            embed.add_field(name="File", value=f"`{path}`", inline=True)

            view = discord.ui.View()
            view.add_item(discord.ui.Button(
                label="Download",
                url=url,
                style=discord.ButtonStyle.link
            ))

            await interaction.followup.send(embed=embed, view=view, ephemeral=True)

        except Exception as e:
            logger.error(f"Error getting download link: {e}", exc_info=True)
            await interaction.followup.send(
                f"An error occurred: {e}",
                ephemeral=True
            )

    # ==========================================
    # CONSOLE
    # ==========================================

    @app_commands.command(name="console", description="Send a command to the server console")
    @app_commands.guild_only()
    @app_commands.describe(
        server="Server to send command to",
        command="Console command to execute"
    )
    async def send_console(
        self,
        interaction: discord.Interaction,
        server: str,
        command: str
    ):
        """Send a console command."""
        if not await require_permission(interaction, 'server_console'):
            return

        await interaction.response.defer(ephemeral=True)

        try:
            client, server_id = await self._get_client_for_server(
                interaction.guild_id, server
            )

            if not client:
                await interaction.followup.send(
                    f"Server `{server}` not found.",
                    ephemeral=True
                )
                return

            response = await client.send_command(server_id, command)

            if response.success:
                embed = discord.Embed(
                    title="Command Sent",
                    description=f"```{command}```",
                    color=discord.Color.green()
                )
                embed.set_footer(text=f"Server: {server}")
            else:
                embed = discord.Embed(
                    title="Command Failed",
                    description=response.message,
                    color=discord.Color.red()
                )

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Error sending console command: {e}", exc_info=True)
            await interaction.followup.send(
                f"An error occurred: {e}",
                ephemeral=True
            )

    @app_commands.command(name="help", description="Show all available Pterodactyl server commands")
    @app_commands.guild_only()
    async def server_help(self, interaction: discord.Interaction):
        """Display detailed Pterodactyl command help."""
        from config.commands import COMMAND_DESCRIPTIONS
        from services.permissions import get_user_allowed_commands

        # Get commands this user can access
        allowed = get_user_allowed_commands(interaction.guild_id, interaction.user)

        # Filter server commands
        server_commands = [
            'server_setup', 'server_connections', 'server_list', 'server_info',
            'server_start', 'server_stop', 'server_restart', 'server_kill',
            'server_files', 'server_readfile', 'server_editfile', 'server_download',
            'server_console'
        ]

        visible = [cmd for cmd in server_commands if cmd in allowed]

        if not visible:
            await interaction.response.send_message(
                "You don't have access to any Pterodactyl server commands.\n\n"
                "Contact a server administrator to request permissions.",
                ephemeral=True
            )
            return

        embed = discord.Embed(
            title="Pterodactyl Server Commands (Premium)",
            description="Game server management via Pterodactyl panel",
            color=discord.Color.blue()
        )

        # Group commands by category
        categories = {
            "Setup & Configuration": [
                'server_setup', 'server_connections', 'server_list'
            ],
            "Server Information": [
                'server_info'
            ],
            "Power Control": [
                'server_start', 'server_stop', 'server_restart', 'server_kill'
            ],
            "File Operations": [
                'server_files', 'server_readfile', 'server_editfile', 'server_download'
            ],
            "Console Access": [
                'server_console'
            ]
        }

        for category_name, category_commands in categories.items():
            visible_in_category = [cmd for cmd in category_commands if cmd in visible]
            if visible_in_category:
                cmd_lines = []
                for cmd in visible_in_category:
                    # Remove 'server_' prefix for display
                    display_name = cmd.replace('server_', '')
                    desc = COMMAND_DESCRIPTIONS.get(cmd, '')
                    cmd_lines.append(f"`/server {display_name}` - {desc}")

                embed.add_field(
                    name=category_name,
                    value="\n".join(cmd_lines),
                    inline=False
                )

        embed.add_field(
            name="Features",
            value="• Power management (start/stop/restart/kill)\n"
                  "• Resource monitoring (CPU, RAM, disk)\n"
                  "• File browsing and editing\n"
                  "• Console command execution",
            inline=False
        )

        embed.set_footer(text=f"You have access to {len(visible)} server commands")

        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ==========================================
    # AUTOCOMPLETE
    # ==========================================

    @server_info.autocomplete('server')
    @start_server.autocomplete('server')
    @stop_server.autocomplete('server')
    @restart_server.autocomplete('server')
    @kill_server.autocomplete('server')
    @list_files.autocomplete('server')
    @read_file.autocomplete('server')
    @edit_file.autocomplete('server')
    @download_file.autocomplete('server')
    @send_console.autocomplete('server')
    async def server_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str
    ) -> list[app_commands.Choice[str]]:
        """Autocomplete for server names."""
        try:
            servers = PterodactylQueries.get_pterodactyl_servers(interaction.guild_id)
            return [
                app_commands.Choice(
                    name=f"{s['server_name']} {'(Default)' if s.get('is_default') else ''}".strip(),
                    value=s['server_name']
                )
                for s in servers
                if current.lower() in s['server_name'].lower()
            ][:25]
        except Exception:
            return []

    # ==========================================
    # HELPER METHODS
    # ==========================================

    async def _get_client_for_server(
        self,
        guild_id: int,
        server_name: str
    ) -> tuple[Optional[PterodactylClient], Optional[str]]:
        """Get Pterodactyl client and server ID for a server name."""
        servers = PterodactylQueries.get_pterodactyl_servers(guild_id)
        server = next((s for s in servers if s['server_name'] == server_name), None)

        if not server:
            return None, None

        connection = PterodactylQueries.get_connection(
            server['connection_id'], guild_id
        )

        if not connection:
            return None, None

        client = pterodactyl_manager.get_client(
            connection['id'],
            connection['panel_url'],
            connection['api_key']
        )

        return client, server['server_id']

    def _status_color(self, status: ServerStatus) -> discord.Color:
        """Get color for server status."""
        colors = {
            ServerStatus.RUNNING: discord.Color.green(),
            ServerStatus.STARTING: discord.Color.yellow(),
            ServerStatus.STOPPING: discord.Color.orange(),
            ServerStatus.OFFLINE: discord.Color.red(),
            ServerStatus.UNKNOWN: discord.Color.greyple(),
        }
        return colors.get(status, discord.Color.greyple())

    def _format_size(self, size_bytes: int) -> str:
        """Format file size for display."""
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        elif size_bytes < 1024 * 1024 * 1024:
            return f"{size_bytes / (1024 * 1024):.1f} MB"
        else:
            return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"


class FileEditModal(discord.ui.Modal, title="Edit File"):
    """Modal for editing file contents."""

    content = discord.ui.TextInput(
        label="File Content",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=4000
    )

    def __init__(
        self,
        client: PterodactylClient,
        server_id: str,
        server_name: str,
        file_path: str,
        current_content: str
    ):
        super().__init__()
        self.client = client
        self.server_id = server_id
        self.server_name = server_name
        self.file_path = file_path
        self.content.default = current_content
        self.content.placeholder = "Enter file contents..."

    async def on_submit(self, interaction: discord.Interaction):
        try:
            response = await self.client.write_file(
                self.server_id,
                self.file_path,
                self.content.value
            )

            if response.success:
                await interaction.response.send_message(
                    f"File `{self.file_path}` saved successfully on {self.server_name}.",
                    ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    f"Failed to save file: {response.message}",
                    ephemeral=True
                )

        except Exception as e:
            logger.error(f"Error saving file: {e}", exc_info=True)
            await interaction.response.send_message(
                f"An error occurred while saving: {e}",
                ephemeral=True
            )


async def setup(bot: commands.Bot):
    """Load the ServerControlCommands cog."""
    await bot.add_cog(ServerControlCommands(bot))
