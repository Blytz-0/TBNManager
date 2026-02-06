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
from services.permissions import require_permission, get_user_allowed_commands
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


class PterodactylCommandSelect(discord.ui.Select):
    """Dropdown menu for selecting Pterodactyl commands."""

    def __init__(self, category: str, cog, user_permissions: set, panel_message=None):
        self.cog = cog
        self.category = category
        self.user_permissions = user_permissions
        self.panel_message = panel_message

        # Map option values to their permission names
        permission_map = {
            "setup": "inpanel_ptero_setup",
            "connections": "inpanel_ptero_connections",
            "list": "inpanel_ptero_list",
            "refresh": "inpanel_ptero_refresh",
            "info": "inpanel_ptero_info",
            "start": "inpanel_ptero_start",
            "stop": "inpanel_ptero_stop",
            "restart": "inpanel_ptero_restart",
            "kill": "inpanel_ptero_kill",
            "files": "inpanel_ptero_files",
            "readfile": "inpanel_ptero_files",
            "editfile": "inpanel_ptero_files",
            "download": "inpanel_ptero_files",
            "console": "inpanel_ptero_console",
        }

        # Define all possible options based on category
        all_options_map = {
            "setup": [
                discord.SelectOption(label="Configure Connection", value="setup", description="Setup Pterodactyl panel connection", emoji="⚙️"),
                discord.SelectOption(label="List Connections", value="connections", description="Show all connections", emoji="📋"),
                discord.SelectOption(label="List Servers", value="list", description="Show all servers from panel", emoji="🖥️"),
            ],
            "power": [
                discord.SelectOption(label="Server Info", value="info", description="Show server details & resources", emoji="ℹ️"),
                discord.SelectOption(label="Start Server", value="start", description="Start game server", emoji="▶️"),
                discord.SelectOption(label="Stop Server", value="stop", description="Stop server gracefully", emoji="⏹️"),
                discord.SelectOption(label="Restart Server", value="restart", description="Restart game server", emoji="🔄"),
                discord.SelectOption(label="Kill Server", value="kill", description="Force kill server", emoji="⚠️"),
            ],
            "files": [
                discord.SelectOption(label="Browse Files", value="files", description="List files in directory", emoji="📁"),
                discord.SelectOption(label="Read File", value="readfile", description="View file contents", emoji="📄"),
                discord.SelectOption(label="Edit File", value="editfile", description="Modify file on server", emoji="✏️"),
                discord.SelectOption(label="Download File", value="download", description="Get download link", emoji="⬇️"),
            ],
            "console": [
                discord.SelectOption(label="Console Command", value="console", description="Execute console command", emoji="⌨️"),
            ],
        }

        # Filter options based on user permissions
        all_options = all_options_map.get(category, [])
        options = [
            opt for opt in all_options
            if permission_map.get(opt.value, opt.value) in user_permissions
        ]

        # Set placeholder based on category
        placeholders = {
            "setup": "Setup & Configuration",
            "power": "Server Information & Power Control",
            "files": "File Operations",
            "console": "Console Access",
        }

        super().__init__(
            placeholder=placeholders.get(category, "Select a command"),
            options=options,
            row={"setup": 0, "power": 1, "files": 2, "console": 3}.get(category, 0)
        )

    async def callback(self, interaction: discord.Interaction):
        """Handle command selection."""
        command = self.values[0]

        # Route to appropriate command handler
        try:
            if command == "setup":
                await self.cog._menu_setup(interaction)
            elif command == "connections":
                await self.cog._menu_connections(interaction)
            elif command == "list":
                await self.cog._menu_list(interaction)
            elif command == "info":
                await self.cog._menu_info(interaction)
            elif command == "start":
                await self.cog._menu_start(interaction)
            elif command == "stop":
                await self.cog._menu_stop(interaction)
            elif command == "restart":
                await self.cog._menu_restart(interaction)
            elif command == "kill":
                await self.cog._menu_kill(interaction)
            elif command == "files":
                await self.cog._menu_files(interaction)
            elif command == "readfile":
                await self.cog._menu_readfile(interaction)
            elif command == "editfile":
                await self.cog._menu_editfile(interaction)
            elif command == "download":
                await self.cog._menu_download(interaction)
            elif command == "console":
                await self.cog._menu_console(interaction)
            else:
                await interaction.response.send_message(
                    f"❌ Unknown command: {command}",
                    ephemeral=True
                )
        except Exception as e:
            logger.error(f"Error handling menu command {command}: {e}", exc_info=True)
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    f"❌ Error executing command: {e}",
                    ephemeral=True
                )
        finally:
            # Refresh the panel dropdown to allow reselection
            if self.panel_message and self.user_permissions:
                try:
                    # Import the parent cog's refresh method
                    panel_cog = interaction.client.get_cog("PterodactylMenuCommands")
                    if panel_cog:
                        await panel_cog._refresh_panel(self.panel_message, self.user_permissions)
                except Exception as refresh_error:
                    logger.error(f"Error refreshing Pterodactyl panel: {refresh_error}", exc_info=True)


class PterodactylCommandView(discord.ui.View):
    """Main view with all Pterodactyl command dropdowns."""

    def __init__(self, cog, user_permissions: set, panel_message=None):
        super().__init__(timeout=300)
        self.cog = cog
        self.panel_message = panel_message

        # Add category dropdowns only if user has at least one permission in that category
        if self._has_category_access(user_permissions, "setup"):
            self.add_item(PterodactylCommandSelect("setup", cog, user_permissions, panel_message))
        if self._has_category_access(user_permissions, "power"):
            self.add_item(PterodactylCommandSelect("power", cog, user_permissions, panel_message))
        if self._has_category_access(user_permissions, "files"):
            self.add_item(PterodactylCommandSelect("files", cog, user_permissions, panel_message))
        if self._has_category_access(user_permissions, "console"):
            self.add_item(PterodactylCommandSelect("console", cog, user_permissions, panel_message))

    def _has_category_access(self, user_permissions: set, category: str) -> bool:
        """Check if user has access to at least one option in the category."""
        category_permissions = {
            "setup": {"inpanel_ptero_setup", "inpanel_ptero_connections", "inpanel_ptero_list", "inpanel_ptero_refresh"},
            "power": {"inpanel_ptero_info", "inpanel_ptero_start", "inpanel_ptero_stop", "inpanel_ptero_restart", "inpanel_ptero_kill"},
            "files": {"inpanel_ptero_files"},
            "console": {"inpanel_ptero_console"},
        }
        required = category_permissions.get(category, set())
        return bool(required.intersection(user_permissions))


class PterodactylMenuCommands(commands.GroupCog, name="pterodactyl"):
    """Pterodactyl menu command."""

    def __init__(self, bot: commands.Bot, server_cog):
        self.bot = bot
        self.server_cog = server_cog
        super().__init__()

    @app_commands.command(name="panel", description="Open Pterodactyl control panel with categorized options")
    @app_commands.guild_only()
    async def pterodactyl_panel(self, interaction: discord.Interaction):
        """Show the Pterodactyl control panel with dropdown selections."""
        # Check if user has permission to access the panel
        if not await require_permission(interaction, 'pterodactyl_panel'):
            return

        # Get user's allowed commands
        user_permissions = get_user_allowed_commands(interaction.guild_id, interaction.user)

        # Create temporary view to check if user has any panel options
        temp_view = PterodactylCommandView(self.server_cog, user_permissions)

        # Check if user has any panel options available
        if len(temp_view.children) == 0:
            await interaction.response.send_message(
                "❌ You have access to the Pterodactyl panel, but no features are enabled for your role.\n"
                "Contact a server administrator to configure your permissions.",
                ephemeral=True
            )
            return

        # Build dynamic description based on available categories
        desc_parts = ["Select a command from the dropdowns below:\n"]
        if any(isinstance(child, PterodactylCommandSelect) and child.category == "setup" for child in temp_view.children):
            desc_parts.append("**⚙️ Setup & Configuration** - Configure panel connections")
        if any(isinstance(child, PterodactylCommandSelect) and child.category == "power" for child in temp_view.children):
            desc_parts.append("**🎮 Server Information & Power Control** - View info, start, stop, restart, kill")
        if any(isinstance(child, PterodactylCommandSelect) and child.category == "files" for child in temp_view.children):
            desc_parts.append("**📁 File Operations** - Browse, read, edit, download files")
        if any(isinstance(child, PterodactylCommandSelect) and child.category == "console" for child in temp_view.children):
            desc_parts.append("**💻 Console Access** - Execute console commands")

        embed = discord.Embed(
            title="<:pterodactyl:1467662805137363166> Pterodactyl Control Panel",
            description="\n".join(desc_parts),
            color=discord.Color.blue()
        )

        embed.set_footer(text="This panel will remain active for 5 minutes")

        # Send initial message without view
        await interaction.response.send_message(embed=embed, ephemeral=True)

        # Get the message object and create view with message reference for refresh capability
        panel_message = await interaction.original_response()
        view = PterodactylCommandView(self.server_cog, user_permissions, panel_message)

        # Edit message to add the view
        await panel_message.edit(view=view)

    async def _refresh_panel(self, panel_message, user_permissions: set):
        """Refresh the panel dropdown by recreating the view."""
        try:
            # Create view to determine available categories
            temp_view = PterodactylCommandView(self.server_cog, user_permissions)

            # Build dynamic description based on available categories
            desc_parts = ["Select a command from the dropdowns below:\n"]
            if any(isinstance(child, PterodactylCommandSelect) and child.category == "setup" for child in temp_view.children):
                desc_parts.append("**⚙️ Setup & Configuration** - Configure panel connections")
            if any(isinstance(child, PterodactylCommandSelect) and child.category == "power" for child in temp_view.children):
                desc_parts.append("**🎮 Server Information & Power Control** - View info, start, stop, restart, kill")
            if any(isinstance(child, PterodactylCommandSelect) and child.category == "files" for child in temp_view.children):
                desc_parts.append("**📁 File Operations** - Browse, read, edit, download files")
            if any(isinstance(child, PterodactylCommandSelect) and child.category == "console" for child in temp_view.children):
                desc_parts.append("**💻 Console Access** - Execute console commands")

            embed = discord.Embed(
                title="<:pterodactyl:1467662805137363166> Pterodactyl Control Panel",
                description="\n".join(desc_parts),
                color=discord.Color.blue()
            )

            embed.set_footer(text="This panel will remain active for 5 minutes")

            # Create fresh view with reset dropdowns
            view = PterodactylCommandView(self.server_cog, user_permissions, panel_message)

            # Edit the panel message to refresh the dropdowns
            await panel_message.edit(embed=embed, view=view)
        except Exception as e:
            logger.error(f"Error refreshing Pterodactyl panel: {e}", exc_info=True)

    @app_commands.command(name="help", description="Show Pterodactyl server management help")
    @app_commands.guild_only()
    async def pterodactyl_help(self, interaction: discord.Interaction):
        """Display detailed Pterodactyl help with menu introduction."""
        from config.commands import COMMAND_DESCRIPTIONS
        from services.permissions import get_user_allowed_commands

        # Get commands this user can access
        allowed = get_user_allowed_commands(interaction.guild_id, interaction.user)

        # Check for panel access
        has_panel_access = 'pterodactyl_panel' in allowed

        # Filter server commands
        server_commands = [
            'server_setup', 'server_connections', 'server_refresh', 'server_list', 'server_info',
            'server_start', 'server_stop', 'server_restart', 'server_kill',
            'server_files', 'server_readfile', 'server_editfile', 'server_download',
            'server_console'
        ]

        visible = [cmd for cmd in server_commands if cmd in allowed]

        if not visible and not has_panel_access:
            await interaction.response.send_message(
                "You don't have access to any Pterodactyl server commands.\n\n"
                "Contact a server administrator to request permissions.",
                ephemeral=True
            )
            return

        embed = discord.Embed(
            title="<:pterodactyl:1467662805137363166> Pterodactyl Server Management",
            description="Game server control via Pterodactyl panel",
            color=discord.Color.blue()
        )

        # Primary recommendation: Use the panel
        if has_panel_access:
            embed.add_field(
                name="🎮 Interactive Panel (Recommended)",
                value="**Use `/pterodactyl panel` for easy access to all features:**\n"
                      "• Setup & manage panel connections\n"
                      "• Server power control (start, stop, restart, kill)\n"
                      "• Browse and edit server files\n"
                      "• Send console commands\n"
                      "• View server resources\n\n"
                      "*The panel provides an organized, user-friendly interface with dropdown selections.*",
                inline=False
            )

        # Show individual commands if available
        if visible:
            # Group commands by category
            categories = {
                "Setup & Configuration": [
                    'server_setup', 'server_connections', 'server_refresh', 'server_list'
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

            embed.add_field(
                name="📋 Individual Commands",
                value="*You can also use individual slash commands:*",
                inline=False
            )

            for category_name, category_commands in categories.items():
                visible_in_category = [cmd for cmd in category_commands if cmd in visible]
                if visible_in_category:
                    cmd_lines = []
                    for cmd in visible_in_category:
                        # Remove 'server_' prefix for display
                        display_name = cmd.replace('server_', '')
                        desc = COMMAND_DESCRIPTIONS.get(cmd, '')
                        # Remove [Premium] prefix from description for cleaner display
                        desc = desc.replace('[Premium] ', '')
                        cmd_lines.append(f"`/server {display_name}` - {desc}")

                    embed.add_field(
                        name=f"　├ {category_name}",
                        value="\n".join(cmd_lines),
                        inline=False
                    )

        total_msg = []
        if has_panel_access:
            total_msg.append("Panel access: ✅")
        if visible:
            total_msg.append(f"{len(visible)} individual commands")

        embed.set_footer(text=" | ".join(total_msg))

        await interaction.response.send_message(embed=embed, ephemeral=True)


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

    @app_commands.command(name="refresh", description="Re-discover servers from Pterodactyl panel")
    @app_commands.guild_only()
    async def refresh_servers(self, interaction: discord.Interaction):
        """Re-discover servers from existing Pterodactyl connections."""
        if not await require_permission(interaction, 'server_setup'):
            return

        await interaction.response.defer(ephemeral=True)

        try:
            connections = PterodactylQueries.get_connections(interaction.guild_id)

            if not connections:
                await interaction.followup.send(
                    "No Pterodactyl connections configured. Use `/server setup` to add one.",
                    ephemeral=True
                )
                return

            total_discovered = 0
            connection_results = []

            for conn in connections:
                try:
                    # Use stored API key to reconnect
                    client = PterodactylClient(conn['panel_url'], conn['api_key'])

                    # Test connection
                    test_result = await client.test_connection()
                    if not test_result.success:
                        connection_results.append(
                            f"❌ **{conn['connection_name']}**: {test_result.message}"
                        )
                        continue

                    # Discover servers
                    servers = await client.list_servers()

                    # Clear old servers for this connection
                    PterodactylQueries.clear_discovered_servers(conn['id'])

                    # Save newly discovered servers
                    for server in servers:
                        PterodactylQueries.add_discovered_server(
                            connection_id=conn['id'],
                            guild_id=interaction.guild_id,
                            server_id=server.server_id,
                            server_name=server.name,
                            server_uuid=server.uuid
                        )

                    total_discovered += len(servers)
                    connection_results.append(
                        f"✅ **{conn['connection_name']}**: Found {len(servers)} server(s)"
                    )

                except Exception as e:
                    logger.error(f"Error refreshing connection {conn['connection_name']}: {e}", exc_info=True)
                    connection_results.append(
                        f"❌ **{conn['connection_name']}**: {str(e)}"
                    )

            # Build response embed
            embed = discord.Embed(
                title="🔄 Server Discovery Complete",
                description=f"Discovered **{total_discovered}** total server(s)",
                color=discord.Color.green() if total_discovered > 0 else discord.Color.orange()
            )

            embed.add_field(
                name="Connection Results",
                value="\n".join(connection_results),
                inline=False
            )

            if total_discovered == 0:
                embed.add_field(
                    name="⚠️ No Servers Found",
                    value="Make sure:\n"
                          "• Your API key has access to servers\n"
                          "• Servers are assigned to your account in the panel\n"
                          "• The API key is a **Client API Key** (ptlc_), not Application key",
                    inline=False
                )

            embed.set_footer(text="Use /server list to view all discovered servers")

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Error refreshing servers: {e}", exc_info=True)
            await interaction.followup.send(
                f"❌ **Error**\n\nAn unexpected error occurred: {str(e)}",
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

            # Build embed using helper method
            embed, inferred_status = self._build_server_info_embed(info, resources)

            # Create control buttons view
            view = ServerControlView(self, interaction.guild_id, server, info.server_id, inferred_status)

            await interaction.followup.send(embed=embed, view=view, ephemeral=True)

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

            # Check if path looks like a file (has extension)
            path_parts = path.rstrip('/').split('/')
            if path_parts:
                last_part = path_parts[-1]
                # If it has a file extension, it's probably a file not a directory
                if '.' in last_part and not last_part.startswith('.'):
                    await interaction.followup.send(
                        f"The path `{path}` appears to be a file, not a directory.\n"
                        f"Use `/server readfile` to view file contents instead.",
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

            # Save original full content for editing
            original_content = content

            # Handle log files differently - show only last N lines
            filename = path.split('/')[-1].lower()
            is_log_file = filename.endswith('.log')
            is_ini_file = filename.endswith('.ini')

            footer_text = f"Server: {server}"

            if is_log_file:
                lines = content.splitlines()
                total_lines = len(lines)

                # Show last N lines for log files, but ensure we stay under character limit
                max_log_lines = 50

                # Start with last 50 lines
                selected_lines = lines[-max_log_lines:] if total_lines > max_log_lines else lines
                content = '\n'.join(selected_lines)

                # If still too long, reduce line count from the beginning to keep most recent lines
                while len(content) > 1800 and len(selected_lines) > 10:
                    selected_lines = selected_lines[1:]  # Remove oldest line
                    content = '\n'.join(selected_lines)

                lines_shown = len(selected_lines)
                if total_lines > lines_shown:
                    footer_text += f" | Showing last {lines_shown} of {total_lines} lines"
            else:
                # Truncate non-log files if too long (for Discord embed limit)
                if len(content) > 1900:
                    content = content[:1900] + "\n... (truncated)"

            embed = discord.Embed(
                title=f"File: {path.split('/')[-1]}",
                description=f"```\n{content}\n```",
                color=discord.Color.blue()
            )
            embed.set_footer(text=footer_text)

            # Add edit button for .ini files (if not too large)
            if is_ini_file and len(original_content) <= 4000:
                view = FileReadView(
                    cog=self,
                    guild_id=interaction.guild_id,
                    server=server,
                    file_path=path,
                    content=original_content  # Use full content, not truncated
                )
                await interaction.followup.send(embed=embed, view=view, ephemeral=True)
            else:
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

            # Discord buttons have a 512 character URL limit
            # If URL is too long, show it in embed description instead
            if len(url) > 512:
                embed = discord.Embed(
                    title="Download Ready",
                    description=f"**Download link for `{path.split('/')[-1]}`:**\n\n{url}",
                    color=discord.Color.green()
                )
                embed.add_field(name="Server", value=server, inline=True)
                embed.add_field(name="File", value=f"`{path}`", inline=True)
                embed.set_footer(text="Copy and paste the link above into your browser")
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
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

        # Update connection status on successful client creation
        if client:
            try:
                # Test the connection by getting server list
                await client.list_servers()
                PterodactylQueries.update_connection_status(connection['id'], success=True)
            except Exception as e:
                PterodactylQueries.update_connection_status(connection['id'], success=False, error=str(e))

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

    def _format_uptime(self, uptime_seconds: int) -> str:
        """Format uptime for display."""
        if uptime_seconds == 0:
            return "0 seconds"

        days = uptime_seconds // 86400
        hours = (uptime_seconds % 86400) // 3600
        minutes = (uptime_seconds % 3600) // 60

        parts = []
        if days > 0:
            parts.append(f"{days} day{'s' if days != 1 else ''}")
        if hours > 0:
            parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
        if minutes > 0:
            parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")

        if not parts:
            return f"{uptime_seconds} second{'s' if uptime_seconds != 1 else ''}"

        return ", ".join(parts)

    def _build_server_info_embed(self, info, resources):
        """Build server info embed and return (embed, inferred_status) tuple."""
        # Infer actual status from resources
        inferred_status = "Unknown"
        if resources:
            # Server is running if it has uptime and active CPU/memory
            if resources.uptime_seconds > 0 and (resources.cpu_percent > 0 or resources.memory_bytes > 0):
                inferred_status = "Running"
            else:
                inferred_status = "Stopped"

        embed = discord.Embed(
            title=f"Server: {info.name}",
            color=discord.Color.green() if inferred_status == "Running" else discord.Color.red()
        )

        # Status (inferred from resources)
        embed.add_field(name="Status", value=inferred_status, inline=True)

        # Address (IP:Port)
        address = f"{info.ip}:{info.port}"
        embed.add_field(name="Address", value=address, inline=True)

        # RCON Port (if available)
        if info.rcon_port:
            embed.add_field(name="RCON Port", value=str(info.rcon_port), inline=True)

        # Game Type (if detected)
        if info.game_type:
            embed.add_field(name="Game", value=info.game_type, inline=True)

        embed.add_field(name="Server ID", value=f"`{info.server_id}`", inline=True)

        if info.description:
            embed.add_field(name="Description", value=info.description, inline=False)

        if resources:
            # Format CPU with limit
            cpu_current = resources.cpu_percent
            cpu_limit = resources.cpu_limit
            cpu_display = f"{cpu_current:.1f}%/{cpu_limit}%"

            # Format memory
            mem_used = resources.memory_bytes / (1024 * 1024)
            mem_limit = resources.memory_limit_bytes / (1024 * 1024)
            mem_pct = (mem_used / mem_limit * 100) if mem_limit > 0 else 0

            # Format disk
            disk_used = resources.disk_bytes / (1024 * 1024 * 1024)
            disk_limit = resources.disk_limit_bytes / (1024 * 1024 * 1024)

            # Format uptime
            uptime_str = self._format_uptime(resources.uptime_seconds)

            embed.add_field(
                name="CPU",
                value=cpu_display,
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
                value=uptime_str,
                inline=True
            )

        return embed, inferred_status

    # Helper methods for menu dropdown callbacks
    async def _menu_setup(self, interaction: discord.Interaction):
        """Handle setup command from menu."""
        # Call the existing setup command
        modal = PterodactylSetupModal(self.bot)
        await interaction.response.send_modal(modal)

    async def _menu_connections(self, interaction: discord.Interaction):
        """Handle connections command from menu."""
        if not await require_permission(interaction, 'server_setup'):
            return

        try:
            connections = PterodactylQueries.get_connections(interaction.guild_id)

            if not connections:
                await interaction.response.send_message(
                    "No Pterodactyl connections configured. Use **Setup & Configuration → Setup** to add one.",
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

    async def _menu_list(self, interaction: discord.Interaction):
        """Handle list command from menu."""
        if not await require_permission(interaction, 'server_info'):
            return

        await interaction.response.defer(ephemeral=True)

        try:
            servers = PterodactylQueries.get_pterodactyl_servers(interaction.guild_id)

            if not servers:
                await interaction.followup.send(
                    "No servers found. Configure a Pterodactyl connection with **Setup & Configuration → Setup**.",
                    ephemeral=True
                )
                return

            embed = discord.Embed(
                title="Game Servers",
                description=f"Found {len(servers)} server(s)",
                color=discord.Color.blue()
            )

            # Fetch actual status for each server
            for server in servers[:10]:
                default = " (Default)" if server.get('is_default') else ""

                # Get actual status from Pterodactyl API
                try:
                    client, server_id = await self._get_client_for_server(
                        interaction.guild_id, server['server_name']
                    )

                    if client:
                        resources = await client.get_server_resources(server_id)
                        if resources:
                            # Infer status from resources
                            if resources.uptime_seconds > 0 and (resources.cpu_percent > 0 or resources.memory_bytes > 0):
                                status = "🟢 Running"
                            else:
                                status = "🔴 Stopped"
                        else:
                            status = "⚪ Unknown"
                    else:
                        status = "⚪ Unknown"
                except Exception:
                    status = "⚪ Unknown"

                embed.add_field(
                    name=f"{server['server_name']}{default}",
                    value=f"**ID:** `{server['server_id']}`\n**Status:** {status}",
                    inline=True
                )

            if len(servers) > 10:
                embed.set_footer(text=f"Showing 10 of {len(servers)} servers")

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Error listing servers: {e}", exc_info=True)
            await interaction.followup.send(
                "An error occurred while listing servers.",
                ephemeral=True
            )

    async def _menu_info(self, interaction: discord.Interaction):
        """Handle info command from menu."""
        if not await require_permission(interaction, 'server_info'):
            return

        servers = PterodactylQueries.get_pterodactyl_servers(interaction.guild_id)

        if not servers:
            await interaction.response.send_message(
                "❌ No servers found. Use `/server setup` to configure a Pterodactyl connection first.",
                ephemeral=True
            )
            return

        # Create server selection dropdown
        options = [
            discord.SelectOption(label=s['server_name'], value=s['server_name'])
            for s in servers[:25]  # Max 25 options
        ]

        cog_ref = self

        class ServerSelect(discord.ui.Select):
            def __init__(self):
                super().__init__(placeholder="Select server to view info", options=options)

            async def callback(self, select_interaction: discord.Interaction):
                server_name = self.values[0]
                await select_interaction.response.defer(ephemeral=True)

                try:
                    client, server_id = await cog_ref._get_client_for_server(
                        select_interaction.guild_id, server_name
                    )

                    if not client:
                        await select_interaction.followup.send(
                            f"Server `{server_name}` not found.",
                            ephemeral=True
                        )
                        return

                    # Get server info and resources
                    info = await client.get_server_info(server_id)
                    resources = await client.get_server_resources(server_id)

                    if not info:
                        await select_interaction.followup.send(
                            "Failed to get server information.",
                            ephemeral=True
                        )
                        return

                    # Build embed using helper method
                    embed, inferred_status = cog_ref._build_server_info_embed(info, resources)

                    # Create control buttons view
                    view = ServerControlView(cog_ref, select_interaction.guild_id, server_name, info.server_id, inferred_status)

                    await select_interaction.followup.send(embed=embed, view=view, ephemeral=True)

                except Exception as e:
                    logger.error(f"Error getting server info: {e}", exc_info=True)
                    await select_interaction.followup.send(
                        f"An error occurred: {e}",
                        ephemeral=True
                    )

        view = discord.ui.View(timeout=60)
        view.add_item(ServerSelect())

        embed = discord.Embed(
            title="Server Information",
            description="Select a server to view details:",
            color=discord.Color.blue()
        )

        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    async def _menu_start(self, interaction: discord.Interaction):
        """Handle start command from menu."""
        await self._menu_power_action(interaction, "start", "Start Server")

    async def _menu_stop(self, interaction: discord.Interaction):
        """Handle stop command from menu."""
        await self._menu_power_action(interaction, "stop", "Stop Server")

    async def _menu_restart(self, interaction: discord.Interaction):
        """Handle restart command from menu."""
        await self._menu_power_action(interaction, "restart", "Restart Server")

    async def _menu_kill(self, interaction: discord.Interaction):
        """Handle kill command from menu."""
        await self._menu_power_action(interaction, "kill", "Force Kill Server")

    async def _menu_power_action(self, interaction: discord.Interaction, action: str, title: str):
        """Generic handler for power actions."""
        if not await require_permission(interaction, f'server_{action}'):
            return

        servers = PterodactylQueries.get_pterodactyl_servers(interaction.guild_id)

        if not servers:
            await interaction.response.send_message(
                "❌ No servers found. Use `/server setup` to configure a Pterodactyl connection first.",
                ephemeral=True
            )
            return

        # Create server selection dropdown
        options = [
            discord.SelectOption(label=s['server_name'], value=s['server_name'])
            for s in servers[:25]  # Max 25 options
        ]

        cog_ref = self

        class ServerSelect(discord.ui.Select):
            def __init__(self):
                super().__init__(placeholder=f"Select server to {action}", options=options)

            async def callback(self, select_interaction: discord.Interaction):
                server_name = self.values[0]
                # Call the appropriate power command via _power_action
                if action == "start":
                    await cog_ref._power_action(select_interaction, server_name, PowerAction.START, 'server_start')
                elif action == "stop":
                    await cog_ref._power_action(select_interaction, server_name, PowerAction.STOP, 'server_stop')
                elif action == "restart":
                    await cog_ref._power_action(select_interaction, server_name, PowerAction.RESTART, 'server_restart')
                elif action == "kill":
                    await cog_ref._power_action(select_interaction, server_name, PowerAction.KILL, 'server_kill')

        view = discord.ui.View(timeout=60)
        view.add_item(ServerSelect())

        embed = discord.Embed(
            title=title,
            description="Select a server:",
            color=discord.Color.orange()
        )

        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    async def _menu_files(self, interaction: discord.Interaction):
        """Handle files command from menu."""
        if not await require_permission(interaction, 'server_files'):
            return

        servers = PterodactylQueries.get_pterodactyl_servers(interaction.guild_id)

        if not servers:
            await interaction.response.send_message(
                "❌ No servers found. Use `/server setup` to configure a Pterodactyl connection first.",
                ephemeral=True
            )
            return

        # Create server selection dropdown
        options = [
            discord.SelectOption(label=s['server_name'], value=s['server_name'])
            for s in servers[:25]  # Max 25 options
        ]

        cog_ref = self

        class ServerSelect(discord.ui.Select):
            def __init__(self):
                super().__init__(placeholder="Select server to browse files", options=options)

            async def callback(self, select_interaction: discord.Interaction):
                server_name = self.values[0]

                # Open directory path modal
                class DirectoryModal(discord.ui.Modal, title="Browse Files"):
                    directory = discord.ui.TextInput(
                        label="Directory Path",
                        placeholder="/ for root, or /TheIsle/Saved/Config",
                        required=False,
                        max_length=500
                    )

                    async def on_submit(self, modal_interaction: discord.Interaction):
                        dir_path = self.directory.value.strip() if self.directory.value else "/"
                        await modal_interaction.response.defer(ephemeral=True)

                        try:
                            client, server_id = await cog_ref._get_client_for_server(
                                modal_interaction.guild_id, server_name
                            )

                            if not client:
                                await modal_interaction.followup.send(
                                    f"Server `{server_name}` not found.",
                                    ephemeral=True
                                )
                                return

                            # Check if path looks like a file (has extension)
                            path_parts = dir_path.rstrip('/').split('/')
                            if path_parts:
                                last_part = path_parts[-1]
                                if '.' in last_part and not last_part.startswith('.'):
                                    await modal_interaction.followup.send(
                                        f"The path `{dir_path}` appears to be a file, not a directory.\n"
                                        f"Use **File Operations → Read File** to view file contents instead.",
                                        ephemeral=True
                                    )
                                    return

                            files = await client.list_files(server_id, dir_path)

                            if not files:
                                await modal_interaction.followup.send(
                                    f"No files found in `{dir_path}` or directory does not exist.",
                                    ephemeral=True
                                )
                                return

                            embed = discord.Embed(
                                title=f"📂 Pterodactyl File Browser",
                                description=f"**Server:** {server_name}\n**Path:** `{dir_path}`\n**Items:** {len(files)}",
                                color=discord.Color.blue()
                            )

                            # Separate directories and files
                            dirs = [f for f in files if not f.is_file]
                            regular_files = [f for f in files if f.is_file]

                            # Format directory list
                            if dirs:
                                dir_list = "\n".join([f"📁 {d.name}/" for d in dirs[:10]])
                                if len(dirs) > 10:
                                    dir_list += f"\n...and {len(dirs) - 10} more folders"
                                embed.add_field(name=f"📂 Folders ({len(dirs)})", value=dir_list, inline=False)

                            # Format file list
                            if regular_files:
                                file_list = "\n".join([
                                    f"📄 {f.name} ({cog_ref._format_size(f.size)})"
                                    for f in regular_files[:15]
                                ])
                                if len(regular_files) > 15:
                                    file_list += f"\n...and {len(regular_files) - 15} more files"
                                embed.add_field(name=f"📄 Files ({len(regular_files)})", value=file_list, inline=False)

                            # Add navigation section
                            nav_text = []

                            # Calculate parent path for Go Up
                            parent_path = None
                            if dir_path and dir_path != '/' and dir_path != '.':
                                parts = dir_path.rstrip('/').split('/')
                                if len(parts) > 1:
                                    parent_path = '/'.join(parts[:-1]) or '/'
                                else:
                                    parent_path = '/'

                            if parent_path is not None:
                                nav_text.append(f"⬆️ **Go Up:** `{parent_path}`")

                            # Show all folder paths numbered
                            if dirs:
                                nav_text.append(f"\n**📁 All Folder Paths:**")
                                for idx, item in enumerate(dirs[:15], start=1):
                                    new_path = f"{dir_path.rstrip('/')}/{item.name}".replace('//', '/')
                                    nav_text.append(f"[{idx}] `{new_path}`")

                                if len(dirs) > 15:
                                    nav_text.append(f"...and {len(dirs) - 15} more folders")

                            # Add quick shortcuts
                            nav_text.append(f"\n**🔗 Quick Shortcuts:**")
                            nav_text.append(f"• `logs` → TheIsle/Saved/Logs")
                            nav_text.append(f"• `saved` → TheIsle/Saved")
                            nav_text.append(f"• `root` → /")

                            embed.add_field(
                                name="🧭 Navigation",
                                value="\n".join(nav_text),
                                inline=False
                            )

                            # Create navigation view with buttons
                            nav_view = discord.ui.View(timeout=300)

                            # Helper to rebrowse a path
                            async def rebrowse_path(btn_interaction: discord.Interaction, target_path: str):
                                # Security check: only users with correct permissions can interact
                                user_permissions = get_user_allowed_commands(btn_interaction.guild_id, btn_interaction.user)
                                if "inpanel_ptero_files" not in user_permissions:
                                    await btn_interaction.response.send_message(
                                        "❌ You don't have permission to interact with this browse session.",
                                        ephemeral=True
                                    )
                                    return

                                await btn_interaction.response.defer()

                                try:
                                    # Delete the previous message to prevent scroll doom
                                    try:
                                        await btn_interaction.message.delete()
                                    except Exception as e:
                                        logger.error(f"Failed to delete message: {e}")

                                    new_files = await client.list_files(server_id, target_path)

                                    if not new_files:
                                        await btn_interaction.followup.send(
                                            f"❌ No files found in `{target_path}`",
                                            ephemeral=True
                                        )
                                        return

                                    new_embed = discord.Embed(
                                        title=f"📂 Pterodactyl File Browser",
                                        description=f"**Server:** {server_name}\n**Path:** `{target_path}`\n**Items:** {len(new_files)}",
                                        color=discord.Color.blue()
                                    )

                                    new_dirs = [f for f in new_files if not f.is_file]
                                    new_regular_files = [f for f in new_files if f.is_file]

                                    if new_dirs:
                                        new_dir_list = "\n".join([f"📁 {d.name}/" for d in new_dirs[:10]])
                                        if len(new_dirs) > 10:
                                            new_dir_list += f"\n...and {len(new_dirs) - 10} more folders"
                                        new_embed.add_field(name=f"📂 Folders ({len(new_dirs)})", value=new_dir_list, inline=False)

                                    if new_regular_files:
                                        new_file_list = "\n".join([
                                            f"📄 {f.name} ({cog_ref._format_size(f.size)})"
                                            for f in new_regular_files[:15]
                                        ])
                                        if len(new_regular_files) > 15:
                                            new_file_list += f"\n...and {len(new_regular_files) - 15} more files"
                                        new_embed.add_field(name=f"📄 Files ({len(new_regular_files)})", value=new_file_list, inline=False)

                                    # Add navigation section
                                    new_nav_text = []

                                    # Calculate parent path for Go Up
                                    new_parent_path_nav = None
                                    if target_path and target_path != '/' and target_path != '.':
                                        parts = target_path.rstrip('/').split('/')
                                        if len(parts) > 1:
                                            new_parent_path_nav = '/'.join(parts[:-1]) or '/'
                                        else:
                                            new_parent_path_nav = '/'

                                    if new_parent_path_nav is not None:
                                        new_nav_text.append(f"⬆️ **Go Up:** `{new_parent_path_nav}`")

                                    # Show all folder paths numbered
                                    if new_dirs:
                                        new_nav_text.append(f"\n**📁 All Folder Paths:**")
                                        for idx, item in enumerate(new_dirs[:15], start=1):
                                            path_for_nav = f"{target_path.rstrip('/')}/{item.name}".replace('//', '/')
                                            new_nav_text.append(f"[{idx}] `{path_for_nav}`")

                                        if len(new_dirs) > 15:
                                            new_nav_text.append(f"...and {len(new_dirs) - 15} more folders")

                                    # Add quick shortcuts
                                    new_nav_text.append(f"\n**🔗 Quick Shortcuts:**")
                                    new_nav_text.append(f"• `logs` → TheIsle/Saved/Logs")
                                    new_nav_text.append(f"• `saved` → TheIsle/Saved")
                                    new_nav_text.append(f"• `root` → /")

                                    new_embed.add_field(
                                        name="🧭 Navigation",
                                        value="\n".join(new_nav_text),
                                        inline=False
                                    )

                                    # Create new navigation view
                                    new_nav_view = discord.ui.View(timeout=300)

                                    # Calculate parent path for Go Up button
                                    new_parent_path = None
                                    if target_path and target_path != '/' and target_path != '.':
                                        parts = target_path.rstrip('/').split('/')
                                        if len(parts) > 1:
                                            new_parent_path = '/'.join(parts[:-1]) or '/'
                                        else:
                                            new_parent_path = '/'

                                    # Add Go Up button
                                    if new_parent_path:
                                        class NewGoUpButton(discord.ui.Button):
                                            def __init__(self, p_path):
                                                self.parent = p_path
                                                super().__init__(label="⬆️ Go Up", style=discord.ButtonStyle.secondary, row=0)

                                            async def callback(self, new_btn_interaction: discord.Interaction):
                                                await rebrowse_path(new_btn_interaction, self.parent)

                                        new_nav_view.add_item(NewGoUpButton(new_parent_path))

                                    # Add Close button
                                    class NewCloseButton(discord.ui.Button):
                                        def __init__(self):
                                            super().__init__(label="❌ Close", style=discord.ButtonStyle.danger, row=0)

                                        async def callback(self, close_interaction: discord.Interaction):
                                            # Security check: only users with correct permissions can close
                                            user_permissions = get_user_allowed_commands(close_interaction.guild_id, close_interaction.user)
                                            if "inpanel_ptero_files" not in user_permissions:
                                                await close_interaction.response.send_message(
                                                    "❌ You don't have permission to interact with this browse session.",
                                                    ephemeral=True
                                                )
                                                return

                                            try:
                                                await close_interaction.message.delete()
                                            except:
                                                await close_interaction.response.send_message("❌ Failed to delete message", ephemeral=True)

                                    new_nav_view.add_item(NewCloseButton())

                                    # Add directory buttons (up to 20)
                                    new_dir_count = 0
                                    for idx, item in enumerate(new_dirs[:min(20, len(new_dirs))], start=1):
                                        next_path = f"{target_path.rstrip('/')}/{item.name}"

                                        class NewDirButton(discord.ui.Button):
                                            def __init__(self, num, name, path):
                                                self.target_path = path
                                                # Row 0 is reserved for Go Up and Close buttons, so start from row 1
                                                btn_row = 1 + ((num - 1) // 5)
                                                super().__init__(label=f"[{num}] {name[:12]}", style=discord.ButtonStyle.primary, row=btn_row)

                                            async def callback(self, new_btn_interaction: discord.Interaction):
                                                await rebrowse_path(new_btn_interaction, self.target_path)

                                        new_nav_view.add_item(NewDirButton(idx, item.name, next_path))
                                        new_dir_count += 1

                                    # Add file read buttons for readable files
                                    new_readable_files = [f for f in new_regular_files if f.name.lower().endswith(('.ini', '.conf', '.cfg', '.log', '.txt', '.json', '.yml', '.yaml'))]

                                    # Row 0 is reserved for navigation buttons (Go Up/Close)
                                    # Directory buttons start at row 1, so file buttons come after them
                                    new_file_button_start_row = 1 + ((new_dir_count + 4) // 5)
                                    # Max 25 buttons total, minus navigation buttons on row 0, minus directory buttons
                                    new_nav_buttons_count = 1 + (1 if new_parent_path else 0)  # Close + optional Go Up
                                    max_new_file_buttons = min(10, 25 - new_dir_count - new_nav_buttons_count)

                                    for idx, file_item in enumerate(new_readable_files[:max_new_file_buttons], start=1):
                                        file_full_path = f"{target_path.rstrip('/')}/{file_item.name}"

                                        class NewFileReadButton(discord.ui.Button):
                                            def __init__(self, filename, fpath, idx_num):
                                                self.file_path = fpath
                                                self.filename = filename
                                                btn_row = new_file_button_start_row + ((idx_num - 1) // 5)
                                                super().__init__(
                                                    label=f"📄 {filename[:15]}",
                                                    style=discord.ButtonStyle.success,
                                                    row=min(btn_row, 4)
                                                )

                                            async def callback(self, file_btn_interaction: discord.Interaction):
                                                # Security check: only users with correct permissions can read files
                                                user_permissions = get_user_allowed_commands(file_btn_interaction.guild_id, file_btn_interaction.user)
                                                if "inpanel_ptero_files" not in user_permissions:
                                                    await file_btn_interaction.response.send_message(
                                                        "❌ You don't have permission to interact with this browse session.",
                                                        ephemeral=True
                                                    )
                                                    return

                                                await file_btn_interaction.response.defer(ephemeral=True)

                                                try:
                                                    content = await client.read_file(server_id, self.file_path)

                                                    if content is None:
                                                        await file_btn_interaction.followup.send(
                                                            f"❌ Failed to read file: `{self.file_path}`",
                                                            ephemeral=True
                                                        )
                                                        return

                                                    # Smart display: if small enough, show in description; otherwise chunk
                                                    lines = content.splitlines()
                                                    content_text = '\n'.join(lines)

                                                    # Try to fit in description first (cleaner for small files)
                                                    if len(content_text) <= 3900:
                                                        file_embed = discord.Embed(
                                                            title=f"📄 {self.filename}",
                                                            description=f"**Path:** `{self.file_path}`\n**Server:** {server_name}\n\n```\n{content_text}\n```",
                                                            color=discord.Color.green()
                                                        )
                                                    else:
                                                        # Too large for description, use chunked fields
                                                        file_embed = discord.Embed(
                                                            title=f"📄 {self.filename}",
                                                            description=f"**Path:** `{self.file_path}`\n**Server:** {server_name}",
                                                            color=discord.Color.green()
                                                        )

                                                        max_chunk_size = 1016
                                                        chunks = []
                                                        current_chunk = []
                                                        current_size = 0

                                                        for line in lines:
                                                            line_with_newline = line + '\n'
                                                            if current_size + len(line_with_newline) > max_chunk_size:
                                                                if current_chunk:
                                                                    chunks.append(''.join(current_chunk).rstrip('\n'))
                                                                current_chunk = [line_with_newline]
                                                                current_size = len(line_with_newline)
                                                            else:
                                                                current_chunk.append(line_with_newline)
                                                                current_size += len(line_with_newline)

                                                        if current_chunk:
                                                            chunks.append(''.join(current_chunk).rstrip('\n'))

                                                        for i, chunk in enumerate(chunks[:10], 1):
                                                            file_embed.add_field(
                                                                name=f"File Contents (Part {i}/{min(len(chunks), 10)})",
                                                                value=f"```\n{chunk}\n```",
                                                                inline=False
                                                            )

                                                    # Add edit button for .ini files (if not too large)
                                                    if self.filename.lower().endswith('.ini') and len(content) <= 4000:
                                                        class FileReadView(discord.ui.View):
                                                            def __init__(self):
                                                                super().__init__(timeout=300)

                                                            @discord.ui.button(label="✏️ Edit File", style=discord.ButtonStyle.primary)
                                                            async def edit_file(self, edit_interaction: discord.Interaction, _):
                                                                class FileEditModal(discord.ui.Modal, title="Edit File"):
                                                                    file_content = discord.ui.TextInput(
                                                                        label="File Content",
                                                                        style=discord.TextStyle.paragraph,
                                                                        default=content,
                                                                        required=True,
                                                                        max_length=4000
                                                                    )

                                                                    async def on_submit(self, modal_interaction: discord.Interaction):
                                                                        await modal_interaction.response.defer(ephemeral=True)

                                                                        try:
                                                                            new_content = self.file_content.value
                                                                            result = await client.write_file(server_id, self.file_path, new_content)

                                                                            if result.success:
                                                                                await modal_interaction.followup.send(
                                                                                    f"✅ File `{self.file_path}` saved successfully!",
                                                                                    ephemeral=True
                                                                                )
                                                                            else:
                                                                                await modal_interaction.followup.send(
                                                                                    f"❌ Failed to save file: {result.message}",
                                                                                    ephemeral=True
                                                                                )

                                                                        except Exception as e:
                                                                            logger.error(f"Error saving file: {e}", exc_info=True)
                                                                            await modal_interaction.followup.send(
                                                                                f"❌ Error saving file: {e}",
                                                                                ephemeral=True
                                                                            )

                                                                edit_modal = FileEditModal()
                                                                edit_modal.file_path = self.file_path
                                                                await edit_interaction.response.send_modal(edit_modal)

                                                        view = FileReadView()
                                                        await file_btn_interaction.followup.send(embed=file_embed, view=view, ephemeral=True)
                                                    else:
                                                        await file_btn_interaction.followup.send(embed=file_embed, ephemeral=True)

                                                except Exception as e:
                                                    logger.error(f"Error reading file: {e}", exc_info=True)
                                                    await file_btn_interaction.followup.send(f"❌ Error: {e}", ephemeral=True)

                                        new_nav_view.add_item(NewFileReadButton(file_item.name, file_full_path, idx))

                                    await btn_interaction.followup.send(embed=new_embed, view=new_nav_view, ephemeral=False)

                                except Exception as e:
                                    logger.error(f"Error rebrowsing: {e}", exc_info=True)
                                    await btn_interaction.followup.send(f"❌ Error: {e}", ephemeral=True)

                            # Calculate parent path for Go Up button
                            parent_path = None
                            if dir_path and dir_path != '/' and dir_path != '.':
                                parts = dir_path.rstrip('/').split('/')
                                if len(parts) > 1:
                                    parent_path = '/'.join(parts[:-1]) or '/'
                                else:
                                    parent_path = '/'

                            # Add Go Up button
                            if parent_path:
                                class GoUpButton(discord.ui.Button):
                                    def __init__(self, p_path):
                                        self.parent = p_path
                                        super().__init__(label="⬆️ Go Up", style=discord.ButtonStyle.secondary, row=0)

                                    async def callback(self, btn_interaction: discord.Interaction):
                                        await rebrowse_path(btn_interaction, self.parent)

                                nav_view.add_item(GoUpButton(parent_path))

                            # Add Close button
                            class CloseButton(discord.ui.Button):
                                def __init__(self):
                                    super().__init__(label="❌ Close", style=discord.ButtonStyle.danger, row=0)

                                async def callback(self, close_interaction: discord.Interaction):
                                    # Security check: only users with correct permissions can close
                                    user_permissions = get_user_allowed_commands(close_interaction.guild_id, close_interaction.user)
                                    if "inpanel_ptero_files" not in user_permissions:
                                        await close_interaction.response.send_message(
                                            "❌ You don't have permission to interact with this browse session.",
                                            ephemeral=True
                                        )
                                        return

                                    try:
                                        await close_interaction.message.delete()
                                    except:
                                        await close_interaction.response.send_message("❌ Failed to delete message", ephemeral=True)

                            nav_view.add_item(CloseButton())

                            # Add directory buttons (up to 20)
                            dir_count = 0
                            for idx, item in enumerate(dirs[:min(20, len(dirs))], start=1):
                                next_path = f"{dir_path.rstrip('/')}/{item.name}"

                                class DirButton(discord.ui.Button):
                                    def __init__(self, num, name, path):
                                        self.target_path = path
                                        # Row 0 is reserved for Go Up and Close buttons, so start from row 1
                                        btn_row = 1 + ((num - 1) // 5)
                                        super().__init__(label=f"[{num}] {name[:12]}", style=discord.ButtonStyle.primary, row=btn_row)

                                    async def callback(self, btn_interaction: discord.Interaction):
                                        await rebrowse_path(btn_interaction, self.target_path)

                                nav_view.add_item(DirButton(idx, item.name, next_path))
                                dir_count += 1

                            # Add file read buttons for readable files
                            readable_files = [f for f in regular_files if f.name.lower().endswith(('.ini', '.conf', '.cfg', '.log', '.txt', '.json', '.yml', '.yaml'))]

                            # Row 0 is reserved for navigation buttons (Go Up/Close)
                            # Directory buttons start at row 1, so file buttons come after them
                            file_button_start_row = 1 + ((dir_count + 4) // 5)
                            # Max 25 buttons total, minus navigation buttons on row 0 (1 or 2), minus directory buttons
                            nav_buttons_count = 1 + (1 if parent_path else 0)  # Close + optional Go Up
                            max_file_buttons = min(10, 25 - dir_count - nav_buttons_count)

                            for idx, file_item in enumerate(readable_files[:max_file_buttons], start=1):
                                file_full_path = f"{dir_path.rstrip('/')}/{file_item.name}"

                                class FileReadButton(discord.ui.Button):
                                    def __init__(self, filename, fpath, idx_num):
                                        self.file_path = fpath
                                        self.filename = filename
                                        btn_row = file_button_start_row + ((idx_num - 1) // 5)
                                        super().__init__(
                                            label=f"📄 {filename[:15]}",
                                            style=discord.ButtonStyle.success,
                                            row=min(btn_row, 4)
                                        )

                                    async def callback(self, file_btn_interaction: discord.Interaction):
                                        # Security check: only users with correct permissions can read files
                                        user_permissions = get_user_allowed_commands(file_btn_interaction.guild_id, file_btn_interaction.user)
                                        if "inpanel_ptero_files" not in user_permissions:
                                            await file_btn_interaction.response.send_message(
                                                "❌ You don't have permission to interact with this browse session.",
                                                ephemeral=True
                                            )
                                            return

                                        await file_btn_interaction.response.defer(ephemeral=True)

                                        try:
                                            content = await client.read_file(server_id, self.file_path)

                                            if content is None:
                                                await file_btn_interaction.followup.send(
                                                    f"❌ Failed to read file: `{self.file_path}`",
                                                    ephemeral=True
                                                )
                                                return

                                            # Smart display: if small enough, show in description; otherwise chunk
                                            lines = content.splitlines()
                                            content_text = '\n'.join(lines)

                                            # Try to fit in description first (cleaner for small files)
                                            if len(content_text) <= 3900:
                                                file_embed = discord.Embed(
                                                    title=f"📄 {self.filename}",
                                                    description=f"**Path:** `{self.file_path}`\n**Server:** {server_name}\n\n```\n{content_text}\n```",
                                                    color=discord.Color.green()
                                                )
                                            else:
                                                # Too large for description, use chunked fields
                                                file_embed = discord.Embed(
                                                    title=f"📄 {self.filename}",
                                                    description=f"**Path:** `{self.file_path}`\n**Server:** {server_name}",
                                                    color=discord.Color.green()
                                                )

                                                max_chunk_size = 1016
                                                chunks = []
                                                current_chunk = []
                                                current_size = 0

                                                for line in lines:
                                                    line_with_newline = line + '\n'
                                                    if current_size + len(line_with_newline) > max_chunk_size:
                                                        if current_chunk:
                                                            chunks.append(''.join(current_chunk).rstrip('\n'))
                                                        current_chunk = [line_with_newline]
                                                        current_size = len(line_with_newline)
                                                    else:
                                                        current_chunk.append(line_with_newline)
                                                        current_size += len(line_with_newline)

                                                if current_chunk:
                                                    chunks.append(''.join(current_chunk).rstrip('\n'))

                                                for i, chunk in enumerate(chunks[:10], 1):
                                                    file_embed.add_field(
                                                        name=f"File Contents (Part {i}/{min(len(chunks), 10)})",
                                                        value=f"```\n{chunk}\n```",
                                                        inline=False
                                                    )

                                            # Add edit button for .ini files (if not too large)
                                            if self.filename.lower().endswith('.ini') and len(content) <= 4000:
                                                class FileReadView(discord.ui.View):
                                                    def __init__(self):
                                                        super().__init__(timeout=300)

                                                    @discord.ui.button(label="✏️ Edit File", style=discord.ButtonStyle.primary)
                                                    async def edit_file(self, edit_interaction: discord.Interaction, _):
                                                        class FileEditModal(discord.ui.Modal, title="Edit File"):
                                                            file_content = discord.ui.TextInput(
                                                                label="File Content",
                                                                style=discord.TextStyle.paragraph,
                                                                default=content,
                                                                required=True,
                                                                max_length=4000
                                                            )

                                                            async def on_submit(self, modal_interaction: discord.Interaction):
                                                                await modal_interaction.response.defer(ephemeral=True)

                                                                try:
                                                                    new_content = self.file_content.value
                                                                    result = await client.write_file(server_id, self.file_path, new_content)

                                                                    if result.success:
                                                                        await modal_interaction.followup.send(
                                                                            f"✅ File `{self.file_path}` saved successfully!",
                                                                            ephemeral=True
                                                                        )
                                                                    else:
                                                                        await modal_interaction.followup.send(
                                                                            f"❌ Failed to save file: {result.message}",
                                                                            ephemeral=True
                                                                        )

                                                                except Exception as e:
                                                                    logger.error(f"Error saving file: {e}", exc_info=True)
                                                                    await modal_interaction.followup.send(
                                                                        f"❌ Error saving file: {e}",
                                                                        ephemeral=True
                                                                    )

                                                        edit_modal = FileEditModal()
                                                        edit_modal.file_path = self.file_path
                                                        await edit_interaction.response.send_modal(edit_modal)

                                                view = FileReadView()
                                                await file_btn_interaction.followup.send(embed=file_embed, view=view, ephemeral=True)
                                            else:
                                                await file_btn_interaction.followup.send(embed=file_embed, ephemeral=True)

                                        except Exception as e:
                                            logger.error(f"Error reading file: {e}", exc_info=True)
                                            await file_btn_interaction.followup.send(f"❌ Error: {e}", ephemeral=True)

                                nav_view.add_item(FileReadButton(file_item.name, file_full_path, idx))

                            await modal_interaction.followup.send(embed=embed, view=nav_view, ephemeral=False)

                        except Exception as e:
                            logger.error(f"Error listing files: {e}", exc_info=True)
                            await modal_interaction.followup.send(
                                f"An error occurred: {e}",
                                ephemeral=True
                            )

                modal = DirectoryModal()
                await select_interaction.response.send_modal(modal)

        view = discord.ui.View(timeout=60)
        view.add_item(ServerSelect())

        embed = discord.Embed(
            title="Browse Files",
            description="Select a server to browse files:",
            color=discord.Color.blue()
        )

        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    async def _menu_readfile(self, interaction: discord.Interaction):
        """Handle readfile command from menu."""
        if not await require_permission(interaction, 'server_readfile'):
            return

        servers = PterodactylQueries.get_pterodactyl_servers(interaction.guild_id)

        if not servers:
            await interaction.response.send_message(
                "❌ No servers found. Use `/server setup` to configure a Pterodactyl connection first.",
                ephemeral=True
            )
            return

        # Create server selection dropdown
        options = [
            discord.SelectOption(label=s['server_name'], value=s['server_name'])
            for s in servers[:25]  # Max 25 options
        ]

        cog_ref = self

        class ServerSelect(discord.ui.Select):
            def __init__(self):
                super().__init__(placeholder="Select server", options=options)

            async def callback(self, select_interaction: discord.Interaction):
                server_name = self.values[0]

                # Open file path modal
                class FilePathModal(discord.ui.Modal, title="Read File"):
                    file_path = discord.ui.TextInput(
                        label="File Path",
                        placeholder="e.g., /TheIsle/Saved/Config/LinuxServer/Game.ini",
                        required=True,
                        max_length=500
                    )

                    async def on_submit(self, modal_interaction: discord.Interaction):
                        path = self.file_path.value.strip()
                        await modal_interaction.response.defer(ephemeral=True)

                        try:
                            client, server_id = await cog_ref._get_client_for_server(
                                modal_interaction.guild_id, server_name
                            )

                            if not client:
                                await modal_interaction.followup.send(
                                    f"Server `{server_name}` not found.",
                                    ephemeral=True
                                )
                                return

                            content = await client.read_file(server_id, path)

                            if content is None:
                                await modal_interaction.followup.send(
                                    f"Failed to read file `{path}`. File may not exist.",
                                    ephemeral=True
                                )
                                return

                            # Save original full content for editing
                            original_content = content
                            filename = path.split('/')[-1]

                            # Smart display: if small enough, show in description; otherwise chunk
                            lines = content.splitlines()
                            content_text = '\n'.join(lines)

                            # Try to fit in description first (cleaner for small files)
                            if len(content_text) <= 3900:
                                embed = discord.Embed(
                                    title=f"📄 {filename}",
                                    description=f"**Path:** `{path}`\n**Server:** {server_name}\n\n```\n{content_text}\n```",
                                    color=discord.Color.blue()
                                )
                            else:
                                # Too large for description, use chunked fields
                                embed = discord.Embed(
                                    title=f"📄 {filename}",
                                    description=f"**Path:** `{path}`\n**Server:** {server_name}",
                                    color=discord.Color.blue()
                                )

                                max_chunk_size = 1016
                                chunks = []
                                current_chunk = []
                                current_size = 0

                                for line in lines:
                                    line_with_newline = line + '\n'
                                    if current_size + len(line_with_newline) > max_chunk_size:
                                        if current_chunk:
                                            chunks.append(''.join(current_chunk).rstrip('\n'))
                                        current_chunk = [line_with_newline]
                                        current_size = len(line_with_newline)
                                    else:
                                        current_chunk.append(line_with_newline)
                                        current_size += len(line_with_newline)

                                if current_chunk:
                                    chunks.append(''.join(current_chunk).rstrip('\n'))

                                for i, chunk in enumerate(chunks[:10], 1):
                                    embed.add_field(
                                        name=f"File Contents (Part {i}/{min(len(chunks), 10)})",
                                        value=f"```\n{chunk}\n```",
                                        inline=False
                                    )

                            # Add edit button for .ini files (if not too large)
                            if filename.lower().endswith('.ini') and len(original_content) <= 4000:
                                view = FileReadView(
                                    cog=cog_ref,
                                    guild_id=modal_interaction.guild_id,
                                    server=server_name,
                                    file_path=path,
                                    content=original_content
                                )
                                await modal_interaction.followup.send(embed=embed, view=view, ephemeral=True)
                            else:
                                await modal_interaction.followup.send(embed=embed, ephemeral=True)

                        except Exception as e:
                            logger.error(f"Error reading file: {e}", exc_info=True)
                            await modal_interaction.followup.send(
                                f"An error occurred: {e}",
                                ephemeral=True
                            )

                modal = FilePathModal()
                await select_interaction.response.send_modal(modal)

        view = discord.ui.View(timeout=60)
        view.add_item(ServerSelect())

        embed = discord.Embed(
            title="Read File",
            description="Select a server and enter the file path:",
            color=discord.Color.blue()
        )

        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    async def _menu_editfile(self, interaction: discord.Interaction):
        """Handle editfile command from menu."""
        if not await require_permission(interaction, 'server_editfile'):
            return

        servers = PterodactylQueries.get_pterodactyl_servers(interaction.guild_id)

        if not servers:
            await interaction.response.send_message(
                "❌ No servers found. Use `/server setup` to configure a Pterodactyl connection first.",
                ephemeral=True
            )
            return

        # Create server selection dropdown
        options = [
            discord.SelectOption(label=s['server_name'], value=s['server_name'])
            for s in servers[:25]  # Max 25 options
        ]

        cog_ref = self

        class ServerSelect(discord.ui.Select):
            def __init__(self):
                super().__init__(placeholder="Select server", options=options)

            async def callback(self, select_interaction: discord.Interaction):
                server_name = self.values[0]

                # Open file path modal
                class FilePathModal(discord.ui.Modal, title="Edit File"):
                    file_path = discord.ui.TextInput(
                        label="File Path",
                        placeholder="e.g., /TheIsle/Saved/Config/LinuxServer/Game.ini",
                        required=True,
                        max_length=500
                    )

                    async def on_submit(self, modal_interaction: discord.Interaction):
                        path = self.file_path.value.strip()
                        await modal_interaction.response.defer(ephemeral=True)

                        try:
                            client, server_id = await cog_ref._get_client_for_server(
                                modal_interaction.guild_id, server_name
                            )

                            if not client:
                                await modal_interaction.followup.send(
                                    f"Server `{server_name}` not found.",
                                    ephemeral=True
                                )
                                return

                            # Get current content
                            content = await client.read_file(server_id, path)

                            if content is None:
                                content = ""  # New file

                            # Truncate for modal (max 4000 chars)
                            if len(content) > 4000:
                                await modal_interaction.followup.send(
                                    f"File is too large to edit in Discord ({len(content)} chars). "
                                    "Max is 4000 characters. Use **File Operations → Download** instead.",
                                    ephemeral=True
                                )
                                return

                            # Create a new interaction message with edit button
                            view = discord.ui.View(timeout=300)

                            class EditButton(discord.ui.Button):
                                def __init__(self):
                                    super().__init__(label="✏️ Edit File", style=discord.ButtonStyle.primary)

                                async def callback(self, btn_interaction: discord.Interaction):
                                    # Show edit modal
                                    edit_modal = FileEditModal(
                                        client=client,
                                        server_id=server_id,
                                        server_name=server_name,
                                        file_path=path,
                                        current_content=content
                                    )
                                    await btn_interaction.response.send_modal(edit_modal)

                            view.add_item(EditButton())

                            # Show preview
                            preview = content[:500] + ("..." if len(content) > 500 else "")
                            await modal_interaction.followup.send(
                                f"**File:** `{path}`\n"
                                f"**Size:** {len(content)} characters\n"
                                f"**Server:** {server_name}\n\n"
                                f"**Preview:**\n```\n{preview}\n```\n"
                                f"Click the button below to edit:",
                                view=view,
                                ephemeral=True
                            )

                        except Exception as e:
                            logger.error(f"Error preparing file edit: {e}", exc_info=True)
                            await modal_interaction.followup.send(
                                f"An error occurred: {e}",
                                ephemeral=True
                            )

                modal = FilePathModal()
                await select_interaction.response.send_modal(modal)

        view = discord.ui.View(timeout=60)
        view.add_item(ServerSelect())

        embed = discord.Embed(
            title="Edit File",
            description="Select a server and enter the file path:",
            color=discord.Color.blue()
        )

        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    async def _menu_download(self, interaction: discord.Interaction):
        """Handle download command from menu."""
        if not await require_permission(interaction, 'server_download'):
            return

        servers = PterodactylQueries.get_pterodactyl_servers(interaction.guild_id)

        if not servers:
            await interaction.response.send_message(
                "❌ No servers found. Use `/server setup` to configure a Pterodactyl connection first.",
                ephemeral=True
            )
            return

        # Create server selection dropdown
        options = [
            discord.SelectOption(label=s['server_name'], value=s['server_name'])
            for s in servers[:25]  # Max 25 options
        ]

        cog_ref = self

        class ServerSelect(discord.ui.Select):
            def __init__(self):
                super().__init__(placeholder="Select server", options=options)

            async def callback(self, select_interaction: discord.Interaction):
                server_name = self.values[0]

                # Open file path modal
                class FilePathModal(discord.ui.Modal, title="Download File"):
                    file_path = discord.ui.TextInput(
                        label="File Path",
                        placeholder="e.g., /TheIsle/Saved/Config/LinuxServer/Game.ini",
                        required=True,
                        max_length=500
                    )

                    async def on_submit(self, modal_interaction: discord.Interaction):
                        path = self.file_path.value.strip()
                        await modal_interaction.response.defer(ephemeral=True)

                        try:
                            client, server_id = await cog_ref._get_client_for_server(
                                modal_interaction.guild_id, server_name
                            )

                            if not client:
                                await modal_interaction.followup.send(
                                    f"Server `{server_name}` not found.",
                                    ephemeral=True
                                )
                                return

                            url = await client.get_download_url(server_id, path)

                            if not url:
                                await modal_interaction.followup.send(
                                    f"Failed to get download link for `{path}`.",
                                    ephemeral=True
                                )
                                return

                            # Discord buttons have a 512 character URL limit
                            if len(url) > 512:
                                embed = discord.Embed(
                                    title="Download Ready",
                                    description=f"**Download link for `{path.split('/')[-1]}`:**\n\n{url}",
                                    color=discord.Color.green()
                                )
                                embed.add_field(name="Server", value=server_name, inline=True)
                                embed.add_field(name="File", value=f"`{path}`", inline=True)
                                embed.set_footer(text="Copy and paste the link above into your browser")
                                await modal_interaction.followup.send(embed=embed, ephemeral=True)
                            else:
                                embed = discord.Embed(
                                    title="Download Ready",
                                    description=f"Click below to download `{path.split('/')[-1]}`",
                                    color=discord.Color.green()
                                )
                                embed.add_field(name="Server", value=server_name, inline=True)
                                embed.add_field(name="File", value=f"`{path}`", inline=True)

                                view = discord.ui.View()
                                view.add_item(discord.ui.Button(
                                    label="Download",
                                    url=url,
                                    style=discord.ButtonStyle.link
                                ))

                                await modal_interaction.followup.send(embed=embed, view=view, ephemeral=True)

                        except Exception as e:
                            logger.error(f"Error getting download link: {e}", exc_info=True)
                            await modal_interaction.followup.send(
                                f"An error occurred: {e}",
                                ephemeral=True
                            )

                modal = FilePathModal()
                await select_interaction.response.send_modal(modal)

        view = discord.ui.View(timeout=60)
        view.add_item(ServerSelect())

        embed = discord.Embed(
            title="Download File",
            description="Select a server and enter the file path:",
            color=discord.Color.blue()
        )

        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    async def _menu_console(self, interaction: discord.Interaction):
        """Handle console command from menu."""
        if not await require_permission(interaction, 'server_console'):
            return

        servers = PterodactylQueries.get_pterodactyl_servers(interaction.guild_id)

        if not servers:
            await interaction.response.send_message(
                "❌ No servers found. Use `/server setup` to configure a Pterodactyl connection first.",
                ephemeral=True
            )
            return

        # Create server selection dropdown
        options = [
            discord.SelectOption(label=s['server_name'], value=s['server_name'])
            for s in servers[:25]  # Max 25 options
        ]

        cog_ref = self

        class ServerSelect(discord.ui.Select):
            def __init__(self):
                super().__init__(placeholder="Select server", options=options)

            async def callback(self, select_interaction: discord.Interaction):
                server_name = self.values[0]

                # Open console command modal
                class ConsoleCommandModal(discord.ui.Modal, title="Console Command"):
                    command = discord.ui.TextInput(
                        label="Command",
                        placeholder="e.g., save or any console command",
                        required=True,
                        max_length=500
                    )

                    async def on_submit(self, modal_interaction: discord.Interaction):
                        cmd = self.command.value.strip()
                        await modal_interaction.response.defer(ephemeral=True)

                        try:
                            client, server_id = await cog_ref._get_client_for_server(
                                modal_interaction.guild_id, server_name
                            )

                            if not client:
                                await modal_interaction.followup.send(
                                    f"Server `{server_name}` not found.",
                                    ephemeral=True
                                )
                                return

                            response = await client.send_command(server_id, cmd)

                            if response.success:
                                embed = discord.Embed(
                                    title="Command Sent",
                                    description=f"```{cmd}```",
                                    color=discord.Color.green()
                                )
                                embed.set_footer(text=f"Server: {server_name}")
                            else:
                                embed = discord.Embed(
                                    title="Command Failed",
                                    description=response.message,
                                    color=discord.Color.red()
                                )

                            await modal_interaction.followup.send(embed=embed, ephemeral=True)

                        except Exception as e:
                            logger.error(f"Error sending console command: {e}", exc_info=True)
                            await modal_interaction.followup.send(
                                f"An error occurred: {e}",
                                ephemeral=True
                            )

                modal = ConsoleCommandModal()
                await select_interaction.response.send_modal(modal)

        view = discord.ui.View(timeout=60)
        view.add_item(ServerSelect())

        embed = discord.Embed(
            title="Console Command",
            description="Select a server and enter the console command:",
            color=discord.Color.blue()
        )

        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


class ServerControlView(discord.ui.View):
    """View with server control buttons."""

    def __init__(self, cog, guild_id: int, server_name: str, server_id: str, current_status: str):
        super().__init__(timeout=300)  # 5 minute timeout
        self.cog = cog
        self.guild_id = guild_id
        self.server_name = server_name
        self.server_id = server_id
        self.current_status = current_status
        self._update_button_states()

    def _update_button_states(self):
        """Update button enabled/disabled states based on current status."""
        # Disable start button if already running
        if self.current_status.lower() == "running":
            self.start_button.disabled = True
            self.stop_button.disabled = False
        # Disable stop button if already stopped
        elif self.current_status.lower() in ["stopped", "offline"]:
            self.start_button.disabled = False
            self.stop_button.disabled = True
        else:
            # Unknown status - enable both
            self.start_button.disabled = False
            self.stop_button.disabled = False

    @discord.ui.button(label="Start", style=discord.ButtonStyle.success, emoji="▶️")
    async def start_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Start the server."""
        await interaction.response.defer(ephemeral=True)

        try:
            client, _ = await self.cog._get_client_for_server(self.guild_id, self.server_name)
            if not client:
                await interaction.followup.send("Server not found.", ephemeral=True)
                return

            result = await client.start_server(self.server_id)

            embed = discord.Embed(
                title="Server Start",
                description=result.message,
                color=discord.Color.green() if result.success else discord.Color.red()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as e:
            logger.error(f"Error starting server: {e}", exc_info=True)
            embed = discord.Embed(
                title="Server Start",
                description=f"An error occurred: {e}",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)

    @discord.ui.button(label="Stop", style=discord.ButtonStyle.danger, emoji="⏹️")
    async def stop_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Stop the server."""
        await interaction.response.defer(ephemeral=True)

        try:
            client, _ = await self.cog._get_client_for_server(self.guild_id, self.server_name)
            if not client:
                await interaction.followup.send("Server not found.", ephemeral=True)
                return

            result = await client.stop_server(self.server_id)

            embed = discord.Embed(
                title="Server Stop",
                description=result.message,
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as e:
            logger.error(f"Error stopping server: {e}", exc_info=True)
            embed = discord.Embed(
                title="Server Stop",
                description=f"An error occurred: {e}",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)

    @discord.ui.button(label="Restart", style=discord.ButtonStyle.primary, emoji="🔄")
    async def restart_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Restart the server."""
        await interaction.response.defer(ephemeral=True)

        try:
            client, _ = await self.cog._get_client_for_server(self.guild_id, self.server_name)
            if not client:
                await interaction.followup.send("Server not found.", ephemeral=True)
                return

            result = await client.restart_server(self.server_id)

            embed = discord.Embed(
                title="Server Restart",
                description=result.message,
                color=discord.Color.blue()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as e:
            logger.error(f"Error restarting server: {e}", exc_info=True)
            embed = discord.Embed(
                title="Server Restart",
                description=f"An error occurred: {e}",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)

    @discord.ui.button(label="Refresh", style=discord.ButtonStyle.secondary, emoji="🔄", row=1)
    async def refresh_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Refresh server information."""
        await interaction.response.defer()

        try:
            client, _ = await self.cog._get_client_for_server(self.guild_id, self.server_name)
            if not client:
                await interaction.followup.send("Server not found.", ephemeral=True)
                return

            # Get fresh server info
            info = await client.get_server_info(self.server_id)
            resources = await client.get_server_resources(self.server_id)

            if not info:
                await interaction.followup.send("Failed to get server information.", ephemeral=True)
                return

            # Build updated embed
            embed, new_status = self.cog._build_server_info_embed(info, resources)

            # Update current status and button states
            self.current_status = new_status
            self._update_button_states()

            # Update the original message
            await interaction.edit_original_response(embed=embed, view=self)

        except Exception as e:
            logger.error(f"Error refreshing server info: {e}", exc_info=True)
            await interaction.followup.send(f"An error occurred: {e}", ephemeral=True)


class FileReadView(discord.ui.View):
    """View with an Edit button for file reading."""

    def __init__(self, cog, guild_id: int, server: str, file_path: str, content: str):
        super().__init__(timeout=300)
        self.cog = cog
        self.guild_id = guild_id
        self.server = server
        self.file_path = file_path
        self.current_content = content

    @discord.ui.button(label="Edit File", style=discord.ButtonStyle.primary, emoji="✏️")
    async def edit_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Open the file editor modal."""
        # Check permission
        from services.permissions import require_permission
        if not await require_permission(interaction, 'server_editfile'):
            return

        try:
            # Check if file is too large for modal
            if len(self.current_content) > 4000:
                await interaction.response.send_message(
                    f"File is too large to edit in Discord ({len(self.current_content)} chars). "
                    "Max is 4000 characters. Use `/server download` instead.",
                    ephemeral=True
                )
                return

            # Get client
            client, server_id = await self.cog._get_client_for_server(
                self.guild_id, self.server
            )

            if not client:
                await interaction.response.send_message(
                    f"Server `{self.server}` not found.",
                    ephemeral=True
                )
                return

            # Show edit modal
            modal = FileEditModal(
                client=client,
                server_id=server_id,
                server_name=self.server,
                file_path=self.file_path,
                current_content=self.current_content
            )
            await interaction.response.send_modal(modal)

        except Exception as e:
            logger.error(f"Error opening file editor: {e}", exc_info=True)
            await interaction.response.send_message(
                f"An error occurred: {e}",
                ephemeral=True
            )


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
    """Load the Pterodactyl cogs."""
    server_cog = ServerControlCommands(bot)
    await bot.add_cog(server_cog)
    await bot.add_cog(PterodactylMenuCommands(bot, server_cog))
