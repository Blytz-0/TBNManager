# cogs/admin/rcon.py
"""
RCON Integration Commands (Premium)

Commands for managing game servers via RCON:
- Server configuration (add, remove, list, test)
- Player management (kick, ban, announce)
- Player verification via in-game codes
"""

import discord
from discord import app_commands
from discord.ext import commands
from database.queries import (
    GuildQueries, RCONServerQueries, RCONCommandLogQueries, PlayerQueries
)
from database.queries.rcon import DinoPools, AIRestrictions, DisabledDinos
from services.permissions import require_permission, get_user_allowed_commands
from services.rcon import get_rcon_client, GameType, RCONManager, rcon_manager
import logging
from typing import Optional

logger = logging.getLogger(__name__)


# Game type choices for dropdowns
GAME_CHOICES = [
    discord.SelectOption(label="The Isle Evrima", value="the_isle_evrima", description="The Isle Evrima RCON"),
    discord.SelectOption(label="Path of Titans", value="path_of_titans", description="Path of Titans RCON"),
]


# ==========================================
# DROPDOWN-BASED RCON INTERFACE
# ==========================================

class RCONCommandSelect(discord.ui.Select):
    """Dropdown menu for selecting RCON commands."""

    def __init__(self, category: str, cog, user_permissions: set, panel_message=None):
        self.cog = cog
        self.category = category
        self.user_permissions = user_permissions
        self.panel_message = panel_message

        # Map command values to permission names
        permission_map = {
            "addserver": "inpanel_rcon_addserver",
            "servers": "inpanel_rcon_servers",
            "removeserver": "inpanel_rcon_removeserver",
            "test": "inpanel_rcon_test",
            "console": "inpanel_rcon_console",
            "kick": "inpanel_rcon_kick",
            "ban": "inpanel_rcon_ban",
            "announce": "inpanel_rcon_announce",
            "dm": "inpanel_rcon_dm",
            "players": "inpanel_rcon_players",
            "wipecorpses": "inpanel_rcon_wipecorpses",
            "allowclasses": "inpanel_rcon_allowclasses",
            "addremoveclass": "inpanel_rcon_addremoveclass",
            "globalchat": "inpanel_rcon_globalchat",
            "togglehumans": "inpanel_rcon_togglehumans",
            "toggleai": "inpanel_rcon_toggleai",
            "disableai": "inpanel_rcon_disableai",
            "aidensity": "inpanel_rcon_aidensity",
            "whitelist": "inpanel_rcon_whitelist",
            "managewhitelist": "inpanel_rcon_managewhitelist",
        }

        # Define options based on category
        options_map = {
            "setup": [
                discord.SelectOption(label="Add Server", value="addserver", description="Configure new RCON server", emoji="➕"),
                discord.SelectOption(label="List Servers", value="servers", description="Show configured servers", emoji="📋"),
                discord.SelectOption(label="Remove Server", value="removeserver", description="Delete server config", emoji="🗑️"),
                discord.SelectOption(label="Test Connection", value="test", description="Test RCON connection", emoji="🔌"),
            ],
            "raw": [
                discord.SelectOption(label="Raw Console Command", value="console", description="Send raw RCON (PoT/Any game)", emoji="⌨️"),
            ],
            "player": [
                discord.SelectOption(label="Kick Player", value="kick", description="Kick player from server", emoji="👢"),
                discord.SelectOption(label="Ban Player", value="ban", description="Ban player permanently", emoji="🔨"),
                discord.SelectOption(label="Announce", value="announce", description="Send server announcement", emoji="📢"),
                discord.SelectOption(label="Direct Message", value="dm", description="DM player in-game", emoji="💬"),
                discord.SelectOption(label="List Players", value="players", description="Show online players", emoji="👥"),
            ],
            "evrima": [
                discord.SelectOption(label="Wipe Corpses", value="wipecorpses", description="Remove all corpses", emoji="🧹"),
                discord.SelectOption(label="Allow Classes", value="allowclasses", description="Enable/disable playable dinos", emoji="🦖"),
                discord.SelectOption(label="Add or Remove Class", value="addremoveclass", description="Manage master dinosaur pool", emoji="🔧"),
                discord.SelectOption(label="Toggle Global Chat", value="globalchat", description="Enable/disable chat", emoji="💬"),
                discord.SelectOption(label="Toggle Humans", value="togglehumans", description="Enable/disable humans", emoji="🚶"),
                discord.SelectOption(label="Toggle AI", value="toggleai", description="Enable/disable AI", emoji="🤖"),
                discord.SelectOption(label="Disable AI Classes", value="disableai", description="Disable specific AI", emoji="🚫"),
                discord.SelectOption(label="AI Density", value="aidensity", description="Set AI spawn density", emoji="📊"),
                discord.SelectOption(label="Toggle Whitelist", value="whitelist", description="Enable/disable whitelist", emoji="🔐"),
                discord.SelectOption(label="Manage Whitelist", value="managewhitelist", description="Add or remove players", emoji="📝"),
            ],
        }

        # Filter options based on user permissions
        all_options = options_map.get(category, [])
        filtered_options = [
            opt for opt in all_options
            if permission_map.get(opt.value) in user_permissions
        ]

        options = filtered_options
        placeholder_map = {
            "setup": "Setup & Configuration",
            "raw": "Raw Commands",
            "player": "Player Management",
            "evrima": "Evrima Game Settings",
        }

        super().__init__(
            placeholder=placeholder_map.get(category, "Select a command"),
            options=options,
            row={"setup": 0, "raw": 1, "player": 2, "evrima": 3}.get(category, 0)
        )

    async def callback(self, interaction: discord.Interaction):
        """Handle command selection."""
        command = self.values[0]

        # Route to appropriate modal or action
        if command == "addserver":
            # Show game type selection first
            view = GameTypeSelectView(self.cog)
            await interaction.response.send_message(
                "Select the game type for your RCON server:",
                view=view,
                ephemeral=True
            )
        elif command == "servers":
            await self.cog._show_servers(interaction)
            # Refresh after immediate action
            if self.panel_message and self.user_permissions:
                await self.cog._refresh_panel(self.panel_message, self.user_permissions)
        elif command == "removeserver":
            await self.cog._show_remove_server_modal(interaction)
        elif command == "test":
            await self.cog._show_test_connection_modal(interaction)
        elif command == "kick":
            await self.cog._show_kick_modal(interaction)
        elif command == "ban":
            await self.cog._show_ban_modal(interaction)
        elif command == "announce":
            await self.cog._show_announce_modal(interaction)
        elif command == "dm":
            await self.cog._show_dm_modal(interaction)
        elif command == "players":
            await self.cog._show_players_modal(interaction)
        elif command == "console":
            await self.cog._show_console_modal(interaction)
        # elif command == "save":
        #     await self.cog._show_save_modal(interaction)  # Commented out - server saves automatically
        elif command == "wipecorpses":
            await self.cog._show_wipecorpses_modal(interaction)
        elif command == "allowclasses":
            await self.cog._show_allowclasses_modal(interaction)
        elif command == "addremoveclass":
            await self.cog._show_addremoveclass_modal(interaction)
        elif command == "whitelist":
            await self.cog._show_whitelist_modal(interaction)
        elif command == "managewhitelist":
            await self.cog._show_managewhitelist_modal(interaction)
        elif command == "globalchat":
            await self.cog._show_globalchat_modal(interaction)
        elif command == "togglehumans":
            await self.cog._show_togglehumans_modal(interaction)
        elif command == "toggleai":
            await self.cog._show_toggleai_modal(interaction)
        elif command == "disableai":
            await self.cog._show_disableai_modal(interaction)
        elif command == "aidensity":
            await self.cog._show_aidensity_modal(interaction)


class RCONCommandView(discord.ui.View):
    """Main view with all RCON command dropdowns."""

    def __init__(self, cog, user_permissions: set, panel_message=None):
        super().__init__(timeout=300)
        self.cog = cog
        self.panel_message = panel_message

        # Define which permissions belong to each category
        category_permissions = {
            "setup": {"inpanel_rcon_addserver", "inpanel_rcon_servers", "inpanel_rcon_removeserver", "inpanel_rcon_test"},
            "raw": {"inpanel_rcon_console"},
            "player": {"inpanel_rcon_kick", "inpanel_rcon_ban", "inpanel_rcon_announce", "inpanel_rcon_dm", "inpanel_rcon_players"},
            "evrima": {
                "inpanel_rcon_wipecorpses", "inpanel_rcon_allowclasses", "inpanel_rcon_addremoveclass",
                "inpanel_rcon_globalchat", "inpanel_rcon_togglehumans", "inpanel_rcon_toggleai",
                "inpanel_rcon_disableai", "inpanel_rcon_aidensity", "inpanel_rcon_whitelist", "inpanel_rcon_managewhitelist"
            }
        }

        # Add category dropdowns only if user has at least one permission in that category
        for category in ["setup", "raw", "player", "evrima"]:
            if user_permissions & category_permissions[category]:  # Check if any permission in category
                self.add_item(RCONCommandSelect(category, cog, user_permissions, panel_message))


class GameTypeSelectView(discord.ui.View):
    """View for selecting game type when adding a server."""

    def __init__(self, cog):
        super().__init__(timeout=60)
        self.cog = cog

    @discord.ui.select(
        placeholder="Select game type",
        options=GAME_CHOICES
    )
    async def game_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        game_type = select.values[0]
        game_display = "The Isle Evrima" if game_type == "the_isle_evrima" else "Path of Titans"

        # Open the add server modal
        modal = AddRCONServerModal(game_type, game_display)
        await interaction.response.send_modal(modal)


class ServerSelectView(discord.ui.View):
    """View for selecting a server to execute a command on."""

    def __init__(self, cog, command_type: str, guild_id: int, **kwargs):
        super().__init__(timeout=60)
        self.cog = cog
        self.command_type = command_type
        self.guild_id = guild_id
        self.kwargs = kwargs

        # Get available servers
        servers = RCONServerQueries.get_servers(guild_id, active_only=True)

        if not servers:
            return

        # Build server options
        options = []
        for server in servers[:25]:  # Discord max 25 options
            game = "🦖 Evrima" if server['game_type'] == 'the_isle_evrima' else "🦕 PoT"
            options.append(
                discord.SelectOption(
                    label=server['server_name'],
                    value=str(server['id']),
                    description=f"{game} - {server['host']}:{server['port']}"
                )
            )

        # Add "All Servers" option at the top
        if len(servers) > 1:
            options.insert(0, discord.SelectOption(
                label="All Servers",
                value="all",
                description="Execute on all configured servers",
                emoji="🌐"
            ))

        self.add_item(ServerSelect(options, self.cog, self.command_type, self.guild_id, self.kwargs))


class ToggleSelectView(discord.ui.View):
    """View for selecting on/off toggle before server selection."""

    def __init__(self, cog, command_type: str, guild_id: int, title: str, description: str):
        super().__init__(timeout=60)
        self.cog = cog
        self.command_type = command_type
        self.guild_id = guild_id
        self.title = title
        self.description = description

        self.add_item(ToggleSelect(cog, command_type, guild_id))


class ToggleSelect(discord.ui.Select):
    """Dropdown for on/off selection."""

    def __init__(self, cog, command_type, guild_id):
        options = [
            discord.SelectOption(label="Enable (ON)", value="on", emoji="✅"),
            discord.SelectOption(label="Disable (OFF)", value="off", emoji="❌"),
        ]
        super().__init__(placeholder="Select action", options=options)
        self.cog = cog
        self.command_type = command_type
        self.guild_id = guild_id

    async def callback(self, interaction: discord.Interaction):
        action = self.values[0]

        # Get available servers (filter by game type if applicable)
        servers = RCONServerQueries.get_servers(self.guild_id, active_only=True)

        # For Evrima-only commands, filter to Evrima servers
        if self.command_type in ['whitelist_toggle', 'globalchat', 'togglehumans', 'toggleai']:
            servers = [s for s in servers if s.get('game_type') == 'the_isle_evrima']

        if not servers:
            game_msg = " (Evrima servers only)" if self.command_type in ['whitelist_toggle', 'globalchat', 'togglehumans', 'toggleai'] else ""
            await interaction.response.send_message(
                f"No active servers configured{game_msg}. Add a server first.",
                ephemeral=True
            )
            return

        # If only 1 server, execute directly
        if len(servers) == 1:
            await interaction.response.defer(ephemeral=True)
            servers_to_execute = self.cog._get_target_servers(self.guild_id, None)
            if self.command_type in ['whitelist_toggle', 'globalchat', 'togglehumans', 'toggleai']:
                servers_to_execute = [s for s in servers_to_execute if s.get('game_type') == 'the_isle_evrima']

            # Execute the toggle command
            if self.command_type == 'whitelist_toggle':
                results = await rcon_manager.execute_on_servers(servers_to_execute, 'toggle_whitelist', action)
            elif self.command_type == 'globalchat':
                results = await rcon_manager.execute_on_servers(servers_to_execute, 'toggle_global_chat', action)
            elif self.command_type == 'togglehumans':
                results = await rcon_manager.execute_on_servers(servers_to_execute, 'toggle_humans', action)
            elif self.command_type == 'toggleai':
                results = await rcon_manager.execute_on_servers(servers_to_execute, 'toggle_ai', action)
            else:
                await interaction.followup.send(f"Unknown command type: {self.command_type}", ephemeral=True)
                return

            embed = self.cog._build_results_embed(
                f"{'✅ Enable' if action == 'on' else '❌ Disable'} Results",
                results,
                servers_to_execute
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            # Multiple servers - show server selection
            view = ServerSelectView(self.cog, self.command_type, self.guild_id, action=action)
            embed = discord.Embed(
                title=f"{'✅ Enable' if action == 'on' else '❌ Disable'}",
                description="Select which server:",
                color=discord.Color.green() if action == 'on' else discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


class ServerSelect(discord.ui.Select):
    """Dropdown for server selection."""

    def __init__(self, options, cog, command_type, guild_id, kwargs):
        super().__init__(placeholder="Select a server", options=options)
        self.cog = cog
        self.command_type = command_type
        self.guild_id = guild_id
        self.command_kwargs = kwargs

    async def callback(self, interaction: discord.Interaction):
        server_value = self.values[0]

        # Get target servers
        if server_value == "all":
            servers = self.cog._get_target_servers(self.guild_id, None)
        else:
            server_id = int(server_value)
            server_data = RCONServerQueries.get_server(server_id, self.guild_id)
            servers = [server_data] if server_data else []

        if not servers:
            await interaction.response.send_message(
                "Server not found.",
                ephemeral=True
            )
            return

        # Execute the command
        await self._execute_command(interaction, servers)

    async def _execute_command(self, interaction: discord.Interaction, servers):
        """Execute the selected RCON command."""
        await interaction.response.defer(ephemeral=True)

        try:
            if self.command_type == "save":
                results = await rcon_manager.execute_on_servers(servers, 'save')
                embed = self.cog._build_results_embed("Save Results", results, servers)

            elif self.command_type == "wipecorpses":
                results = await rcon_manager.execute_on_servers(servers, 'wipe_corpses')
                embed = self.cog._build_results_embed("Wipe Corpses Results", results, servers)

            elif self.command_type == "whitelist_toggle":
                action = self.command_kwargs.get('action', 'on')
                enabled = action == 'on'
                results = await rcon_manager.execute_on_servers(servers, 'toggle_whitelist', enabled)
                embed = self.cog._build_results_embed(f"Whitelist {action.upper()} Results", results, servers)

            elif self.command_type == "globalchat":
                action = self.command_kwargs.get('action', 'on')
                enabled = action == 'on'
                results = await rcon_manager.execute_on_servers(servers, 'toggle_global_chat', enabled)
                embed = self.cog._build_results_embed(f"Global Chat {action.upper()} Results", results, servers)

            elif self.command_type == "togglehumans":
                action = self.command_kwargs.get('action', 'on')
                enabled = action == 'on'
                results = await rcon_manager.execute_on_servers(servers, 'toggle_humans', enabled)
                embed = self.cog._build_results_embed(f"Humans {action.upper()} Results", results, servers)

            elif self.command_type == "toggleai":
                action = self.command_kwargs.get('action', 'on')
                enabled = action == 'on'
                results = await rcon_manager.execute_on_servers(servers, 'toggle_ai', enabled)
                embed = self.cog._build_results_embed(f"AI {action.upper()} Results", results, servers)

            else:
                await interaction.followup.send("Unknown command type.", ephemeral=True)
                return

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Error executing {self.command_type}: {e}", exc_info=True)
            await interaction.followup.send(f"An error occurred: {e}", ephemeral=True)


class AddRCONServerModal(discord.ui.Modal):
    """Modal for adding a new RCON server."""

    server_name = discord.ui.TextInput(
        label="Server Name",
        placeholder="e.g., The Isle Server 1",
        required=True,
        max_length=100
    )

    host = discord.ui.TextInput(
        label="RCON Host (IP or hostname)",
        placeholder="e.g., 192.168.1.37 or game.example.com",
        required=True,
        max_length=255
    )

    port = discord.ui.TextInput(
        label="RCON Port",
        placeholder="e.g., 44000",
        required=True,
        max_length=5
    )

    password = discord.ui.TextInput(
        label="RCON Password",
        placeholder="Your RCON password",
        required=True,
        max_length=100,
        style=discord.TextStyle.short
    )

    def __init__(self, game_type: str, game_display: str):
        super().__init__(title=f"Add {game_display} Server")
        self.game_type = game_type
        self.game_display = game_display
        # Set default port based on game type
        default_port = "8888" if game_type == "the_isle_evrima" else "7779"
        self.port.default = default_port

    async def on_submit(self, interaction: discord.Interaction):
        try:
            # Validate port
            try:
                port_num = int(self.port.value)
                if not (1 <= port_num <= 65535):
                    raise ValueError("Port out of range")
            except ValueError:
                await interaction.response.send_message(
                    "Invalid port number. Please enter a number between 1 and 65535.",
                    ephemeral=True
                )
                return

            # Check for duplicate name
            existing = RCONServerQueries.get_server_by_name(
                interaction.guild_id, self.server_name.value
            )
            if existing:
                await interaction.response.send_message(
                    f"A server named `{self.server_name.value}` already exists. Choose a different name.",
                    ephemeral=True
                )
                return

            server_id = RCONServerQueries.add_server(
                guild_id=interaction.guild_id,
                server_name=self.server_name.value,
                game_type=self.game_type,
                host=self.host.value,
                port=port_num,
                password=self.password.value
            )

            embed = discord.Embed(
                title="RCON Server Added",
                description=f"Server `{self.server_name.value}` has been configured.",
                color=discord.Color.green()
            )
            embed.add_field(name="Game", value=self.game_display, inline=True)
            embed.add_field(name="Host", value=f"`{self.host.value}:{port_num}`", inline=True)
            embed.add_field(name="Server ID", value=str(server_id), inline=True)
            embed.set_footer(text="Use /rcon test to verify the connection")

            await interaction.response.send_message(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Error adding RCON server: {e}", exc_info=True)
            await interaction.response.send_message(
                "An error occurred while adding the server.",
                ephemeral=True
            )


# ==========================================
# PLAYER MANAGEMENT MODALS
# ==========================================

class KickPlayerModal(discord.ui.Modal, title="Kick Player"):
    """Modal for kicking a player."""

    player_id = discord.ui.TextInput(
        label="Player ID (Steam ID or Alderon ID)",
        placeholder="e.g., 76561198012345678 or 123-456-789",
        required=True,
        max_length=50
    )

    reason = discord.ui.TextInput(
        label="Reason",
        placeholder="Reason for kicking this player",
        required=False,
        default="Kicked by admin",
        style=discord.TextStyle.paragraph,
        max_length=200
    )

    server = discord.ui.TextInput(
        label="Server (leave blank for all servers)",
        placeholder="Server name or leave empty for all",
        required=False,
        max_length=100
    )

    def __init__(self, cog):
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        try:
            server_name = self.server.value.strip() if self.server.value else None
            servers = self.cog._get_target_servers(interaction.guild_id, server_name)
            if not servers:
                await interaction.followup.send(
                    "No servers configured or server not found.",
                    ephemeral=True
                )
                return

            results = await rcon_manager.execute_on_servers(
                servers, 'kick', self.player_id.value, self.reason.value or "Kicked by admin"
            )

            embed = self.cog._build_results_embed("Kick Results", results, servers)

            # Log command
            for server_id, response in results.items():
                RCONCommandLogQueries.log_command(
                    guild_id=interaction.guild_id,
                    command_type='kick',
                    executed_by_id=interaction.user.id,
                    success=response.success,
                    server_id=server_id,
                    target_player_id=self.player_id.value,
                    command_data={'reason': self.reason.value or "Kicked by admin"},
                    response_message=response.message
                )

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Error kicking player: {e}", exc_info=True)
            await interaction.followup.send(f"An error occurred: {e}", ephemeral=True)


class AnnounceModal(discord.ui.Modal, title="Server Announcement"):
    """Modal for server announcements."""

    message = discord.ui.TextInput(
        label="Announcement Message",
        placeholder="Enter your announcement message...",
        required=True,
        style=discord.TextStyle.paragraph,
        max_length=500
    )

    server = discord.ui.TextInput(
        label="Server (leave blank for all servers)",
        placeholder="Server name or leave empty for all",
        required=False,
        max_length=100
    )

    def __init__(self, cog):
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        try:
            server_name = self.server.value.strip() if self.server.value else None
            servers = self.cog._get_target_servers(interaction.guild_id, server_name)
            if not servers:
                await interaction.followup.send(
                    "No servers configured or server not found.",
                    ephemeral=True
                )
                return

            results = await rcon_manager.execute_on_servers(
                servers, 'announce', self.message.value
            )

            embed = self.cog._build_results_embed("Announcement Results", results, servers)

            # Add the message that was sent
            embed.insert_field_at(
                0,
                name="Message Sent",
                value=f"```{self.message.value[:500]}```",
                inline=False
            )

            # Log command
            for server_id, response in results.items():
                RCONCommandLogQueries.log_command(
                    guild_id=interaction.guild_id,
                    command_type='announce',
                    executed_by_id=interaction.user.id,
                    success=response.success,
                    server_id=server_id,
                    command_data={'message': self.message.value},
                    response_message=response.message
                )

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Error sending announcement: {e}", exc_info=True)
            await interaction.followup.send(f"An error occurred: {e}", ephemeral=True)


class AnnounceMessageModal(discord.ui.Modal, title="Server Announcement"):
    """Simplified modal for announcements (used with server selection view)."""

    message = discord.ui.TextInput(
        label="Announcement Message",
        placeholder="Enter your announcement message...",
        required=True,
        style=discord.TextStyle.paragraph,
        max_length=500
    )

    def __init__(self, cog, servers: list[dict]):
        super().__init__()
        self.cog = cog
        self.servers = servers

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        try:
            results = await rcon_manager.execute_on_servers(
                self.servers, 'announce', self.message.value
            )

            embed = self.cog._build_results_embed("Announcement Results", results, self.servers)

            # Add the message that was sent
            embed.insert_field_at(
                0,
                name="Message Sent",
                value=f"```{self.message.value[:500]}```",
                inline=False
            )

            # Log command
            for server_id, response in results.items():
                RCONCommandLogQueries.log_command(
                    guild_id=interaction.guild_id,
                    command_type='announce',
                    executed_by_id=interaction.user.id,
                    success=response.success,
                    server_id=server_id,
                    command_data={'message': self.message.value},
                    response_message=response.message
                )

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Error sending announcement: {e}", exc_info=True)
            await interaction.followup.send(f"An error occurred: {e}", ephemeral=True)


class AnnounceServerSelect(discord.ui.Select):
    """Server selection for announcements."""

    def __init__(self, options, cog, guild_id):
        super().__init__(placeholder="Select server for announcement", options=options)
        self.cog = cog
        self.guild_id = guild_id

    async def callback(self, interaction: discord.Interaction):
        server_value = self.values[0]

        # Get target servers
        if server_value == "all":
            servers = self.cog._get_target_servers(self.guild_id, None)
        else:
            server_id = int(server_value)
            server_data = RCONServerQueries.get_server(server_id, self.guild_id)
            servers = [server_data] if server_data else []

        if not servers:
            await interaction.response.send_message(
                "Server not found.",
                ephemeral=True
            )
            return

        # Open the message modal
        modal = AnnounceMessageModal(self.cog, servers)
        await interaction.response.send_modal(modal)


class AnnounceServerSelectView(discord.ui.View):
    """View for selecting server before announcement."""

    def __init__(self, cog, guild_id: int):
        super().__init__(timeout=60)
        self.cog = cog
        self.guild_id = guild_id

        # Get available servers
        servers = RCONServerQueries.get_servers(guild_id, active_only=True)

        if not servers:
            return

        # Build server options
        options = []
        for server in servers[:25]:  # Discord max 25 options
            game = "🦖 Evrima" if server['game_type'] == 'the_isle_evrima' else "🦕 PoT"
            options.append(
                discord.SelectOption(
                    label=server['server_name'],
                    value=str(server['id']),
                    description=f"{game} - {server['host']}:{server['port']}"
                )
            )

        # Add "All Servers" option at the top
        if len(servers) > 1:
            options.insert(0, discord.SelectOption(
                label="All Servers",
                value="all",
                description="Send announcement to all configured servers",
                emoji="🌐"
            ))

        self.add_item(AnnounceServerSelect(options, cog, guild_id))


class PlayerActionServerSelect(discord.ui.Select):
    """Server selection for player actions (kick, ban, dm, console)."""

    def __init__(self, options, cog, guild_id, action_type: str, title: str):
        super().__init__(placeholder=f"Select server for {action_type}", options=options)
        self.cog = cog
        self.guild_id = guild_id
        self.action_type = action_type
        self.title = title

    async def callback(self, interaction: discord.Interaction):
        server_value = self.values[0]

        # Get target servers
        if server_value == "all":
            servers = self.cog._get_target_servers(self.guild_id, None)
        else:
            server_id = int(server_value)
            server_data = RCONServerQueries.get_server(server_id, self.guild_id)
            servers = [server_data] if server_data else []

        if not servers:
            await interaction.response.send_message(
                "Server not found.",
                ephemeral=True
            )
            return

        # Open the appropriate modal based on action type
        if self.action_type == "kick":
            modal = KickPlayerModalSimplified(self.cog, servers)
        elif self.action_type == "ban":
            modal = BanPlayerModal(self.cog, servers)
        elif self.action_type == "dm":
            modal = DMPlayerModalSimplified(self.cog, servers)
        elif self.action_type == "console":
            modal = ConsoleCommandModalSimplified(self.cog, servers)
        elif self.action_type == "whitelistadd":
            modal = WhitelistAddModal(self.cog, servers)
        elif self.action_type == "whitelistremove":
            modal = WhitelistRemoveModal(self.cog, servers)
        else:
            await interaction.response.send_message("Unknown action type.", ephemeral=True)
            return

        await interaction.response.send_modal(modal)


class PlayerActionServerSelectView(discord.ui.View):
    """View for selecting server before player actions."""

    def __init__(self, cog, guild_id: int, action_type: str, title: str):
        super().__init__(timeout=60)
        self.cog = cog
        self.guild_id = guild_id
        self.action_type = action_type

        # Get available servers
        servers = RCONServerQueries.get_servers(guild_id, active_only=True)

        if not servers:
            return

        # Build server options
        options = []
        for server in servers[:25]:  # Discord max 25 options
            game = "🦖 Evrima" if server['game_type'] == 'the_isle_evrima' else "🦕 PoT"
            options.append(
                discord.SelectOption(
                    label=server['server_name'],
                    value=str(server['id']),
                    description=f"{game} - {server['host']}:{server['port']}"
                )
            )

        # Add "All Servers" option for kick, ban, console (not DM)
        if len(servers) > 1 and action_type in ['kick', 'ban', 'console']:
            options.insert(0, discord.SelectOption(
                label="All Servers",
                value="all",
                description=f"Execute on all configured servers",
                emoji="🌐"
            ))

        self.add_item(PlayerActionServerSelect(options, cog, guild_id, action_type, title))


class KickPlayerModalSimplified(discord.ui.Modal, title="Kick Player"):
    """Simplified kick modal (used with server selection view)."""

    player_id = discord.ui.TextInput(
        label="Player ID (Steam ID or Alderon ID)",
        placeholder="e.g., 76561198012345678 or 123-456-789",
        required=True,
        max_length=50
    )

    reason = discord.ui.TextInput(
        label="Reason",
        placeholder="Reason for kicking this player",
        required=False,
        default="Kicked by admin",
        style=discord.TextStyle.paragraph,
        max_length=200
    )

    def __init__(self, cog, servers: list[dict]):
        super().__init__()
        self.cog = cog
        self.servers = servers

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        try:
            results = await rcon_manager.execute_on_servers(
                self.servers, 'kick', self.player_id.value, self.reason.value
            )

            embed = self.cog._build_results_embed("Kick Results", results, self.servers)

            # Add player info
            embed.insert_field_at(
                0,
                name="Player Kicked",
                value=f"**ID:** {self.player_id.value}\n**Reason:** {self.reason.value}",
                inline=False
            )

            # Log command
            for server_id, response in results.items():
                RCONCommandLogQueries.log_command(
                    guild_id=interaction.guild_id,
                    command_type='kick',
                    target_player_id=self.player_id.value,
                    executed_by_id=interaction.user.id,
                    success=response.success,
                    server_id=server_id,
                    command_data={'reason': self.reason.value},
                    response_message=response.message
                )

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Error kicking player: {e}", exc_info=True)
            await interaction.followup.send(f"An error occurred: {e}", ephemeral=True)


class DMPlayerModalSimplified(discord.ui.Modal, title="DM Player In-Game"):
    """Simplified DM modal (used with server selection view)."""

    player_id = discord.ui.TextInput(
        label="Player ID (Steam ID or Alderon ID)",
        placeholder="e.g., 76561198012345678 or 123-456-789",
        required=True,
        max_length=50
    )

    message = discord.ui.TextInput(
        label="Message",
        placeholder="Your message to the player...",
        required=True,
        style=discord.TextStyle.paragraph,
        max_length=500
    )

    def __init__(self, cog, servers: list[dict]):
        super().__init__()
        self.cog = cog
        self.servers = servers

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        try:
            # Determine sender's role for the message
            user = interaction.user
            if user.id == interaction.guild.owner_id:
                sender_role = "Owner"
            elif user.guild_permissions.administrator:
                sender_role = "Head Admin"
            else:
                # Check highest role name
                highest_role = None
                for role in sorted(user.roles, key=lambda r: r.position, reverse=True):
                    if role.name != "@everyone":
                        highest_role = role.name
                        break
                sender_role = highest_role or "Admin"

            # Format the message with context (using first server's name)
            server_name = self.servers[0]['server_name']
            discord_name = user.name  # Use actual username

            formatted_message = (
                f"[PRIVATE DM from {sender_role}]\n"
                f"\n"  # RCON symbol appears on the blank line after this
                f"\n"
                f"Server: {server_name}\n"
                f"From: {discord_name}\n"
                f"{self.message.value}"
            )

            # Execute DM with formatted message
            results = await rcon_manager.execute_on_servers(
                self.servers, 'dm', self.player_id.value, formatted_message
            )

            # Create embed matching /rcon dm format
            embed = discord.Embed(
                title="✉️ Private DM Sent",
                color=discord.Color.blue()
            )
            embed.add_field(name="Server", value=server_name, inline=True)
            embed.add_field(name="Player ID", value=f"`{self.player_id.value}`", inline=True)
            embed.add_field(name="Sent by", value=f"{sender_role} ({discord_name})", inline=False)
            embed.add_field(name="Message", value=f"```{self.message.value}```", inline=False)

            # Log command
            for server_id, response in results.items():
                RCONCommandLogQueries.log_command(
                    guild_id=interaction.guild_id,
                    command_type='dm',
                    target_player_id=self.player_id.value,
                    executed_by_id=interaction.user.id,
                    success=response.success,
                    server_id=server_id,
                    command_data={'message': self.message.value},
                    response_message=response.message
                )

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Error sending DM: {e}", exc_info=True)
            await interaction.followup.send(f"An error occurred: {e}", ephemeral=True)


class ConsoleCommandModalSimplified(discord.ui.Modal, title="Raw Console Command"):
    """Simplified console command modal (used with server selection view)."""

    command = discord.ui.TextInput(
        label="Console Command",
        placeholder="Enter raw RCON command (e.g., /save, /help)",
        required=True,
        max_length=500
    )

    def __init__(self, cog, servers: list[dict]):
        super().__init__()
        self.cog = cog
        self.servers = servers

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        try:
            results = await rcon_manager.execute_on_servers(
                self.servers, 'console', self.command.value
            )

            embed = self.cog._build_results_embed("Console Command Results", results, self.servers)

            # Add command info
            embed.insert_field_at(
                0,
                name="Command Executed",
                value=f"```{self.command.value}```",
                inline=False
            )

            # Log command
            for server_id, response in results.items():
                RCONCommandLogQueries.log_command(
                    guild_id=interaction.guild_id,
                    command_type='console',
                    executed_by_id=interaction.user.id,
                    success=response.success,
                    server_id=server_id,
                    command_data={'command': self.command.value},
                    response_message=response.message
                )

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Error executing console command: {e}", exc_info=True)
            await interaction.followup.send(f"An error occurred: {e}", ephemeral=True)


class WhitelistAddModal(discord.ui.Modal, title="Add Players to Whitelist"):
    """Modal for adding players to whitelist (The Isle Evrima only)."""

    player_ids = discord.ui.TextInput(
        label="Player IDs (comma-separated Steam IDs)",
        placeholder="e.g., 76561198012345678,76561198087654321",
        required=True,
        style=discord.TextStyle.paragraph,
        max_length=500
    )

    def __init__(self, cog, servers: list[dict]):
        super().__init__()
        self.cog = cog
        self.servers = servers

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        try:
            # Parse player IDs
            ids = [pid.strip() for pid in self.player_ids.value.split(',') if pid.strip()]

            if not ids:
                await interaction.followup.send("❌ No valid player IDs provided.", ephemeral=True)
                return

            results = await rcon_manager.execute_on_servers(
                self.servers, 'whitelist_add', ','.join(ids)
            )

            embed = self.cog._build_results_embed("Whitelist Add Results", results, self.servers)

            # Add player info
            embed.insert_field_at(
                0,
                name="Players Added",
                value=f"**{len(ids)}** player(s): {', '.join(ids[:5])}{'...' if len(ids) > 5 else ''}",
                inline=False
            )

            # Log command
            for server_id, response in results.items():
                RCONCommandLogQueries.log_command(
                    guild_id=interaction.guild_id,
                    command_type='whitelist_add',
                    executed_by_id=interaction.user.id,
                    success=response.success,
                    server_id=server_id,
                    command_data={'player_ids': ids},
                    response_message=response.message
                )

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Error adding to whitelist: {e}", exc_info=True)
            await interaction.followup.send(f"An error occurred: {e}", ephemeral=True)


class WhitelistRemoveModal(discord.ui.Modal, title="Remove Players from Whitelist"):
    """Modal for removing players from whitelist (The Isle Evrima only)."""

    player_ids = discord.ui.TextInput(
        label="Player IDs (comma-separated Steam IDs)",
        placeholder="e.g., 76561198012345678,76561198087654321",
        required=True,
        style=discord.TextStyle.paragraph,
        max_length=500
    )

    def __init__(self, cog, servers: list[dict]):
        super().__init__()
        self.cog = cog
        self.servers = servers

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        try:
            # Parse player IDs
            ids = [pid.strip() for pid in self.player_ids.value.split(',') if pid.strip()]

            if not ids:
                await interaction.followup.send("❌ No valid player IDs provided.", ephemeral=True)
                return

            results = await rcon_manager.execute_on_servers(
                self.servers, 'whitelist_remove', ','.join(ids)
            )

            embed = self.cog._build_results_embed("Whitelist Remove Results", results, self.servers)

            # Add player info
            embed.insert_field_at(
                0,
                name="Players Removed",
                value=f"**{len(ids)}** player(s): {', '.join(ids[:5])}{'...' if len(ids) > 5 else ''}",
                inline=False
            )

            # Log command
            for server_id, response in results.items():
                RCONCommandLogQueries.log_command(
                    guild_id=interaction.guild_id,
                    command_type='whitelist_remove',
                    executed_by_id=interaction.user.id,
                    success=response.success,
                    server_id=server_id,
                    command_data={'player_ids': ids},
                    response_message=response.message
                )

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Error removing from whitelist: {e}", exc_info=True)
            await interaction.followup.send(f"An error occurred: {e}", ephemeral=True)


class DMPlayerModal(discord.ui.Modal, title="DM Player In-Game"):
    """Modal for sending direct messages to players."""

    player_id = discord.ui.TextInput(
        label="Player ID (Steam ID or Alderon ID)",
        placeholder="e.g., 76561198012345678 or 123-456-789",
        required=True,
        max_length=50
    )

    message = discord.ui.TextInput(
        label="Message",
        placeholder="Your message to the player...",
        required=True,
        style=discord.TextStyle.paragraph,
        max_length=500
    )

    server = discord.ui.TextInput(
        label="Server Name",
        placeholder="Which server is the player on?",
        required=True,
        max_length=100
    )

    def __init__(self, cog):
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        try:
            servers = self.cog._get_target_servers(interaction.guild_id, self.server.value)
            if not servers:
                await interaction.followup.send(
                    f"Server `{self.server.value}` not found.",
                    ephemeral=True
                )
                return

            results = await rcon_manager.execute_on_servers(
                servers, 'dm', self.player_id.value, self.message.value
            )

            embed = self.cog._build_results_embed("DM Results", results, servers)

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Error sending DM: {e}", exc_info=True)
            await interaction.followup.send(f"An error occurred: {e}", ephemeral=True)


class ConsoleCommandModal(discord.ui.Modal, title="Raw Console Command"):
    """Modal for sending raw console commands."""

    command = discord.ui.TextInput(
        label="Console Command",
        placeholder="e.g., /save or /listplayers",
        required=True,
        style=discord.TextStyle.paragraph,
        max_length=500
    )

    server = discord.ui.TextInput(
        label="Server Name",
        placeholder="Which server to send command to?",
        required=True,
        max_length=100
    )

    def __init__(self, cog):
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        try:
            servers = self.cog._get_target_servers(interaction.guild_id, self.server.value)
            if not servers:
                await interaction.followup.send(
                    f"Server `{self.server.value}` not found.",
                    ephemeral=True
                )
                return

            results = await rcon_manager.execute_on_servers(
                servers, 'console', self.command.value
            )

            embed = self.cog._build_results_embed("Console Command Results", results, servers)

            # Add the command that was sent
            embed.insert_field_at(
                0,
                name="Command Sent",
                value=f"```{self.command.value}```",
                inline=False
            )

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Error sending console command: {e}", exc_info=True)
            await interaction.followup.send(f"An error occurred: {e}", ephemeral=True)


class RemoveCustomDinosModal(discord.ui.Modal, title="Remove Dinosaurs from List"):
    """Modal for removing dinosaurs from the selection."""

    remove_dinos = discord.ui.TextInput(
        label="Dinosaur Names to Remove",
        placeholder="AllowedClasses=Tyrannosaurus\nAllowedClasses=Stegosaurus\nor just:\nTyrannosaurus\nStegosaurus",
        required=True,
        style=discord.TextStyle.paragraph,
        max_length=500
    )

    def __init__(self, parent_view):
        super().__init__()
        self.parent_view = parent_view

    async def on_submit(self, interaction: discord.Interaction):
        try:
            # Parse input - support both "AllowedClasses=Name" and just "Name"
            lines = [line.strip() for line in self.remove_dinos.value.split('\n') if line.strip()]
            dinos_to_remove = []

            for line in lines:
                # Handle "AllowedClasses=DinoName" format
                if line.startswith("AllowedClasses="):
                    dino_name = line.split("=", 1)[1].strip()
                else:
                    # Handle plain "DinoName" format
                    dino_name = line.strip()

                # Validate name
                if dino_name:
                    dinos_to_remove.append(dino_name)

            if not dinos_to_remove:
                await interaction.response.send_message(
                    "❌ No valid dinosaur names found. Please enter at least one name.",
                    ephemeral=True
                )
                return

            # Remove from selected list and custom list
            removed = []
            for dino in dinos_to_remove:
                # Remove from selected dinos
                if dino in self.parent_view.selected_dinos:
                    self.parent_view.selected_dinos.remove(dino)
                    removed.append(dino)
                # Remove from custom dinos if it exists there
                if dino in self.parent_view.custom_dinos:
                    self.parent_view.custom_dinos.remove(dino)

            if removed:
                await interaction.response.send_message(
                    f"✅ Removed {len(removed)} dinosaur(s) from the list:\n```{chr(10).join(removed)}```\n"
                    f"They will be disabled when you click **Confirm & Apply**.",
                    ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    "ℹ️ None of the entered dinosaurs were in the selection.",
                    ephemeral=True
                )

        except Exception as e:
            logger.error(f"Error in RemoveCustomDinosModal: {e}", exc_info=True)
            await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)


class AddCustomDinosModal(discord.ui.Modal, title="Add Custom Dinosaurs"):
    """Modal for adding custom/future dinosaurs to the list."""

    custom_dinos = discord.ui.TextInput(
        label="Custom Dinosaur Names",
        placeholder="AllowedClasses=Astro\nAllowedClasses=NewDino\nor just:\nAstro\nNewDino",
        required=True,
        style=discord.TextStyle.paragraph,
        max_length=500
    )

    def __init__(self, parent_view):
        super().__init__()
        self.parent_view = parent_view

    async def on_submit(self, interaction: discord.Interaction):
        try:
            # Parse input - support both "AllowedClasses=Name" and just "Name"
            lines = [line.strip() for line in self.custom_dinos.value.split('\n') if line.strip()]
            new_dinos = []

            for line in lines:
                # Handle "AllowedClasses=DinoName" format
                if line.startswith("AllowedClasses="):
                    dino_name = line.split("=", 1)[1].strip()
                else:
                    # Handle plain "DinoName" format
                    dino_name = line.strip()

                # Validate name (alphanumeric only)
                if dino_name and dino_name.replace(" ", "").isalnum():
                    new_dinos.append(dino_name)

            if not new_dinos:
                await interaction.response.send_message(
                    "❌ No valid dinosaur names found. Please enter at least one name.",
                    ephemeral=True
                )
                return

            # Add to parent view's custom list
            added = []
            for dino in new_dinos:
                if dino not in self.parent_view.custom_dinos and dino not in self.parent_view.DINOSAURS:
                    self.parent_view.custom_dinos.append(dino)
                    # Auto-select custom dinos
                    if dino not in self.parent_view.selected_dinos:
                        self.parent_view.selected_dinos.append(dino)
                    added.append(dino)

            if added:
                await interaction.response.send_message(
                    f"✅ Added {len(added)} custom dinosaur(s):\n```{chr(10).join(added)}```\n"
                    f"These will be included when you click **Confirm & Apply**.",
                    ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    "ℹ️ All entered dinosaurs are already in the list.",
                    ephemeral=True
                )

        except Exception as e:
            logger.error(f"Error in AddCustomDinosModal: {e}", exc_info=True)
            await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)


class AllowClassesServerSelectView(discord.ui.View):
    """View for selecting servers before showing Allow Classes dino selection."""

    def __init__(self, cog, servers: list[dict], master_pool: list[str], pool_count: int):
        super().__init__(timeout=60)
        self.cog = cog
        self.servers = servers
        self.master_pool = master_pool
        self.pool_count = pool_count

        # Build server options
        options = [discord.SelectOption(label="All Servers", value="all", description="Apply to all Evrima servers", emoji="🌐")]
        for server in servers[:24]:  # Max 25 total options
            options.append(discord.SelectOption(
                label=server['server_name'],
                value=str(server['id']),
                description=f"{server['host']}:{server['port']}",
                emoji="🦖"
            ))

        self.server_select = discord.ui.Select(
            placeholder="Select server(s) to configure",
            options=options
        )
        self.server_select.callback = self.server_select_callback
        self.add_item(self.server_select)

    async def server_select_callback(self, interaction: discord.Interaction):
        """Handle server selection."""
        selected = self.server_select.values[0]
        guild_id = interaction.guild_id

        if selected == "all":
            target_servers = self.servers
            server_text = "**All Evrima servers**"
            # For "all servers", use empty disabled list (will apply same settings to all)
            current_disabled = []
        else:
            server_id = int(selected)
            server = next((s for s in self.servers if s['id'] == server_id), None)
            target_servers = [server]
            server_text = f"**{server['server_name']}**"
            # Load currently disabled dinos for this specific server
            current_disabled = self.cog._get_disabled_dinos(guild_id, server_id)

        # Build status message
        if current_disabled:
            status_msg = f"⚠️ Currently **{len(current_disabled)} dinosaurs disabled** (shown deselected in dropdown)."
        else:
            status_msg = f"✅ All {self.pool_count} dinosaurs are **pre-selected** by default."

        # Show dinosaur selection
        view = AllowDinosView(self.cog, target_servers, self.master_pool, current_disabled)
        await interaction.response.send_message(
            f"**Select The Isle Evrima Playable Dinosaurs**\n"
            f"🎯 Server: {server_text}\n"
            f"{status_msg}\n"
            f"🔽 Open the dropdown and **deselect** any you want to disable.\n"
            f"✔️ Click **Confirm & Apply** when ready to apply changes.",
            view=view,
            ephemeral=True
        )


class AllowDinosView(discord.ui.View):
    """View with dropdown for selecting playable dinosaurs."""

    # All available dinosaurs in The Isle Evrima (current as of Update 10)
    DINOSAURS = [
        "Ceratosaurus",
        "Deinosuchus",
        "Pteranodon",
        "Omniraptor",
        "Tyrannosaurus",
        "Troodon",
        "Gallimimus",
        "Beipiaosaurus",
        "Herrerasaurus",
        "Dilophosaurus",
        "Carnotaurus",
        "Allosaurus",
        "Triceratops",
        "Tenontosaurus",
        "Stegosaurus",
        "Pachycephalosaurus",
        "Maiasaura",
        "Hypsilophodon",
        "Dryosaurus",
        "Diabloceratops"
    ]

    def __init__(self, cog, servers: list[dict], master_pool: list[str], current_disabled: list[str]):
        super().__init__(timeout=300)  # 5 minute timeout
        self.cog = cog
        self.servers = servers
        # Use the master pool instead of hardcoded DINOSAURS
        self.master_pool = master_pool
        # Track currently disabled dinos
        self.current_disabled = current_disabled.copy()
        # Pre-select only enabled dinosaurs (exclude currently disabled ones)
        self.selected_dinos = [d for d in self.master_pool if d not in current_disabled]

        # Create select menu with enabled dinos pre-selected
        options = [
            discord.SelectOption(
                label=dino,
                value=dino,
                default=(dino not in current_disabled)  # Pre-select enabled, not disabled
            )
            for dino in self.master_pool
        ]

        # Dynamic placeholder based on current state
        if current_disabled:
            placeholder_text = f"{len(current_disabled)} disabled - toggle to change"
        else:
            placeholder_text = f"All {len(self.master_pool)} enabled - select ones to disable"

        self.dino_select = discord.ui.Select(
            placeholder=placeholder_text,
            min_values=1,
            max_values=len(self.master_pool),
            options=options
        )
        self.dino_select.callback = self.dino_select_callback
        self.add_item(self.dino_select)

    async def dino_select_callback(self, interaction: discord.Interaction):
        """Handle dinosaur selection."""
        self.selected_dinos = self.dino_select.values
        total_in_pool = len(self.master_pool)
        disabled_count = total_in_pool - len(self.selected_dinos)

        await interaction.response.send_message(
            f"✅ **{len(self.selected_dinos)} dinosaurs** will be playable.\n"
            f"❌ **{disabled_count} dinosaurs** will be disabled.\n"
            f"Click **Confirm & Apply** to update the server.",
            ephemeral=True
        )

    @discord.ui.button(label="Confirm & Apply", style=discord.ButtonStyle.green, row=0)
    async def confirm_button(self, interaction: discord.Interaction, _button: discord.ui.Button):
        """Confirm and apply dinosaur selection."""
        if not self.selected_dinos:
            await interaction.response.send_message(
                "❌ At least one dinosaur must be playable. Please select at least one.",
                ephemeral=True
            )
            return

        try:
            await interaction.response.defer(ephemeral=True)

            # Create comma-separated list with selected dinos
            dino_str = ','.join(self.selected_dinos)

            results = await rcon_manager.execute_on_servers(self.servers, 'update_playables', dino_str)
            embed = self.cog._build_results_embed("Update Playables Results", results, self.servers)

            # Show enabled and disabled dinosaurs
            disabled_dinos = [d for d in self.master_pool if d not in self.selected_dinos]
            total_enabled = len(self.selected_dinos)
            total_possible = len(self.master_pool)

            # Save disabled dinos to database
            guild_id = interaction.guild_id
            server_ids = [server['id'] for server in self.servers]

            if len(server_ids) == 1:
                # Single server
                self.cog._save_disabled_dinos(guild_id, server_ids[0], disabled_dinos)
            else:
                # Multiple servers (bulk update)
                self.cog._save_disabled_dinos_bulk(guild_id, server_ids, disabled_dinos)

            embed.insert_field_at(
                0,
                name=f"Playable Dinosaurs ({total_enabled}/{total_possible})",
                value=f"```\n{chr(10).join(self.selected_dinos)}\n```",
                inline=True
            )

            if disabled_dinos:
                embed.insert_field_at(
                    1,
                    name=f"Disabled ({len(disabled_dinos)})",
                    value=f"```\n{chr(10).join(disabled_dinos)}\n```",
                    inline=True
                )

            await interaction.followup.send(embed=embed, ephemeral=True)

            # Disable the view
            self.stop()

        except Exception as e:
            logger.error(f"Error in AllowDinosView confirm: {e}", exc_info=True)
            await interaction.followup.send(f"An error occurred: {e}", ephemeral=True)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.red, row=0)
    async def cancel_button(self, interaction: discord.Interaction, _button: discord.ui.Button):
        """Cancel the operation."""
        await interaction.response.send_message("❌ Cancelled. No changes were made.", ephemeral=True)
        self.stop()


class AddOrRemoveClassServerSelectView(discord.ui.View):
    """View for selecting servers before managing dinosaur pool."""

    def __init__(self, cog, servers: list[dict], guild_id: int, current_pool: list[str]):
        super().__init__(timeout=60)
        self.cog = cog
        self.servers = servers
        self.guild_id = guild_id
        self.current_pool = current_pool

        # Build server options
        options = [discord.SelectOption(label="All Servers", value="all", description="Apply changes to all Evrima servers", emoji="🌐")]
        for server in servers[:24]:  # Max 25 total options
            options.append(discord.SelectOption(
                label=server['server_name'],
                value=str(server['id']),
                description=f"{server['host']}:{server['port']}",
                emoji="🦖"
            ))

        self.server_select = discord.ui.Select(
            placeholder="Select server(s) for pool management",
            options=options
        )
        self.server_select.callback = self.server_select_callback
        self.add_item(self.server_select)

    async def server_select_callback(self, interaction: discord.Interaction):
        """Handle server selection."""
        selected = self.server_select.values[0]

        if selected == "all":
            target_servers = self.servers
            server_text = "**All Evrima servers**"
        else:
            server_id = int(selected)
            server = next((s for s in self.servers if s['id'] == server_id), None)
            target_servers = [server]
            server_text = f"**{server['server_name']}**"

        # Show pool management view
        view = AddOrRemoveClassView(self.cog, self.guild_id, self.current_pool, target_servers)
        embed = discord.Embed(
            title="🔧 Manage Master Dinosaur Pool",
            description=f"🎯 Server: {server_text}\n\n"
                       f"**Current pool contains {len(self.current_pool)} dinosaurs.**\n\n"
                       "Use the buttons below to add or remove dinosaurs from the master pool.\n"
                       "This affects what appears in the **Allow Classes** dropdown.\n"
                       "**Changes will be applied to the server immediately.**",
            color=discord.Color.gold()
        )
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


class AddOrRemoveClassView(discord.ui.View):
    """View for adding or removing dinosaurs from the master pool."""

    def __init__(self, cog, guild_id: int, current_pool: list[str], servers: list[dict]):
        super().__init__(timeout=300)
        self.cog = cog
        self.guild_id = guild_id
        self.current_pool = current_pool.copy()
        self.servers = servers

    @discord.ui.button(label="Add Dinosaur", style=discord.ButtonStyle.green, row=0)
    async def add_button(self, interaction: discord.Interaction, _button: discord.ui.Button):
        """Open modal to add dinosaur to pool."""
        modal = AddDinoToPoolModal(self)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Remove Dinosaur", style=discord.ButtonStyle.red, row=0)
    async def remove_button(self, interaction: discord.Interaction, _button: discord.ui.Button):
        """Open modal to remove dinosaur from pool."""
        if not self.current_pool:
            await interaction.response.send_message(
                "❌ Cannot remove dinosaurs - pool is already empty!",
                ephemeral=True
            )
            return

        modal = RemoveDinoFromPoolModal(self)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="View Current Pool", style=discord.ButtonStyle.blurple, row=0)
    async def view_button(self, interaction: discord.Interaction, _button: discord.ui.Button):
        """Show current dinosaur pool."""
        if not self.current_pool:
            await interaction.response.send_message(
                "❌ No dinosaurs in the pool!",
                ephemeral=True
            )
            return

        embed = discord.Embed(
            title="🦖 Master Dinosaur Pool",
            description=f"**{len(self.current_pool)} dinosaurs** currently in the pool:",
            color=discord.Color.blue()
        )
        embed.add_field(
            name="Available Dinosaurs",
            value=f"```{chr(10).join(sorted(self.current_pool))}```",
            inline=False
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="Done", style=discord.ButtonStyle.grey, row=0)
    async def done_button(self, interaction: discord.Interaction, _button: discord.ui.Button):
        """Finish managing the pool."""
        await interaction.response.send_message(
            f"✅ Master pool updated! Now contains **{len(self.current_pool)} dinosaurs**.",
            ephemeral=True
        )
        self.stop()


class AddDinoToPoolModal(discord.ui.Modal, title="Add Dinosaur to Pool"):
    """Modal for adding a dinosaur to the master pool."""

    dino_name = discord.ui.TextInput(
        label="Dinosaur Name",
        placeholder="Tyrannosaurus",
        required=True,
        max_length=50
    )

    def __init__(self, view: AddOrRemoveClassView):
        super().__init__()
        self.view = view

    async def on_submit(self, interaction: discord.Interaction):
        dino = self.dino_name.value.strip()

        if dino in self.view.current_pool:
            await interaction.response.send_message(
                f"❌ **{dino}** is already in the pool!",
                ephemeral=True
            )
            return

        try:
            # Defer since we're sending RCON commands
            await interaction.response.defer(ephemeral=True)

            # Add to pool
            self.view.current_pool.append(dino)

            # Save to database
            self.view.cog._save_dino_pool(self.view.guild_id, self.view.current_pool)

            # Use servers from view (already filtered to Evrima)
            evrima_servers = self.view.servers

            # Send RCON command with updated pool
            dino_str = ','.join(self.view.current_pool)
            results = await rcon_manager.execute_on_servers(evrima_servers, 'update_playables', dino_str)

            # Build results embed
            embed = self.view.cog._build_results_embed("Add Dinosaur to Pool", results, evrima_servers)
            embed.insert_field_at(
                0,
                name="Pool Updated",
                value=f"✅ Added **{dino}** to the master pool!\n"
                      f"Pool now contains **{len(self.view.current_pool)} dinosaurs**.\n"
                      f"All {len(self.view.current_pool)} dinosaurs have been enabled in-game.",
                inline=False
            )

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Error in AddDinoToPoolModal: {e}", exc_info=True)
            await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)


class RemoveDinoFromPoolModal(discord.ui.Modal, title="Remove Dinosaur from Pool"):
    """Modal for removing a dinosaur from the master pool."""

    dino_name = discord.ui.TextInput(
        label="Dinosaur Name",
        placeholder="Tyrannosaurus",
        required=True,
        max_length=50
    )

    def __init__(self, view: AddOrRemoveClassView):
        super().__init__()
        self.view = view

    async def on_submit(self, interaction: discord.Interaction):
        dino = self.dino_name.value.strip()

        if dino not in self.view.current_pool:
            await interaction.response.send_message(
                f"❌ **{dino}** is not in the pool!",
                ephemeral=True
            )
            return

        if len(self.view.current_pool) <= 1:
            await interaction.response.send_message(
                f"❌ Cannot remove **{dino}** - at least one dinosaur must remain in the pool!",
                ephemeral=True
            )
            return

        try:
            # Defer since we're sending RCON commands
            await interaction.response.defer(ephemeral=True)

            # Remove from pool
            self.view.current_pool.remove(dino)

            # Save to database
            self.view.cog._save_dino_pool(self.view.guild_id, self.view.current_pool)

            # Use servers from view (already filtered to Evrima)
            evrima_servers = self.view.servers

            # Send RCON command with updated pool
            dino_str = ','.join(self.view.current_pool)
            results = await rcon_manager.execute_on_servers(evrima_servers, 'update_playables', dino_str)

            # Build results embed
            embed = self.view.cog._build_results_embed("Remove Dinosaur from Pool", results, evrima_servers)
            embed.insert_field_at(
                0,
                name="Pool Updated",
                value=f"✅ Removed **{dino}** from the master pool!\n"
                      f"Pool now contains **{len(self.view.current_pool)} dinosaurs**.\n"
                      f"**{dino}** has been disabled in-game.\n"
                      f"Remaining {len(self.view.current_pool)} dinosaurs are enabled.",
                inline=False
            )

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Error in RemoveDinoFromPoolModal: {e}", exc_info=True)
            await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)


class DisallowAIView(discord.ui.View):
    """View with dropdown for selecting AI creatures to disable (with state persistence)."""

    # All available AI creatures in The Isle Evrima
    AI_CREATURES = [
        "Compsognathus",
        "Pterodactylus",
        "Boar",
        "Deer",
        "Goat",
        "Seaturtle",
        "Fish",
        "Crab"
    ]

    def __init__(self, cog, servers: list[dict], current_disallowed: list[str]):
        super().__init__(timeout=300)  # 5 minute timeout
        self.cog = cog
        self.servers = servers
        # Pre-select currently disallowed AI
        self.current_disallowed = current_disallowed.copy()
        self.selected_ai = current_disallowed.copy()

        # Create select menu with currently disallowed AI pre-selected
        options = [
            discord.SelectOption(
                label=ai,
                value=ai,
                default=(ai in current_disallowed)
            )
            for ai in self.AI_CREATURES
        ]

        placeholder_text = (
            f"{len(current_disallowed)} AI disabled - toggle to change"
            if current_disallowed
            else "Select AI creatures to disable"
        )

        self.ai_select = discord.ui.Select(
            placeholder=placeholder_text,
            min_values=0,
            max_values=len(self.AI_CREATURES),
            options=options
        )
        self.ai_select.callback = self.ai_select_callback
        self.add_item(self.ai_select)

    async def ai_select_callback(self, interaction: discord.Interaction):
        """Handle AI selection."""
        self.selected_ai = self.ai_select.values

        # Log selection for debugging
        logger.info(f"AI selection callback - selected: {self.selected_ai}, count: {len(self.selected_ai)}")

        # Calculate what's changing
        newly_disabled = [ai for ai in self.selected_ai if ai not in self.current_disallowed]
        newly_enabled = [ai for ai in self.current_disallowed if ai not in self.selected_ai]

        message_parts = []

        if newly_disabled:
            message_parts.append(f"🔴 **Will disable:** {', '.join(sorted(newly_disabled))}")
        if newly_enabled:
            message_parts.append(f"🟢 **Will enable:** {', '.join(sorted(newly_enabled))}")

        if not message_parts:
            message_parts.append("ℹ️ No changes - selection matches current state.")

        message_parts.append(f"\n**Total disabled:** {len(self.selected_ai)}/{len(self.AI_CREATURES)}")
        message_parts.append("Click **Confirm & Apply** to save changes.")

        await interaction.response.send_message(
            "\n".join(message_parts),
            ephemeral=True
        )

    @discord.ui.button(label="Confirm & Apply", style=discord.ButtonStyle.green, row=0)
    async def confirm_button(self, interaction: discord.Interaction, _button: discord.ui.Button):
        """Confirm and apply AI restrictions."""
        try:
            await interaction.response.defer(ephemeral=True)

            # Send RCON command to update AI restrictions
            if self.selected_ai:
                # Disable selected AI
                results = await rcon_manager.execute_on_servers(
                    self.servers,
                    'disable_ai_classes',
                    ','.join(self.selected_ai)
                )
            else:
                # Clear all restrictions (empty list = enable all AI)
                results = await rcon_manager.execute_on_servers(
                    self.servers,
                    'disable_ai_classes',
                    ''  # Empty string clears restrictions
                )

            # Save to database
            guild_id = interaction.guild_id
            server_ids = [server['id'] for server in self.servers]

            if len(server_ids) == 1:
                # Single server
                self.cog._save_ai_restrictions(guild_id, server_ids[0], self.selected_ai)
            else:
                # Multiple servers (bulk update)
                self.cog._save_ai_restrictions_bulk(guild_id, server_ids, self.selected_ai)

            embed = self.cog._build_results_embed("Disallow AI Results", results, self.servers)

            # Show what changed
            if self.selected_ai:
                # Sort for consistent display
                disabled_list = sorted(self.selected_ai)
                enabled_ai = sorted([ai for ai in self.AI_CREATURES if ai not in self.selected_ai])

                # Log for debugging
                logger.info(f"Disabled AI count: {len(disabled_list)}, List: {disabled_list}")

                embed.insert_field_at(
                    0,
                    name=f"❌ Disabled AI ({len(disabled_list)})",
                    value=f"```\n{chr(10).join(disabled_list)}\n```",
                    inline=True
                )

                if enabled_ai:
                    embed.insert_field_at(
                        1,
                        name=f"✅ Enabled AI ({len(enabled_ai)})",
                        value=f"```\n{chr(10).join(enabled_ai)}\n```",
                        inline=True
                    )
            else:
                embed.insert_field_at(
                    0,
                    name="✅ All AI Enabled",
                    value="No AI restrictions active",
                    inline=False
                )

            await interaction.followup.send(embed=embed, ephemeral=True)
            self.stop()

        except Exception as e:
            logger.error(f"Error in DisallowAIView confirm: {e}", exc_info=True)
            await interaction.followup.send(f"An error occurred: {e}", ephemeral=True)

    @discord.ui.button(label="Clear All Restrictions", style=discord.ButtonStyle.blurple, row=0)
    async def clear_button(self, interaction: discord.Interaction, _button: discord.ui.Button):
        """Clear all AI restrictions (enable all AI)."""
        try:
            await interaction.response.defer(ephemeral=True)

            # Send empty string to clear all restrictions
            results = await rcon_manager.execute_on_servers(
                self.servers,
                'disable_ai_classes',
                ''  # Empty string clears restrictions
            )

            # Save to database (empty list = clear all)
            guild_id = interaction.guild_id
            server_ids = [server['id'] for server in self.servers]

            if len(server_ids) == 1:
                # Single server
                self.cog._save_ai_restrictions(guild_id, server_ids[0], [])
            else:
                # Multiple servers (bulk update)
                self.cog._save_ai_restrictions_bulk(guild_id, server_ids, [])

            embed = self.cog._build_results_embed("Clear AI Restrictions", results, self.servers)
            embed.insert_field_at(
                0,
                name="✅ All AI Enabled",
                value=f"Cleared all AI restrictions.\nAll {len(self.AI_CREATURES)} AI creatures are now enabled.",
                inline=False
            )

            await interaction.followup.send(embed=embed, ephemeral=True)
            self.stop()

        except Exception as e:
            logger.error(f"Error clearing AI restrictions: {e}", exc_info=True)
            await interaction.followup.send(f"An error occurred: {e}", ephemeral=True)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.red, row=0)
    async def cancel_button(self, interaction: discord.Interaction, _button: discord.ui.Button):
        """Cancel the operation."""
        await interaction.response.send_message("❌ Cancelled. No changes were made.", ephemeral=True)
        self.stop()


class DisallowAIServerSelectView(discord.ui.View):
    """View for selecting servers before disallowing AI creatures."""

    def __init__(self, cog, servers: list[dict]):
        super().__init__(timeout=60)
        self.cog = cog
        self.servers = servers

        # Build server options
        options = [discord.SelectOption(
            label="All Servers",
            value="all",
            description="Apply AI restrictions to all Evrima servers",
            emoji="🌐"
        )]
        for server in servers[:24]:  # Max 25 total options
            options.append(discord.SelectOption(
                label=server['server_name'],
                value=str(server['id']),
                description=f"{server['host']}:{server['port']}",
                emoji="🦖"
            ))

        self.server_select = discord.ui.Select(
            placeholder="Select server(s) for AI restrictions",
            options=options
        )
        self.server_select.callback = self.server_select_callback
        self.add_item(self.server_select)

    async def server_select_callback(self, interaction: discord.Interaction):
        """Handle server selection."""
        selected = self.server_select.values[0]
        guild_id = interaction.guild_id

        if selected == "all":
            target_servers = self.servers
            server_text = "**All Evrima servers**"
            # For "all servers", use the first server's state from database
            if self.servers:
                first_server_id = self.servers[0]['id']
                current_disallowed = self.cog._get_ai_restrictions(guild_id, first_server_id)
            else:
                current_disallowed = []
        else:
            server_id = int(selected)
            server = next((s for s in self.servers if s['id'] == server_id), None)
            target_servers = [server]
            server_text = f"**{server['server_name']}**"
            # Load current state for this specific server from database
            current_disallowed = self.cog._get_ai_restrictions(guild_id, server_id)

        # Show AI selection view with current state
        view = DisallowAIView(self.cog, target_servers, current_disallowed)

        status_text = (
            f"Currently **{len(current_disallowed)} AI disabled**"
            if current_disallowed
            else "All AI currently **enabled**"
        )

        await interaction.response.send_message(
            f"**Disallow AI Creatures (The Isle Evrima)**\n"
            f"🎯 Server: {server_text}\n"
            f"📊 Status: {status_text}\n\n"
            f"🔽 Select/deselect AI creatures to toggle restrictions.\n"
            f"✔️ Click **Confirm & Apply** to save changes.\n"
            f"🔵 Click **Clear All Restrictions** to enable all AI.",
            view=view,
            ephemeral=True
        )


class AIDensityModal(discord.ui.Modal, title="Set AI Spawn Density"):
    """Modal for setting AI spawn density."""

    density = discord.ui.TextInput(
        label="AI Density Value",
        placeholder="Enter density value (e.g., 1.0 for default, 0.5 for half, 2.0 for double)",
        required=True,
        max_length=10
    )

    def __init__(self, cog, servers: list[dict]):
        super().__init__()
        self.cog = cog
        self.servers = servers

    async def on_submit(self, interaction: discord.Interaction):
        """Handle density submission."""
        try:
            # Validate density value
            try:
                density_value = float(self.density.value)
                if density_value < 0:
                    await interaction.response.send_message(
                        "❌ Density value must be positive!",
                        ephemeral=True
                    )
                    return
            except ValueError:
                await interaction.response.send_message(
                    "❌ Invalid density value! Please enter a number (e.g., 1.0, 0.5, 2.0).",
                    ephemeral=True
                )
                return

            await interaction.response.defer(ephemeral=True)

            # Send RCON command to set AI density
            results = await rcon_manager.execute_on_servers(
                self.servers,
                'set_ai_density',
                density_value
            )

            embed = self.cog._build_results_embed("AI Density Results", results, self.servers)
            embed.insert_field_at(
                0,
                name="Density Value",
                value=f"```AI Spawn Density: {density_value}```\n"
                      f"1.0 = Default\n"
                      f"< 1.0 = Less AI spawns\n"
                      f"> 1.0 = More AI spawns",
                inline=False
            )

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Error in AIDensityModal: {e}", exc_info=True)
            await interaction.followup.send(f"An error occurred: {e}", ephemeral=True)


class AIDensityServerSelectView(discord.ui.View):
    """View for selecting servers before setting AI density."""

    def __init__(self, cog, servers: list[dict]):
        super().__init__(timeout=60)
        self.cog = cog
        self.servers = servers

        # Build server options
        options = [discord.SelectOption(
            label="All Servers",
            value="all",
            description="Apply AI density to all Evrima servers",
            emoji="🌐"
        )]
        for server in servers[:24]:  # Max 25 total options
            options.append(discord.SelectOption(
                label=server['server_name'],
                value=str(server['id']),
                description=f"{server['host']}:{server['port']}",
                emoji="🦖"
            ))

        self.server_select = discord.ui.Select(
            placeholder="Select server(s) for AI density",
            options=options
        )
        self.server_select.callback = self.server_select_callback
        self.add_item(self.server_select)

    async def server_select_callback(self, interaction: discord.Interaction):
        """Handle server selection."""
        selected = self.server_select.values[0]

        if selected == "all":
            target_servers = self.servers
        else:
            server_id = int(selected)
            server = next((s for s in self.servers if s['id'] == server_id), None)
            target_servers = [server]

        # Show density modal
        modal = AIDensityModal(self.cog, target_servers)
        await interaction.response.send_modal(modal)


class ManageWhitelistView(discord.ui.View):
    """View for managing whitelist with add and remove options."""

    def __init__(self, cog, guild_id: int):
        super().__init__(timeout=60)
        self.cog = cog
        self.guild_id = guild_id

    @discord.ui.button(label="Add to Whitelist", style=discord.ButtonStyle.green, emoji="➕", row=0)
    async def add_button(self, interaction: discord.Interaction, _button: discord.ui.Button):
        """Show server selection for whitelist add or direct modal if 1 Evrima server."""
        # Get Evrima servers only
        all_servers = RCONServerQueries.get_servers(self.guild_id, active_only=True)
        evrima_servers = [s for s in all_servers if s.get('game_type') == 'the_isle_evrima']

        if not evrima_servers:
            await interaction.response.send_message(
                "No Evrima servers configured. This command only works with The Isle Evrima.",
                ephemeral=True
            )
            return

        # If only 1 Evrima server, go straight to modal
        if len(evrima_servers) == 1:
            modal = WhitelistAddModal(self.cog, evrima_servers)
            await interaction.response.send_modal(modal)
        else:
            # Multiple servers - show selection
            view = PlayerActionServerSelectView(self.cog, self.guild_id, "whitelistadd", "➕ Add to Whitelist")
            embed = discord.Embed(
                title="➕ Add Players to Whitelist",
                description="Select which server to add players to whitelist (The Isle Evrima only):",
                color=discord.Color.green()
            )
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @discord.ui.button(label="Remove from Whitelist", style=discord.ButtonStyle.red, emoji="➖", row=0)
    async def remove_button(self, interaction: discord.Interaction, _button: discord.ui.Button):
        """Show server selection for whitelist remove or direct modal if 1 Evrima server."""
        # Get Evrima servers only
        all_servers = RCONServerQueries.get_servers(self.guild_id, active_only=True)
        evrima_servers = [s for s in all_servers if s.get('game_type') == 'the_isle_evrima']

        if not evrima_servers:
            await interaction.response.send_message(
                "No Evrima servers configured. This command only works with The Isle Evrima.",
                ephemeral=True
            )
            return

        # If only 1 Evrima server, go straight to modal
        if len(evrima_servers) == 1:
            modal = WhitelistRemoveModal(self.cog, evrima_servers)
            await interaction.response.send_modal(modal)
        else:
            # Multiple servers - show selection
            view = PlayerActionServerSelectView(self.cog, self.guild_id, "whitelistremove", "➖ Remove from Whitelist")
            embed = discord.Embed(
                title="➖ Remove Players from Whitelist",
                description="Select which server to remove players from whitelist (The Isle Evrima only):",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


class WhitelistAddModal(discord.ui.Modal, title="Add Players to Whitelist"):
    """Modal for adding players to whitelist."""

    player_ids = discord.ui.TextInput(
        label="Steam IDs (one per line)",
        placeholder="76561198012345678\n76561198087654321",
        required=True,
        style=discord.TextStyle.paragraph,
        max_length=2000
    )

    def __init__(self, cog, servers: list[dict]):
        super().__init__()
        self.cog = cog
        self.servers = servers

    async def on_submit(self, interaction: discord.Interaction):
        try:
            # Convert newline-separated to comma-separated
            lines = [line.strip() for line in self.player_ids.value.split('\n') if line.strip()]
            ids_str = ','.join(lines)

            await interaction.response.defer(ephemeral=True)

            results = await rcon_manager.execute_on_servers(self.servers, 'add_whitelist', ids_str)
            embed = self.cog._build_results_embed("Whitelist Add Results", results, self.servers)

            embed.insert_field_at(
                0,
                name="Players Added",
                value=f"```{chr(10).join(lines[:20])}{'...' if len(lines) > 20 else ''}```",
                inline=False
            )

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Error in WhitelistAddModal: {e}", exc_info=True)
            await interaction.followup.send(f"An error occurred: {e}", ephemeral=True)


class WhitelistRemoveModal(discord.ui.Modal, title="Remove Players from Whitelist"):
    """Modal for removing players from whitelist."""

    player_ids = discord.ui.TextInput(
        label="Steam IDs (one per line)",
        placeholder="76561198012345678\n76561198087654321",
        required=True,
        style=discord.TextStyle.paragraph,
        max_length=2000
    )

    def __init__(self, cog, servers: list[dict]):
        super().__init__()
        self.cog = cog
        self.servers = servers

    async def on_submit(self, interaction: discord.Interaction):
        try:
            # Convert newline-separated to comma-separated
            lines = [line.strip() for line in self.player_ids.value.split('\n') if line.strip()]
            ids_str = ','.join(lines)

            await interaction.response.defer(ephemeral=True)

            results = await rcon_manager.execute_on_servers(self.servers, 'remove_whitelist', ids_str)
            embed = self.cog._build_results_embed("Whitelist Remove Results", results, self.servers)

            embed.insert_field_at(
                0,
                name="Players Removed",
                value=f"```{chr(10).join(lines[:20])}{'...' if len(lines) > 20 else ''}```",
                inline=False
            )

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Error in WhitelistRemoveModal: {e}", exc_info=True)
            await interaction.followup.send(f"An error occurred: {e}", ephemeral=True)


class DisableAIModal(discord.ui.Modal, title="Disable AI Classes"):
    """Modal for disabling AI classes."""

    dino_list = discord.ui.TextInput(
        label="Dinosaur Names to Disable (one per line)",
        placeholder="Tyrannosaurus\nVelociraptor",
        required=True,
        style=discord.TextStyle.paragraph,
        max_length=2000
    )

    def __init__(self, cog, servers: list[dict]):
        super().__init__()
        self.cog = cog
        self.servers = servers

    async def on_submit(self, interaction: discord.Interaction):
        try:
            # Convert newline-separated to comma-separated
            lines = [line.strip() for line in self.dino_list.value.split('\n') if line.strip()]
            dino_str = ','.join(lines)

            await interaction.response.defer(ephemeral=True)

            results = await rcon_manager.execute_on_servers(self.servers, 'disable_ai_classes', dino_str)
            embed = self.cog._build_results_embed("Disable AI Classes Results", results, self.servers)

            embed.insert_field_at(
                0,
                name="AI Classes Disabled",
                value=f"```{chr(10).join(lines[:20])}{'...' if len(lines) > 20 else ''}```",
                inline=False
            )

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Error in DisableAIModal: {e}", exc_info=True)
            await interaction.followup.send(f"An error occurred: {e}", ephemeral=True)


class WipeCorpsesConfirmModal(discord.ui.Modal, title="Confirm Wipe Corpses"):
    """Confirmation modal for wiping corpses."""

    confirmation = discord.ui.TextInput(
        label='Type "CONFIRM" to wipe all corpses',
        placeholder="CONFIRM",
        required=True,
        max_length=10
    )

    def __init__(self, cog, servers: list[dict]):
        super().__init__()
        self.cog = cog
        self.servers = servers

    async def on_submit(self, interaction: discord.Interaction):
        try:
            if self.confirmation.value.upper() != "CONFIRM":
                await interaction.response.send_message(
                    "Wipe cancelled. You must type `CONFIRM` to proceed.",
                    ephemeral=True
                )
                return

            await interaction.response.defer(ephemeral=True)

            results = await rcon_manager.execute_on_servers(self.servers, 'wipe_corpses')
            embed = self.cog._build_results_embed("Wipe Corpses Results", results, self.servers)

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Error in WipeCorpsesConfirmModal: {e}", exc_info=True)
            await interaction.followup.send(f"An error occurred: {e}", ephemeral=True)


class BanPlayerModal(discord.ui.Modal, title="Ban Player"):
    """Modal for banning a player with reason."""

    player_id = discord.ui.TextInput(
        label="Steam ID or Alderon ID",
        placeholder="76561198012345678 or XXX-XXX-XXX",
        required=True,
        max_length=50
    )

    reason = discord.ui.TextInput(
        label="Reason for Ban",
        placeholder="Explain why this player is being banned",
        required=False,
        style=discord.TextStyle.paragraph,
        default="Banned by admin",
        max_length=500
    )

    confirmation = discord.ui.TextInput(
        label='Type "BAN" to confirm',
        placeholder="BAN",
        required=True,
        max_length=10
    )

    def __init__(self, cog, servers: list[dict]):
        super().__init__()
        self.cog = cog
        self.servers = servers

    async def on_submit(self, interaction: discord.Interaction):
        try:
            if self.confirmation.value.upper() != "BAN":
                await interaction.response.send_message(
                    "Ban cancelled. You must type `BAN` to confirm.",
                    ephemeral=True
                )
                return

            await interaction.response.defer(ephemeral=True)

            results = await rcon_manager.execute_on_servers(
                self.servers, 'ban', self.player_id.value, self.reason.value
            )

            embed = self.cog._build_results_embed("Ban Results", results, self.servers)

            # Add ban details
            embed.insert_field_at(0, name="Player ID", value=f"`{self.player_id.value}`", inline=True)
            embed.insert_field_at(1, name="Reason", value=self.reason.value, inline=True)

            # Log command
            for server_id, response in results.items():
                RCONCommandLogQueries.log_command(
                    guild_id=interaction.guild_id,
                    command_type='ban',
                    executed_by_id=interaction.user.id,
                    success=response.success,
                    server_id=server_id,
                    target_player_id=self.player_id.value,
                    command_data={'reason': self.reason.value},
                    response_message=response.message
                )

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Error in BanPlayerModal: {e}", exc_info=True)
            await interaction.followup.send(f"An error occurred: {e}", ephemeral=True)


class ToggleConfirmModal(discord.ui.Modal):
    """Confirmation modal for toggle commands (whitelist, global chat, etc.)."""

    action = discord.ui.TextInput(
        label="Choose Action",
        placeholder="Type ON or OFF",
        required=True,
        max_length=3
    )

    confirmation = discord.ui.TextInput(
        label='Type "CONFIRM" to proceed',
        placeholder="CONFIRM",
        required=True,
        max_length=10
    )

    def __init__(self, cog, servers: list[dict], setting_name: str, rcon_method: str):
        super().__init__(title=f"Toggle {setting_name}")
        self.cog = cog
        self.servers = servers
        self.setting_name = setting_name
        self.rcon_method = rcon_method

    async def on_submit(self, interaction: discord.Interaction):
        try:
            # Validate action
            action_value = self.action.value.upper()
            if action_value not in ['ON', 'OFF']:
                await interaction.response.send_message(
                    "Invalid action. Please type ON or OFF.",
                    ephemeral=True
                )
                return

            # Validate confirmation
            if self.confirmation.value.upper() != "CONFIRM":
                await interaction.response.send_message(
                    "Action cancelled. You must type `CONFIRM` to proceed.",
                    ephemeral=True
                )
                return

            await interaction.response.defer(ephemeral=True)

            # Convert ON/OFF to boolean
            enabled = action_value == 'ON'

            # Execute command
            results = await rcon_manager.execute_on_servers(
                self.servers, self.rcon_method, enabled
            )

            embed = self.cog._build_results_embed(
                f"{self.setting_name} Toggle Results",
                results,
                self.servers
            )

            # Add what was changed
            embed.insert_field_at(
                0,
                name="Action",
                value=f"{self.setting_name} **{'Enabled' if enabled else 'Disabled'}**",
                inline=False
            )

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Error in ToggleConfirmModal: {e}", exc_info=True)
            await interaction.followup.send(f"An error occurred: {e}", ephemeral=True)


class DMPlayerModal(discord.ui.Modal, title="Send Private DM to Player"):
    """Modal for sending a private DM to a player in-game."""

    player_id = discord.ui.TextInput(
        label="Player's Game ID",
        placeholder="76561198012345678 (Steam ID) or XXX-XXX-XXX (Alderon ID)",
        required=True,
        max_length=50
    )

    message = discord.ui.TextInput(
        label="Message",
        placeholder="Your message to the player",
        required=True,
        style=discord.TextStyle.paragraph,
        max_length=400
    )

    def __init__(self, server_config: dict):
        super().__init__()
        self.server_config = server_config

    async def on_submit(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer(ephemeral=True)

            # Determine sender's role for the message
            user = interaction.user
            if user.id == interaction.guild.owner_id:
                sender_role = "Owner"
            elif user.guild_permissions.administrator:
                sender_role = "Head Admin"
            else:
                # Check highest role name
                highest_role = None
                for role in sorted(user.roles, key=lambda r: r.position, reverse=True):
                    if role.name != "@everyone":
                        highest_role = role.name
                        break
                sender_role = highest_role or "Admin"

            # Format the message with context
            server_name = self.server_config['server_name']
            discord_name = user.name  # Use actual username (e.g., .blytz.) not display name

            formatted_message = (
                f"[PRIVATE DM from {sender_role}]\n"
                f"\n"  # RCON symbol appears on the blank line after this
                f"\n"
                f"Server: {server_name}\n"
                f"From: {discord_name}\n"
                f"{self.message.value}"
            )

            client = get_rcon_client(
                self.server_config['game_type'],
                self.server_config['host'],
                self.server_config['port'],
                self.server_config['password']
            )

            # Use comma-separated format (Format 2) which works in-game
            await client.connect()
            command = b'\x02\x11' + f'{self.player_id.value},{formatted_message}'.encode() + b'\x00'
            await client._send_command(command)
            await client.disconnect()

            embed = discord.Embed(
                title="✉️ Private DM Sent",
                color=discord.Color.blue()
            )
            embed.add_field(name="Server", value=self.server_config['server_name'], inline=True)
            embed.add_field(name="Player ID", value=f"`{self.player_id.value}`", inline=True)
            embed.add_field(name="Sent by", value=f"{sender_role} ({discord_name})", inline=False)
            embed.add_field(name="Message", value=f"```{self.message.value}```", inline=False)

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Error sending DM: {e}", exc_info=True)
            await interaction.followup.send(f"An error occurred: {e}", ephemeral=True)


class RCONCommands(commands.GroupCog, name="rcon"):
    """RCON server management commands."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        super().__init__()
        # DEPRECATED: In-memory caches - data is now stored in database
        # These are kept for backward compatibility during migration
        # Use _get_dino_pool() and _get_ai_restrictions() instead of direct access
        self.master_dino_pools = {}
        self.disallowed_ai_state = {}

    # ==========================================
    # DATABASE HELPER METHODS
    # ==========================================

    def _get_dino_pool(self, guild_id: int) -> list[str]:
        """
        Get dinosaur master pool from database.
        Falls back to default 20 dinosaurs if not configured.
        """
        pool = DinoPools.get_pool(guild_id)
        if not pool:
            # Return default pool if nothing in database
            return AllowDinosView.DINOSAURS.copy()
        return pool

    def _save_dino_pool(self, guild_id: int, dinosaurs: list[str]) -> bool:
        """Save dinosaur master pool to database."""
        success = DinoPools.set_pool(guild_id, dinosaurs)
        if success:
            # Update cache for backward compatibility
            self.master_dino_pools[guild_id] = dinosaurs.copy()
        return success

    def _get_ai_restrictions(self, guild_id: int, server_id: int) -> list[str]:
        """Get AI restrictions from database for a specific server."""
        return AIRestrictions.get_restrictions(guild_id, server_id)

    def _save_ai_restrictions(self, guild_id: int, server_id: int, ai_creatures: list[str]) -> bool:
        """Save AI restrictions to database for a specific server."""
        success = AIRestrictions.set_restrictions(guild_id, server_id, ai_creatures)
        if success:
            # Update cache for backward compatibility
            if guild_id not in self.disallowed_ai_state:
                self.disallowed_ai_state[guild_id] = {}
            self.disallowed_ai_state[guild_id][server_id] = ai_creatures.copy()
        return success

    def _save_ai_restrictions_bulk(self, guild_id: int, server_ids: list[int], ai_creatures: list[str]) -> bool:
        """Save AI restrictions to database for multiple servers ("All Servers")."""
        success = AIRestrictions.set_restrictions_bulk(guild_id, server_ids, ai_creatures)
        if success:
            # Update cache for backward compatibility
            if guild_id not in self.disallowed_ai_state:
                self.disallowed_ai_state[guild_id] = {}
            for server_id in server_ids:
                self.disallowed_ai_state[guild_id][server_id] = ai_creatures.copy()
        return success

    def _get_disabled_dinos(self, guild_id: int, server_id: int) -> list[str]:
        """Get disabled dinosaurs from database for a specific server."""
        return DisabledDinos.get_disabled(guild_id, server_id)

    def _save_disabled_dinos(self, guild_id: int, server_id: int, dinosaurs: list[str]) -> bool:
        """Save disabled dinosaurs to database for a specific server."""
        return DisabledDinos.set_disabled(guild_id, server_id, dinosaurs)

    def _save_disabled_dinos_bulk(self, guild_id: int, server_ids: list[int], dinosaurs: list[str]) -> bool:
        """Save disabled dinosaurs to database for multiple servers ("All Servers")."""
        return DisabledDinos.set_disabled_bulk(guild_id, server_ids, dinosaurs)

    # ==========================================
    # DROPDOWN MENU COMMAND
    # ==========================================

    @app_commands.command(name="panel", description="Open RCON control panel with categorized options")
    @app_commands.guild_only()
    async def rcon_panel(self, interaction: discord.Interaction):
        """Show the RCON control panel with dropdown selections."""
        # Check if user has permission to access the panel
        if not await require_permission(interaction, 'rcon_panel'):
            return

        # Get user's allowed commands
        user_permissions = get_user_allowed_commands(interaction.guild_id, interaction.user)

        # Filter to only inpanel_rcon_* permissions
        inpanel_permissions = {perm for perm in user_permissions if perm.startswith('inpanel_rcon_')}

        # If user has no panel permissions, show error
        if not inpanel_permissions:
            await interaction.response.send_message(
                "You don't have permission to use any RCON panel features.\n"
                "Contact an administrator to configure your permissions.",
                ephemeral=True
            )
            return

        embed = discord.Embed(
            title="🎮 RCON Control Panel",
            description="Select a command from the dropdowns below:\n\n"
                       "**Setup & Configuration** - Manage server connections\n"
                       "**Raw Commands** - Send raw RCON commands (PoT/Any game)\n"
                       "**Player Management** - Kick, ban, announce, message players\n"
                       "**Server Control** - Save server state\n"
                       "**Evrima Game Settings** - Whitelist, dinos, chat, AI, humans (Evrima only)",
            color=discord.Color.blue()
        )
        embed.set_footer(text="Premium Feature | Select a category and choose an action")

        # Send initial message without view
        await interaction.response.send_message(embed=embed, ephemeral=True)

        # Get the message object and create view with message reference for refresh capability
        panel_message = await interaction.original_response()
        view = RCONCommandView(self, inpanel_permissions, panel_message)

        # Edit message to add the view
        await panel_message.edit(view=view)

    async def _refresh_panel(self, panel_message, user_permissions: set):
        """Refresh the panel dropdown by recreating the view."""
        try:
            embed = discord.Embed(
                title="🎮 RCON Control Panel",
                description="Select a command from the dropdowns below:\n\n"
                           "**Setup & Configuration** - Manage server connections\n"
                           "**Raw Commands** - Send raw RCON commands (PoT/Any game)\n"
                           "**Player Management** - Kick, ban, announce, message players\n"
                           "**Server Control** - Save server state\n"
                           "**Evrima Game Settings** - Whitelist, dinos, chat, AI, humans (Evrima only)",
                color=discord.Color.blue()
            )
            embed.set_footer(text="Premium Feature | Select a category and choose an action")

            # Create fresh view with reset dropdowns
            view = RCONCommandView(self, user_permissions, panel_message)

            # Edit the panel message to refresh the dropdowns
            await panel_message.edit(embed=embed, view=view)
        except Exception as e:
            logger.error(f"Error refreshing RCON panel: {e}", exc_info=True)

    # ==========================================
    # HELPER METHODS FOR DROPDOWN CALLBACKS
    # ==========================================

    async def _show_servers(self, interaction: discord.Interaction):
        """Show list of configured servers (called from dropdown)."""
        # Call the existing list_servers command logic directly
        try:
            servers = RCONServerQueries.get_servers(interaction.guild_id, active_only=False)

            if not servers:
                await interaction.response.send_message(
                    "No RCON servers configured. Use **Setup & Configuration → Add Server** to add one.",
                    ephemeral=True
                )
                return

            embed = discord.Embed(
                title="RCON Servers",
                description=f"Configured servers for {interaction.guild.name}",
                color=discord.Color.blue()
            )

            for server in servers:
                game = "Evrima" if server['game_type'] == 'the_isle_evrima' else "PoT"
                status = "✅ Active" if server['is_active'] else "❌ Inactive"

                last_conn = server.get('last_connected_at')
                last_conn_str = last_conn.strftime("%Y-%m-%d %H:%M") if last_conn else "Never"

                value = (
                    f"**Game:** {game}\n"
                    f"**Host:** `{server['host']}:{server['port']}`\n"
                    f"**Status:** {status}\n"
                    f"**Last Connected:** {last_conn_str}"
                )

                if server.get('last_error'):
                    value += f"\n**Error:** {server['last_error'][:50]}..."

                embed.add_field(
                    name=server['server_name'],
                    value=value,
                    inline=False
                )

            await interaction.response.send_message(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Error listing servers: {e}", exc_info=True)
            await interaction.response.send_message(
                "An error occurred while listing servers.",
                ephemeral=True
            )

    async def _show_remove_server_modal(self, interaction: discord.Interaction):
        """Show server selection for removal."""
        servers = RCONServerQueries.get_servers(interaction.guild_id, active_only=False)
        if not servers:
            await interaction.response.send_message(
                "No servers configured. Add a server first with 'Add Server'.",
                ephemeral=True
            )
            return

        # Create server selection dropdown
        options = []
        for server in servers:
            game_emoji = "🦖" if server['game_type'] == 'the_isle_evrima' else "🦕"
            options.append(discord.SelectOption(
                label=server['server_name'],
                value=str(server['id']),
                description=f"{server['game_type']} - {server['host']}:{server['port']}",
                emoji=game_emoji
            ))

        class RemoveServerConfirmModal(discord.ui.Modal, title="Confirm Server Removal"):
            """Modal requiring confirmation text to remove server."""

            confirmation = discord.ui.TextInput(
                label="Type 'remove' to confirm deletion",
                placeholder="remove",
                required=True,
                max_length=10
            )

            def __init__(self, server_id: int, server_name: str, guild_id: int):
                super().__init__()
                self.server_id = server_id
                self.server_name = server_name
                self.guild_id = guild_id

            async def on_submit(self, modal_interaction: discord.Interaction):
                if self.confirmation.value.lower() not in ['remove', 'delete']:
                    await modal_interaction.response.send_message(
                        "❌ Confirmation failed. You must type 'remove' or 'delete' to confirm.",
                        ephemeral=True
                    )
                    return

                if RCONServerQueries.remove_server(self.server_id, self.guild_id):
                    embed = discord.Embed(
                        title="🗑️ Server Removed",
                        description=f"Successfully removed server: **{self.server_name}**",
                        color=discord.Color.green()
                    )
                else:
                    embed = discord.Embed(
                        title="❌ Error",
                        description="Failed to remove server.",
                        color=discord.Color.red()
                    )
                await modal_interaction.response.send_message(embed=embed, ephemeral=True)

        class RemoveServerSelect(discord.ui.Select):
            def __init__(self):
                super().__init__(placeholder="Select server to remove", options=options)

            async def callback(self, select_interaction: discord.Interaction):
                server_id = int(self.values[0])
                server_data = next((s for s in servers if s['id'] == server_id), None)

                # Show confirmation modal
                modal = RemoveServerConfirmModal(
                    server_id=server_id,
                    server_name=server_data['server_name'],
                    guild_id=select_interaction.guild_id
                )
                await select_interaction.response.send_modal(modal)

        view = discord.ui.View(timeout=60)
        view.add_item(RemoveServerSelect())

        embed = discord.Embed(
            title="🗑️ Remove Server",
            description="Select a server to remove:",
            color=discord.Color.orange()
        )
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    async def _show_test_connection_modal(self, interaction: discord.Interaction):
        """Show server selection for connection test."""
        servers = RCONServerQueries.get_servers(interaction.guild_id)
        if not servers:
            await interaction.response.send_message(
                "No servers configured. Add a server first with 'Add Server'.",
                ephemeral=True
            )
            return

        # Create server selection dropdown
        options = []
        for server in servers:
            game_emoji = "🦖" if server['game_type'] == 'the_isle_evrima' else "🦕"
            options.append(discord.SelectOption(
                label=server['server_name'],
                value=str(server['id']),
                description=f"{server['game_type']} - {server['host']}:{server['port']}",
                emoji=game_emoji
            ))

        class TestConnectionSelect(discord.ui.Select):
            def __init__(self):
                super().__init__(placeholder="Select server to test", options=options)

            async def callback(self, select_interaction: discord.Interaction):
                await select_interaction.response.defer(ephemeral=True)
                server_id = int(self.values[0])
                server_data = next((s for s in servers if s['id'] == server_id), None)

                # Test connection
                client = get_rcon_client(
                    server_data['game_type'],
                    server_data['host'],
                    server_data['port'],
                    server_data['password']
                )

                try:
                    success = await client.connect()
                    if success:
                        await client.disconnect()
                        embed = discord.Embed(
                            title="✅ Connection Successful",
                            description=f"Successfully connected to **{server_data['server_name']}**",
                            color=discord.Color.green()
                        )
                        embed.add_field(name="Server", value=server_data['server_name'])
                        embed.add_field(name="Host", value=f"{server_data['host']}:{server_data['port']}")
                    else:
                        embed = discord.Embed(
                            title="❌ Connection Failed",
                            description=f"Could not connect to **{server_data['server_name']}**",
                            color=discord.Color.red()
                        )
                except Exception as e:
                    embed = discord.Embed(
                        title="❌ Connection Error",
                        description=f"Error: {str(e)}",
                        color=discord.Color.red()
                    )

                await select_interaction.followup.send(embed=embed, ephemeral=True)

        view = discord.ui.View(timeout=60)
        view.add_item(TestConnectionSelect())

        embed = discord.Embed(
            title="🔌 Test Connection",
            description="Select a server to test connection:",
            color=discord.Color.blue()
        )
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    async def _show_kick_modal(self, interaction: discord.Interaction):
        """Show server selection for kick or direct modal if 1 server."""
        servers = RCONServerQueries.get_servers(interaction.guild_id, active_only=True)
        if not servers:
            await interaction.response.send_message(
                "No active servers configured. Add a server first.",
                ephemeral=True
            )
            return

        # If only 1 server, skip selection and go straight to modal
        if len(servers) == 1:
            modal = KickPlayerModalSimplified(self, servers)
            await interaction.response.send_modal(modal)
        else:
            # Multiple servers - show selection
            view = PlayerActionServerSelectView(self, interaction.guild_id, "kick", "👢 Kick Player")
            embed = discord.Embed(
                title="👢 Kick Player",
                description="Select which server(s) to kick the player from:",
                color=discord.Color.orange()
            )
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    async def _show_ban_modal(self, interaction: discord.Interaction):
        """Show server selection for ban or direct modal if 1 server."""
        servers = RCONServerQueries.get_servers(interaction.guild_id, active_only=True)
        if not servers:
            await interaction.response.send_message(
                "No active servers configured. Add a server first.",
                ephemeral=True
            )
            return

        # If only 1 server, skip selection and go straight to modal
        if len(servers) == 1:
            modal = BanPlayerModal(self, servers)
            await interaction.response.send_modal(modal)
        else:
            # Multiple servers - show selection
            view = PlayerActionServerSelectView(self, interaction.guild_id, "ban", "🔨 Ban Player")
            embed = discord.Embed(
                title="🔨 Ban Player",
                description="Select which server(s) to ban the player from:",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    async def _show_announce_modal(self, interaction: discord.Interaction):
        """Show server selection for announcement or direct modal if 1 server."""
        servers = RCONServerQueries.get_servers(interaction.guild_id, active_only=True)
        if not servers:
            await interaction.response.send_message(
                "No active servers configured. Add a server first.",
                ephemeral=True
            )
            return

        # If only 1 server, skip selection and go straight to modal
        if len(servers) == 1:
            modal = AnnounceMessageModal(self, servers)
            await interaction.response.send_modal(modal)
        else:
            # Multiple servers - show selection
            view = AnnounceServerSelectView(self, interaction.guild_id)
            embed = discord.Embed(
                title="📢 Server Announcement",
                description="Select which server(s) to send the announcement to:",
                color=discord.Color.blue()
            )
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    async def _show_dm_modal(self, interaction: discord.Interaction):
        """Show server selection for DM or direct modal if 1 server."""
        servers = RCONServerQueries.get_servers(interaction.guild_id, active_only=True)
        if not servers:
            await interaction.response.send_message(
                "No active servers configured. Add a server first.",
                ephemeral=True
            )
            return

        # If only 1 server, skip selection and go straight to modal
        if len(servers) == 1:
            modal = DMPlayerModalSimplified(self, servers)
            await interaction.response.send_modal(modal)
        else:
            # Multiple servers - show selection
            view = PlayerActionServerSelectView(self, interaction.guild_id, "dm", "💬 DM Player")
            embed = discord.Embed(
                title="💬 DM Player In-Game",
                description="Select which server to send the DM on:",
                color=discord.Color.blue()
            )
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    async def _show_players_modal(self, interaction: discord.Interaction):
        """Show server selection for player list."""
        servers = RCONServerQueries.get_servers(interaction.guild_id)
        if not servers:
            await interaction.response.send_message(
                "No servers configured. Add a server first with 'Add Server'.",
                ephemeral=True
            )
            return

        # Create server selection dropdown
        options = []
        for server in servers:
            game_emoji = "🦖" if server['game_type'] == 'the_isle_evrima' else "🦕"
            options.append(discord.SelectOption(
                label=server['server_name'],
                value=str(server['id']),
                description=f"{server['game_type']} - {server['host']}:{server['port']}",
                emoji=game_emoji
            ))

        class PlayersListSelect(discord.ui.Select):
            def __init__(self):
                super().__init__(placeholder="Select server to list players", options=options)

            async def callback(self, select_interaction: discord.Interaction):
                await select_interaction.response.defer(ephemeral=True)
                server_id = int(self.values[0])
                server_data = next((s for s in servers if s['id'] == server_id), None)

                # Get player list
                client = get_rcon_client(
                    server_data['game_type'],
                    server_data['host'],
                    server_data['port'],
                    server_data['password']
                )

                try:
                    await client.connect()
                    players = await client.get_players()
                    await client.disconnect()

                    if not players:
                        embed = discord.Embed(
                            title="👥 Online Players",
                            description=f"No players currently online on **{server_data['server_name']}**",
                            color=discord.Color.orange()
                        )
                    else:
                        embed = discord.Embed(
                            title="👥 Online Players",
                            description=f"**{len(players)}** player(s) online on **{server_data['server_name']}**:",
                            color=discord.Color.green()
                        )

                        # Show players in chunks of 25 (field limit)
                        player_text = []
                        for player in players[:25]:  # Discord embed field limit
                            dino_info = ""
                            if player.dinosaur:
                                growth_pct = f" ({player.growth*100:.1f}%)" if player.growth else ""
                                dino_info = f" - {player.dinosaur}{growth_pct}"

                            player_text.append(f"**{player.player_name}**{dino_info}\n`{player.player_id}`")

                        embed.add_field(
                            name="Players",
                            value="\n\n".join(player_text),
                            inline=False
                        )

                        if len(players) > 25:
                            embed.set_footer(text=f"Showing first 25 of {len(players)} players")

                except Exception as e:
                    embed = discord.Embed(
                        title="❌ Error",
                        description=f"Failed to get player list: {str(e)}",
                        color=discord.Color.red()
                    )

                await select_interaction.followup.send(embed=embed, ephemeral=True)

        view = discord.ui.View(timeout=60)
        view.add_item(PlayersListSelect())

        embed = discord.Embed(
            title="👥 List Players",
            description="Select a server to view online players:",
            color=discord.Color.blue()
        )
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    async def _show_console_modal(self, interaction: discord.Interaction):
        """Show server selection for console command or direct modal if 1 server."""
        servers = RCONServerQueries.get_servers(interaction.guild_id, active_only=True)
        if not servers:
            await interaction.response.send_message(
                "No active servers configured. Add a server first.",
                ephemeral=True
            )
            return

        # If only 1 server, skip selection and go straight to modal
        if len(servers) == 1:
            modal = ConsoleCommandModalSimplified(self, servers)
            await interaction.response.send_modal(modal)
        else:
            # Multiple servers - show selection
            view = PlayerActionServerSelectView(self, interaction.guild_id, "console", "⌨️ Console Command")
            embed = discord.Embed(
                title="⌨️ Raw Console Command",
                description="Select which server to send the command to:",
                color=discord.Color.purple()
            )
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    async def _show_save_modal(self, interaction: discord.Interaction):
        """Show save server selection."""
        view = ServerSelectView(self, "save", interaction.guild_id)
        if not view.children:
            await interaction.response.send_message(
                "No active servers configured. Add a server first.",
                ephemeral=True
            )
            return

        embed = discord.Embed(
            title="💾 Save Server",
            description="Select which server to save:",
            color=discord.Color.blue()
        )
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    async def _show_wipecorpses_modal(self, interaction: discord.Interaction):
        """Show wipe corpses server selection or execute directly if 1 Evrima server."""
        # Get all servers and filter to Evrima only
        all_servers = RCONServerQueries.get_servers(interaction.guild_id, active_only=True)
        evrima_servers = [s for s in all_servers if s.get('game_type') == 'the_isle_evrima']

        if not evrima_servers:
            await interaction.response.send_message(
                "No Evrima servers configured. This command only works with The Isle Evrima.",
                ephemeral=True
            )
            return

        # If only 1 Evrima server, execute directly
        if len(evrima_servers) == 1:
            await interaction.response.defer(ephemeral=True)
            results = await rcon_manager.execute_on_servers(evrima_servers, 'wipe_corpses')
            embed = self._build_results_embed("Wipe Corpses Results", results, evrima_servers)
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            # Multiple Evrima servers - show selection
            view = ServerSelectView(self, "wipecorpses", interaction.guild_id)
            embed = discord.Embed(
                title="🧹 Wipe Corpses",
                description="Select which server to wipe corpses on (The Isle Evrima only):",
                color=discord.Color.orange()
            )
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    async def _show_allowclasses_modal(self, interaction: discord.Interaction):
        """Show allow classes with server selection."""
        try:
            # Get Evrima servers only
            all_servers = RCONServerQueries.get_servers(interaction.guild_id)
            servers = [s for s in all_servers if s.get('game_type') == 'the_isle_evrima']

            if not servers:
                await interaction.response.send_message(
                    "No Isle Evrima servers configured. Add an Evrima server first.",
                    ephemeral=True
                )
                return

            # Get master pool for this guild from database (default to all 20 if not customized)
            guild_id = interaction.guild_id
            master_pool = self._get_dino_pool(guild_id)
            pool_count = len(master_pool)

            # If only 1 server, use it directly
            if len(servers) == 1:
                server_id = servers[0]['id']
                # Load currently disabled dinos from database
                current_disabled = self._get_disabled_dinos(guild_id, server_id)

                # Build status message
                if current_disabled:
                    status_msg = f"⚠️ Currently **{len(current_disabled)} dinosaurs disabled** (shown deselected in dropdown)."
                else:
                    status_msg = f"✅ All {pool_count} dinosaurs are **pre-selected** by default."

                view = AllowDinosView(self, servers, master_pool, current_disabled)
                await interaction.response.send_message(
                    f"**Select The Isle Evrima Playable Dinosaurs**\n"
                    f"🎯 Server: **{servers[0]['server_name']}**\n"
                    f"{status_msg}\n"
                    f"🔽 Open the dropdown and **deselect** any you want to disable.\n"
                    f"✔️ Click **Confirm & Apply** when ready to apply changes.",
                    view=view,
                    ephemeral=True
                )
            else:
                # Multiple servers - show server selection first
                view = AllowClassesServerSelectView(self, servers, master_pool, pool_count)
                embed = discord.Embed(
                    title="🦖 Allow Classes - Select Server",
                    description=f"Select which server(s) to configure playable dinosaurs:\n\n"
                               f"Pool contains **{pool_count} dinosaurs**",
                    color=discord.Color.green()
                )
                await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

        except Exception as e:
            logger.error(f"Error opening allow classes view: {e}", exc_info=True)
            await interaction.response.send_message(f"An error occurred: {e}", ephemeral=True)

    async def _show_addremoveclass_modal(self, interaction: discord.Interaction):
        """Show add or remove class view for managing master dinosaur pool with server selection."""
        try:
            guild_id = interaction.guild_id

            # Get Evrima servers only
            all_servers = RCONServerQueries.get_servers(guild_id)
            servers = [s for s in all_servers if s.get('game_type') == 'the_isle_evrima']

            if not servers:
                await interaction.response.send_message(
                    "No Isle Evrima servers configured. Add an Evrima server first.",
                    ephemeral=True
                )
                return

            # Get current pool from database
            current_pool = self._get_dino_pool(guild_id)

            # If only 1 server, use it directly
            if len(servers) == 1:
                view = AddOrRemoveClassView(self, guild_id, current_pool, servers)
                embed = discord.Embed(
                    title="🔧 Manage Master Dinosaur Pool",
                    description=f"🎯 Server: **{servers[0]['server_name']}**\n\n"
                               f"**Current pool contains {len(current_pool)} dinosaurs.**\n\n"
                               "Use the buttons below to add or remove dinosaurs from the master pool.\n"
                               "This affects what appears in the **Allow Classes** dropdown.\n"
                               "**Changes will be applied to the server immediately.**",
                    color=discord.Color.gold()
                )
                await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
            else:
                # Multiple servers - show server selection first
                view = AddOrRemoveClassServerSelectView(self, servers, guild_id, current_pool)
                embed = discord.Embed(
                    title="🔧 Manage Master Dinosaur Pool - Select Server",
                    description=f"Select which server(s) to apply changes to:\n\n"
                               f"Pool contains **{len(current_pool)} dinosaurs**\n\n"
                               "Changes to the pool will be applied in-game immediately.",
                    color=discord.Color.gold()
                )
                await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

        except Exception as e:
            logger.error(f"Error opening add/remove class view: {e}", exc_info=True)
            await interaction.response.send_message(f"An error occurred: {e}", ephemeral=True)

    async def _show_whitelist_modal(self, interaction: discord.Interaction):
        """Show whitelist toggle view."""
        embed = discord.Embed(
            title="🔐 Toggle Whitelist",
            description="Enable or disable the server whitelist (The Isle Evrima only):",
            color=discord.Color.blue()
        )
        view = ToggleSelectView(
            self, "whitelist_toggle", interaction.guild_id,
            "Toggle Whitelist", "Select action"
        )
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    async def _show_managewhitelist_modal(self, interaction: discord.Interaction):
        """Show combined whitelist management view."""
        embed = discord.Embed(
            title="📝 Manage Whitelist",
            description="Select an action to manage the server whitelist (The Isle Evrima only):",
            color=discord.Color.blue()
        )
        view = ManageWhitelistView(self, interaction.guild_id)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    async def _show_globalchat_modal(self, interaction: discord.Interaction):
        """Show global chat toggle view."""
        embed = discord.Embed(
            title="💬 Toggle Global Chat",
            description="Enable or disable global chat (The Isle Evrima only):",
            color=discord.Color.blue()
        )
        view = ToggleSelectView(
            self, "globalchat", interaction.guild_id,
            "Toggle Global Chat", "Select action"
        )
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    async def _show_togglehumans_modal(self, interaction: discord.Interaction):
        """Show toggle humans view."""
        embed = discord.Embed(
            title="🚶 Toggle Humans",
            description="Enable or disable human players (The Isle Evrima only):",
            color=discord.Color.blue()
        )
        view = ToggleSelectView(
            self, "togglehumans", interaction.guild_id,
            "Toggle Humans", "Select action"
        )
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    async def _show_toggleai_modal(self, interaction: discord.Interaction):
        """Show toggle AI view."""
        embed = discord.Embed(
            title="🤖 Toggle AI",
            description="Enable or disable AI spawns (The Isle Evrima only):",
            color=discord.Color.blue()
        )
        view = ToggleSelectView(
            self, "toggleai", interaction.guild_id,
            "Toggle AI", "Select action"
        )
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    async def _show_disableai_modal(self, interaction: discord.Interaction):
        """Show disallow AI system with server selection."""
        try:
            # Get Evrima servers only
            all_servers = RCONServerQueries.get_servers(interaction.guild_id)
            servers = [s for s in all_servers if s.get('game_type') == 'the_isle_evrima']

            if not servers:
                await interaction.response.send_message(
                    "No Isle Evrima servers configured. Add an Evrima server first.",
                    ephemeral=True
                )
                return

            guild_id = interaction.guild_id

            # If only 1 server, use it directly
            if len(servers) == 1:
                server_id = servers[0]['id']
                # Load current disallowed AI state for this server from database
                current_disallowed = self._get_ai_restrictions(guild_id, server_id)

                view = DisallowAIView(self, servers, current_disallowed)

                status_text = (
                    f"Currently **{len(current_disallowed)} AI disabled**"
                    if current_disallowed
                    else "All AI currently **enabled**"
                )

                await interaction.response.send_message(
                    f"**Disallow AI Creatures (The Isle Evrima)**\n"
                    f"🎯 Server: **{servers[0]['server_name']}**\n"
                    f"📊 Status: {status_text}\n\n"
                    f"🔽 Select/deselect AI creatures to toggle restrictions.\n"
                    f"✔️ Click **Confirm & Apply** to save changes.\n"
                    f"🔵 Click **Clear All Restrictions** to enable all AI.",
                    view=view,
                    ephemeral=True
                )
            else:
                # Multiple servers - show server selection first
                view = DisallowAIServerSelectView(self, servers)
                embed = discord.Embed(
                    title="🚫 Disallow AI - Select Server",
                    description="Select which server(s) to configure AI restrictions:",
                    color=discord.Color.orange()
                )
                await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

        except Exception as e:
            logger.error(f"Error opening disallow AI view: {e}", exc_info=True)
            await interaction.response.send_message(f"An error occurred: {e}", ephemeral=True)

    async def _show_aidensity_modal(self, interaction: discord.Interaction):
        """Show AI density modal with server selection."""
        try:
            # Get Evrima servers only
            all_servers = RCONServerQueries.get_servers(interaction.guild_id)
            servers = [s for s in all_servers if s.get('game_type') == 'the_isle_evrima']

            if not servers:
                await interaction.response.send_message(
                    "No Isle Evrima servers configured. Add an Evrima server first.",
                    ephemeral=True
                )
                return

            # If only 1 server, show modal directly
            if len(servers) == 1:
                modal = AIDensityModal(self, servers)
                await interaction.response.send_modal(modal)
            else:
                # Multiple servers - show server selection first
                view = AIDensityServerSelectView(self, servers)
                embed = discord.Embed(
                    title="🎚️ AI Density - Select Server",
                    description="Select which server(s) to configure AI spawn density:",
                    color=discord.Color.blue()
                )
                await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

        except Exception as e:
            logger.error(f"Error opening AI density modal: {e}", exc_info=True)
            await interaction.response.send_message(f"An error occurred: {e}", ephemeral=True)

    # ==========================================
    # SERVER CONFIGURATION
    # ==========================================

    @app_commands.command(name="addserver", description="Add a new RCON server configuration")
    @app_commands.guild_only()
    @app_commands.describe(
        game="Game type for this server"
    )
    @app_commands.choices(game=[
        app_commands.Choice(name="The Isle Evrima", value="the_isle_evrima"),
        app_commands.Choice(name="Path of Titans", value="path_of_titans"),
    ])
    async def add_server(
        self,
        interaction: discord.Interaction,
        game: app_commands.Choice[str]
    ):
        """Add a new RCON server - opens a configuration modal."""
        if not await require_permission(interaction, 'rcon_addserver'):
            return

        GuildQueries.get_or_create(interaction.guild_id, interaction.guild.name)

        # Open the modal for server configuration
        modal = AddRCONServerModal(game_type=game.value, game_display=game.name)
        await interaction.response.send_modal(modal)

    @app_commands.command(name="servers", description="List configured RCON servers")
    @app_commands.guild_only()
    async def list_servers(self, interaction: discord.Interaction):
        """List all configured RCON servers."""
        if not await require_permission(interaction, 'rcon_servers'):
            return

        try:
            servers = RCONServerQueries.get_servers(interaction.guild_id, active_only=False)

            if not servers:
                await interaction.response.send_message(
                    "No RCON servers configured. Use `/rcon addserver` to add one.",
                    ephemeral=True
                )
                return

            embed = discord.Embed(
                title="RCON Servers",
                description=f"Configured servers for {interaction.guild.name}",
                color=discord.Color.blue()
            )

            for server in servers:
                game = "Evrima" if server['game_type'] == 'the_isle_evrima' else "PoT"
                status = "Active" if server['is_active'] else "Inactive"
                default = " (Default)" if server['is_default'] else ""

                last_conn = server.get('last_connected_at')
                last_conn_str = last_conn.strftime("%Y-%m-%d %H:%M") if last_conn else "Never"

                value = (
                    f"**Game:** {game}\n"
                    f"**Host:** `{server['host']}:{server['port']}`\n"
                    f"**Status:** {status}\n"
                    f"**Last Connected:** {last_conn_str}"
                )

                if server.get('last_error'):
                    value += f"\n**Error:** {server['last_error'][:50]}..."

                embed.add_field(
                    name=f"{server['server_name']}{default}",
                    value=value,
                    inline=False
                )

            await interaction.response.send_message(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Error listing servers: {e}", exc_info=True)
            await interaction.response.send_message(
                "An error occurred while listing servers.",
                ephemeral=True
            )

    @app_commands.command(name="removeserver", description="Remove an RCON server configuration")
    @app_commands.guild_only()
    @app_commands.describe(server="Name of the server to remove")
    async def remove_server(self, interaction: discord.Interaction, server: str):
        """Remove an RCON server."""
        if not await require_permission(interaction, 'rcon_removeserver'):
            return

        try:
            server_config = RCONServerQueries.get_server_by_name(interaction.guild_id, server)
            if not server_config:
                await interaction.response.send_message(
                    f"Server `{server}` not found.",
                    ephemeral=True
                )
                return

            RCONServerQueries.remove_server(server_config['id'], interaction.guild_id)

            await interaction.response.send_message(
                f"Server `{server}` has been removed.",
                ephemeral=True
            )

        except Exception as e:
            logger.error(f"Error removing server: {e}", exc_info=True)
            await interaction.response.send_message(
                "An error occurred while removing the server.",
                ephemeral=True
            )

    @app_commands.command(name="test", description="Test RCON connection to a server")
    @app_commands.guild_only()
    @app_commands.describe(server="Server to test (leave empty for first available)")
    async def test_connection(self, interaction: discord.Interaction, server: str = None):
        """Test RCON connection."""
        if not await require_permission(interaction, 'rcon_test'):
            return

        await interaction.response.defer(ephemeral=True)

        try:
            if server:
                server_config = RCONServerQueries.get_server_by_name(interaction.guild_id, server)
            else:
                # Try default first, then fall back to first available server
                server_config = RCONServerQueries.get_default_server(interaction.guild_id)
                if not server_config:
                    servers = RCONServerQueries.get_servers(interaction.guild_id)
                    server_config = servers[0] if servers else None

            if not server_config:
                await interaction.followup.send(
                    "No servers configured. Use `/rcon addserver` to add one.",
                    ephemeral=True
                )
                return

            # Create client and test
            client = get_rcon_client(
                server_config['game_type'],
                server_config['host'],
                server_config['port'],
                server_config['password']
            )

            response = await client.test_connection()

            # Update connection status
            RCONServerQueries.update_connection_status(
                server_config['id'],
                response.success,
                response.message if not response.success else None
            )

            if response.success:
                embed = discord.Embed(
                    title="Connection Successful",
                    description=f"Successfully connected to `{server_config['server_name']}`",
                    color=discord.Color.green()
                )
            else:
                embed = discord.Embed(
                    title="Connection Failed",
                    description=f"Failed to connect to `{server_config['server_name']}`",
                    color=discord.Color.red()
                )
                embed.add_field(name="Error", value=response.message, inline=False)

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Error testing connection: {e}", exc_info=True)
            await interaction.followup.send(
                f"An error occurred: {e}",
                ephemeral=True
            )

    # ==========================================
    # PLAYER MANAGEMENT
    # ==========================================

    @app_commands.command(name="kick", description="Kick a player from the game server")
    @app_commands.guild_only()
    @app_commands.describe(
        player_id="Steam ID (17 digits) or Alderon ID (XXX-XXX-XXX)",
        reason="Reason for the kick",
        server="Target server (default: all servers)"
    )
    async def kick_player(
        self,
        interaction: discord.Interaction,
        player_id: str,
        reason: str = "Kicked by admin",
        server: str = None
    ):
        """Kick a player from game servers."""
        if not await require_permission(interaction, 'rcon_kick'):
            return

        await interaction.response.defer(ephemeral=True)

        try:
            servers = self._get_target_servers(interaction.guild_id, server)
            if not servers:
                await interaction.followup.send(
                    "No servers configured or server not found.",
                    ephemeral=True
                )
                return

            results = await rcon_manager.execute_on_servers(
                servers, 'kick', player_id, reason
            )

            embed = self._build_results_embed("Kick Results", results, servers)

            # Log command
            for server_id, response in results.items():
                RCONCommandLogQueries.log_command(
                    guild_id=interaction.guild_id,
                    command_type='kick',
                    executed_by_id=interaction.user.id,
                    success=response.success,
                    server_id=server_id,
                    target_player_id=player_id,
                    command_data={'reason': reason},
                    response_message=response.message
                )

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Error kicking player: {e}", exc_info=True)
            await interaction.followup.send(
                f"An error occurred: {e}",
                ephemeral=True
            )

    @app_commands.command(name="ban", description="Ban a player from the game server")
    @app_commands.guild_only()
    @app_commands.describe(server="Target server ('all' for all servers)")
    async def ban_player(self, interaction: discord.Interaction, server: str = None):
        """Ban a player from game servers using a modal with confirmation."""
        if not await require_permission(interaction, 'rcon_ban'):
            return

        try:
            servers = self._get_target_servers(interaction.guild_id, server)
            if not servers:
                await interaction.response.send_message(
                    "No servers configured or server not found.",
                    ephemeral=True
                )
                return

            # Open modal for ban details and confirmation
            modal = BanPlayerModal(self, servers)
            await interaction.response.send_modal(modal)

        except Exception as e:
            logger.error(f"Error opening ban modal: {e}", exc_info=True)
            await interaction.response.send_message(f"An error occurred: {e}", ephemeral=True)

    @app_commands.command(name="announce", description="Send an announcement to game servers")
    @app_commands.guild_only()
    @app_commands.describe(
        message="Message to announce",
        server="Target server ('all' for all servers)"
    )
    async def announce(
        self,
        interaction: discord.Interaction,
        message: str,
        server: str = None
    ):
        """Send an in-game announcement."""
        if not await require_permission(interaction, 'rcon_announce'):
            return

        await interaction.response.defer(ephemeral=True)

        try:
            servers = self._get_target_servers(interaction.guild_id, server)
            if not servers:
                await interaction.followup.send(
                    "No servers configured or server not found.",
                    ephemeral=True
                )
                return

            results = await rcon_manager.execute_on_servers(
                servers, 'announce', message
            )

            embed = self._build_results_embed("Announcement Results", results, servers)

            # Add the message that was sent
            embed.insert_field_at(
                0,
                name="Message Sent",
                value=f"```{message[:500]}```",
                inline=False
            )

            # Log command
            for server_id, response in results.items():
                RCONCommandLogQueries.log_command(
                    guild_id=interaction.guild_id,
                    command_type='announce',
                    executed_by_id=interaction.user.id,
                    success=response.success,
                    server_id=server_id,
                    command_data={'message': message},
                    response_message=response.message
                )

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Error sending announcement: {e}", exc_info=True)
            await interaction.followup.send(
                f"An error occurred: {e}",
                ephemeral=True
            )

    @app_commands.command(name="players", description="List online players on a server")
    @app_commands.guild_only()
    @app_commands.describe(server="Server to query (leave empty for first available)")
    async def list_players(self, interaction: discord.Interaction, server: str = None):
        """List online players on a server."""
        if not await require_permission(interaction, 'rcon_players'):
            return

        await interaction.response.defer(ephemeral=True)

        try:
            if server:
                server_config = RCONServerQueries.get_server_by_name(interaction.guild_id, server)
            else:
                # Try default first, then fall back to first available server
                server_config = RCONServerQueries.get_default_server(interaction.guild_id)
                if not server_config:
                    servers = RCONServerQueries.get_servers(interaction.guild_id)
                    server_config = servers[0] if servers else None

            if not server_config:
                await interaction.followup.send(
                    "No servers configured. Use `/rcon addserver` to add one.",
                    ephemeral=True
                )
                return

            client = get_rcon_client(
                server_config['game_type'],
                server_config['host'],
                server_config['port'],
                server_config['password']
            )

            players = await client.get_players()

            embed = discord.Embed(
                title=f"Online Players - {server_config['server_name']}",
                color=discord.Color.blue()
            )

            if players:
                # Separate admins from regular players
                admins = [p for p in players if p.is_admin]
                regular_players = [p for p in players if not p.is_admin]

                description_parts = []

                # Show admins first
                if admins:
                    description_parts.append("**Admins:**")
                    for p in admins[:25]:
                        player_info = f"• {p.player_name} (`{p.player_id}`)"
                        if p.dinosaur:
                            gender_symbol = "♂" if p.gender == "Male" else "♀" if p.gender == "Female" else ""
                            growth_pct = f"{p.growth * 100:.1f}%" if p.growth is not None else "?"
                            prime_tag = " Prime" if p.is_prime_elder else ""
                            player_info += f" - {p.dinosaur} {gender_symbol} ({growth_pct}){prime_tag}"
                        description_parts.append(player_info)

                # Show regular players
                if regular_players:
                    if admins:
                        description_parts.append("")  # Blank line separator
                    description_parts.append("**Players:**")
                    for p in regular_players[:25]:
                        player_info = f"• {p.player_name} (`{p.player_id}`)"
                        if p.dinosaur:
                            gender_symbol = "♂" if p.gender == "Male" else "♀" if p.gender == "Female" else ""
                            growth_pct = f"{p.growth * 100:.1f}%" if p.growth is not None else "?"
                            prime_tag = " Prime" if p.is_prime_elder else ""
                            player_info += f" - {p.dinosaur} {gender_symbol} ({growth_pct}){prime_tag}"
                        description_parts.append(player_info)

                embed.description = "\n".join(description_parts)
                embed.set_footer(text=f"{len(players)} player(s) online")
            else:
                embed.description = "No players online"

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Error listing players: {e}", exc_info=True)
            await interaction.followup.send(
                f"An error occurred: {e}",
                ephemeral=True
            )

    @app_commands.command(name="dm", description="Send a direct message to an in-game player")
    @app_commands.guild_only()
    @app_commands.describe(server="Target server (leave empty for first available)")
    async def dm_player(
        self,
        interaction: discord.Interaction,
        server: str = None
    ):
        """Send a direct message to a player in-game."""
        if not await require_permission(interaction, 'rcon_dm'):
            return

        try:
            if server:
                server_config = RCONServerQueries.get_server_by_name(interaction.guild_id, server)
            else:
                # Try default first, then fall back to first available server
                server_config = RCONServerQueries.get_default_server(interaction.guild_id)
                if not server_config:
                    servers = RCONServerQueries.get_servers(interaction.guild_id)
                    server_config = servers[0] if servers else None

            if not server_config:
                await interaction.response.send_message(
                    "No servers configured. Use `/rcon addserver` to add one.",
                    ephemeral=True
                )
                return

            # Show modal
            await interaction.response.send_modal(DMPlayerModal(server_config))

        except Exception as e:
            logger.error(f"Error opening DM modal: {e}", exc_info=True)
            await interaction.response.send_message(
                f"An error occurred: {e}",
                ephemeral=True
            )

    @app_commands.command(name="console", description="Send raw RCON command to server")
    @app_commands.guild_only()
    @app_commands.describe(
        command="Raw RCON command to execute",
        server="Server to execute on (leave empty for default)"
    )
    async def console_command(self, interaction: discord.Interaction, command: str, server: str = None):
        """Send raw RCON command - useful for Path of Titans admin commands."""
        if not await require_permission(interaction, 'rcon_console'):
            return

        await interaction.response.defer(ephemeral=True)

        try:
            if server:
                server_config = RCONServerQueries.get_server_by_name(interaction.guild_id, server)
            else:
                server_config = RCONServerQueries.get_default_server(interaction.guild_id)
                if not server_config:
                    servers = RCONServerQueries.get_servers(interaction.guild_id)
                    server_config = servers[0] if servers else None

            if not server_config:
                await interaction.followup.send("No servers configured.", ephemeral=True)
                return

            # Get the appropriate client
            client = get_rcon_client(
                server_config['game_type'],
                server_config['host'],
                server_config['port'],
                server_config['password']
            )

            # For PoT, use the _execute method directly
            # For Evrima, this won't work well with binary protocol, so show a warning
            if server_config['game_type'] == 'the_isle_evrima':
                await interaction.followup.send(
                    "**Note:** Evrima uses a binary RCON protocol. Use the specific `/rcon` commands instead.\n"
                    "For Path of Titans, this command allows you to send any admin command directly.",
                    ephemeral=True
                )
                return

            # Execute the command (PoT uses text-based commands)
            from services.rcon import PathOfTitansRCONClient
            if isinstance(client, PathOfTitansRCONClient):
                response = await client._execute(command)

                embed = discord.Embed(
                    title=f"Console Command - {server_config['server_name']}",
                    color=discord.Color.blue()
                )

                # Show the command executed
                embed.add_field(
                    name="Command Executed",
                    value=f"```{command}```",
                    inline=False
                )

                # Show the response
                if response:
                    response_preview = response[:1000] + ("..." if len(response) > 1000 else "")
                    embed.add_field(
                        name="Server Response",
                        value=f"```{response_preview}```",
                        inline=False
                    )
                else:
                    embed.add_field(
                        name="Server Response",
                        value="*(No response)*",
                        inline=False
                    )

                # Log command
                RCONCommandLogQueries.log_command(
                    guild_id=interaction.guild_id,
                    command_type='console',
                    executed_by_id=interaction.user.id,
                    success=True,
                    server_id=server_config['id'],
                    command_data={'command': command},
                    response_message=response
                )

                await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Error executing console command: {e}", exc_info=True)
            await interaction.followup.send(f"An error occurred: {e}", ephemeral=True)

    @app_commands.command(name="save", description="Save the game server state")
    @app_commands.guild_only()
    @app_commands.describe(server="Server to save (leave empty for default)")
    async def save_server(self, interaction: discord.Interaction, server: str = None):
        """Save server state."""
        if not await require_permission(interaction, 'rcon_save'):
            return

        await interaction.response.defer(ephemeral=True)

        try:
            servers = self._get_target_servers(interaction.guild_id, server)
            if not servers:
                await interaction.followup.send(
                    "No servers configured.",
                    ephemeral=True
                )
                return

            results = await rcon_manager.execute_on_servers(servers, 'save')
            embed = self._build_results_embed("Save Results", results, servers)

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Error saving: {e}", exc_info=True)
            await interaction.followup.send(
                f"An error occurred: {e}",
                ephemeral=True
            )

    @app_commands.command(name="wipecorpses", description="Wipe all corpses from the server (Evrima only)")
    @app_commands.guild_only()
    @app_commands.describe(server="Server to wipe corpses on")
    async def wipe_corpses(self, interaction: discord.Interaction, server: str = None):
        """Wipe corpses from server with confirmation modal."""
        if not await require_permission(interaction, 'rcon_wipecorpses'):
            return

        try:
            servers = self._get_target_servers(interaction.guild_id, server)
            if not servers:
                await interaction.response.send_message("No servers configured.", ephemeral=True)
                return

            # Validate game type
            is_valid, error_msg = self._validate_game_type(servers, 'the_isle_evrima')
            if not is_valid:
                await interaction.response.send_message(error_msg, ephemeral=True)
                return

            # Open confirmation modal
            modal = WipeCorpsesConfirmModal(self, servers)
            await interaction.response.send_modal(modal)

        except Exception as e:
            logger.error(f"Error opening wipe corpses modal: {e}", exc_info=True)
            await interaction.response.send_message(f"An error occurred: {e}", ephemeral=True)

    @app_commands.command(name="allowdinos", description="Update list of allowed playable dinosaurs (Evrima only)")
    @app_commands.guild_only()
    @app_commands.describe(server="Server to update")
    async def allow_dinos(self, interaction: discord.Interaction, server: str = None):
        """Update playable dinosaurs list using a dropdown menu."""
        if not await require_permission(interaction, 'rcon_allowdinos'):
            return

        try:
            servers = self._get_target_servers(interaction.guild_id, server)
            if not servers:
                await interaction.response.send_message("No servers configured.", ephemeral=True)
                return

            # Validate game type
            is_valid, error_msg = self._validate_game_type(servers, 'the_isle_evrima')
            if not is_valid:
                await interaction.response.send_message(error_msg, ephemeral=True)
                return

            # Get master pool and currently disabled dinos
            guild_id = interaction.guild_id
            master_pool = self._get_dino_pool(guild_id)
            pool_count = len(master_pool)

            # If single server, load its disabled dinos; otherwise use empty list
            if len(servers) == 1:
                current_disabled = self._get_disabled_dinos(guild_id, servers[0]['id'])
            else:
                current_disabled = []

            # Build status message
            if current_disabled:
                status_msg = f"⚠️ Currently **{len(current_disabled)} dinosaurs disabled** (shown deselected in dropdown)."
            else:
                status_msg = f"✅ All {pool_count} dinosaurs are **pre-selected** by default."

            # Show dropdown view for dinosaur selection
            view = AllowDinosView(self, servers, master_pool, current_disabled)
            await interaction.response.send_message(
                f"**Select The Isle Evrima Playable Dinosaurs**\n"
                f"{status_msg}\n"
                f"🔽 Open the dropdown and **deselect** any you want to disable.\n"
                f"✔️ Click **Confirm** when ready to apply changes.",
                view=view,
                ephemeral=True
            )

        except Exception as e:
            logger.error(f"Error opening allowdinos view: {e}", exc_info=True)
            await interaction.response.send_message(f"An error occurred: {e}", ephemeral=True)

    @app_commands.command(name="whitelist", description="Toggle server whitelist on/off (Evrima only)")
    @app_commands.guild_only()
    @app_commands.describe(server="Server to configure")
    async def toggle_whitelist(self, interaction: discord.Interaction, server: str = None):
        """Toggle whitelist."""
        if not await require_permission(interaction, 'rcon_whitelist'):
            return

        try:
            servers = self._get_target_servers(interaction.guild_id, server)
            if not servers:
                await interaction.response.send_message("No servers configured.", ephemeral=True)
                return

            # Validate game type
            is_valid, error_msg = self._validate_game_type(servers, 'the_isle_evrima')
            if not is_valid:
                await interaction.response.send_message(error_msg, ephemeral=True)
                return

            # Show toggle confirmation modal
            modal = ToggleConfirmModal(self, servers, "Whitelist", "toggle_whitelist")
            await interaction.response.send_modal(modal)

        except Exception as e:
            logger.error(f"Error opening whitelist toggle modal: {e}", exc_info=True)
            await interaction.response.send_message(f"An error occurred: {e}", ephemeral=True)

    @app_commands.command(name="whitelistadd", description="Add players to whitelist (Evrima only)")
    @app_commands.guild_only()
    @app_commands.describe(server="Server to configure")
    async def whitelist_add(self, interaction: discord.Interaction, server: str = None):
        """Add players to whitelist using a modal."""
        if not await require_permission(interaction, 'rcon_whitelistadd'):
            return

        try:
            servers = self._get_target_servers(interaction.guild_id, server)
            if not servers:
                await interaction.response.send_message("No servers configured.", ephemeral=True)
                return

            # Validate game type
            is_valid, error_msg = self._validate_game_type(servers, 'the_isle_evrima')
            if not is_valid:
                await interaction.response.send_message(error_msg, ephemeral=True)
                return

            # Open modal for player IDs input
            modal = WhitelistAddModal(self, servers)
            await interaction.response.send_modal(modal)

        except Exception as e:
            logger.error(f"Error opening whitelist add modal: {e}", exc_info=True)
            await interaction.response.send_message(f"An error occurred: {e}", ephemeral=True)

    @app_commands.command(name="whitelistremove", description="Remove players from whitelist (Evrima only)")
    @app_commands.guild_only()
    @app_commands.describe(server="Server to configure")
    async def whitelist_remove(self, interaction: discord.Interaction, server: str = None):
        """Remove players from whitelist using a modal."""
        if not await require_permission(interaction, 'rcon_whitelistremove'):
            return

        try:
            servers = self._get_target_servers(interaction.guild_id, server)
            if not servers:
                await interaction.response.send_message("No servers configured.", ephemeral=True)
                return

            # Validate game type
            is_valid, error_msg = self._validate_game_type(servers, 'the_isle_evrima')
            if not is_valid:
                await interaction.response.send_message(error_msg, ephemeral=True)
                return

            # Open modal for player IDs input
            modal = WhitelistRemoveModal(self, servers)
            await interaction.response.send_modal(modal)

        except Exception as e:
            logger.error(f"Error opening whitelist remove modal: {e}", exc_info=True)
            await interaction.response.send_message(f"An error occurred: {e}", ephemeral=True)

    @app_commands.command(name="globalchat", description="Toggle global chat on/off (Evrima only)")
    @app_commands.guild_only()
    @app_commands.describe(server="Server to configure")
    async def toggle_global_chat(self, interaction: discord.Interaction, server: str = None):
        """Toggle global chat."""
        if not await require_permission(interaction, 'rcon_globalchat'):
            return

        try:
            servers = self._get_target_servers(interaction.guild_id, server)
            if not servers:
                await interaction.response.send_message("No servers configured.", ephemeral=True)
                return

            # Validate game type
            is_valid, error_msg = self._validate_game_type(servers, 'the_isle_evrima')
            if not is_valid:
                await interaction.response.send_message(error_msg, ephemeral=True)
                return

            # Show toggle confirmation modal
            modal = ToggleConfirmModal(self, servers, "Global Chat", "toggle_global_chat")
            await interaction.response.send_modal(modal)

        except Exception as e:
            logger.error(f"Error opening global chat toggle modal: {e}", exc_info=True)
            await interaction.response.send_message(f"An error occurred: {e}", ephemeral=True)

    @app_commands.command(name="togglehumans", description="Toggle human players on/off (Evrima only)")
    @app_commands.guild_only()
    @app_commands.describe(server="Server to configure")
    async def toggle_humans(self, interaction: discord.Interaction, server: str = None):
        """Toggle humans."""
        if not await require_permission(interaction, 'rcon_togglehumans'):
            return

        try:
            servers = self._get_target_servers(interaction.guild_id, server)
            if not servers:
                await interaction.response.send_message("No servers configured.", ephemeral=True)
                return

            # Validate game type
            is_valid, error_msg = self._validate_game_type(servers, 'the_isle_evrima')
            if not is_valid:
                await interaction.response.send_message(error_msg, ephemeral=True)
                return

            # Show toggle confirmation modal
            modal = ToggleConfirmModal(self, servers, "Human Players", "toggle_humans")
            await interaction.response.send_modal(modal)

        except Exception as e:
            logger.error(f"Error opening toggle humans modal: {e}", exc_info=True)
            await interaction.response.send_message(f"An error occurred: {e}", ephemeral=True)

    @app_commands.command(name="toggleai", description="Toggle AI on/off (Evrima only)")
    @app_commands.guild_only()
    @app_commands.describe(server="Server to configure")
    async def toggle_ai(self, interaction: discord.Interaction, server: str = None):
        """Toggle AI."""
        if not await require_permission(interaction, 'rcon_toggleai'):
            return

        try:
            servers = self._get_target_servers(interaction.guild_id, server)
            if not servers:
                await interaction.response.send_message("No servers configured.", ephemeral=True)
                return

            # Validate game type
            is_valid, error_msg = self._validate_game_type(servers, 'the_isle_evrima')
            if not is_valid:
                await interaction.response.send_message(error_msg, ephemeral=True)
                return

            # Show toggle confirmation modal
            modal = ToggleConfirmModal(self, servers, "AI Spawns", "toggle_ai")
            await interaction.response.send_modal(modal)

        except Exception as e:
            logger.error(f"Error opening toggle AI modal: {e}", exc_info=True)
            await interaction.response.send_message(f"An error occurred: {e}", ephemeral=True)

    @app_commands.command(name="disableai", description="Disable specific AI dinosaur classes (Evrima only)")
    @app_commands.guild_only()
    @app_commands.describe(server="Server to configure")
    async def disable_ai(self, interaction: discord.Interaction, server: str = None):
        """Disable AI classes using a modal."""
        if not await require_permission(interaction, 'rcon_disableai'):
            return

        try:
            servers = self._get_target_servers(interaction.guild_id, server)
            if not servers:
                await interaction.response.send_message("No servers configured.", ephemeral=True)
                return

            # Validate game type
            is_valid, error_msg = self._validate_game_type(servers, 'the_isle_evrima')
            if not is_valid:
                await interaction.response.send_message(error_msg, ephemeral=True)
                return

            # Open modal for AI class list input
            modal = DisableAIModal(self, servers)
            await interaction.response.send_modal(modal)

        except Exception as e:
            logger.error(f"Error opening disable AI modal: {e}", exc_info=True)
            await interaction.response.send_message(f"An error occurred: {e}", ephemeral=True)

    @app_commands.command(name="aidensity", description="Set AI spawn density (Evrima only)")
    @app_commands.guild_only()
    @app_commands.describe(
        density="AI density value (0.0 to 1.0)",
        server="Server to configure"
    )
    async def ai_density(self, interaction: discord.Interaction, density: float, server: str = None):
        """Set AI density."""
        if not await require_permission(interaction, 'rcon_aidensity'):
            return

        await interaction.response.defer(ephemeral=True)

        try:
            servers = self._get_target_servers(interaction.guild_id, server)
            if not servers:
                await interaction.followup.send("No servers configured.", ephemeral=True)
                return

            results = await rcon_manager.execute_on_servers(servers, 'set_ai_density', density)
            embed = self._build_results_embed("AI Density Results", results, servers)

            # Show the new density value
            embed.insert_field_at(
                0,
                name="New AI Density",
                value=f"**{density}**",
                inline=False
            )

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Error setting AI density: {e}", exc_info=True)
            await interaction.followup.send(f"An error occurred: {e}", ephemeral=True)

    # ==========================================
    # HELP
    # ==========================================

    @app_commands.command(name="help", description="Show RCON server management help")
    @app_commands.guild_only()
    async def rcon_help(self, interaction: discord.Interaction):
        """Display detailed RCON help with menu introduction."""
        from config.commands import COMMAND_DESCRIPTIONS
        from services.permissions import get_user_allowed_commands

        # Get commands this user can access
        allowed = get_user_allowed_commands(interaction.guild_id, interaction.user)

        # Check for panel access
        has_panel_access = 'rcon_panel' in allowed

        # Filter RCON commands
        rcon_commands = [
            'rcon_addserver', 'rcon_servers', 'rcon_removeserver', 'rcon_test',
            'rcon_kick', 'rcon_ban', 'rcon_announce', 'rcon_dm', 'rcon_players',
            'rcon_save', 'rcon_console', 'rcon_wipecorpses', 'rcon_allowdinos',
            'rcon_whitelist', 'rcon_whitelistadd', 'rcon_whitelistremove',
            'rcon_globalchat', 'rcon_togglehumans', 'rcon_toggleai',
            'rcon_disableai', 'rcon_aidensity'
        ]

        visible = [cmd for cmd in rcon_commands if cmd in allowed]

        if not visible and not has_panel_access:
            await interaction.response.send_message(
                "You don't have access to any RCON commands.\n\n"
                "Contact a server administrator to request permissions.",
                ephemeral=True
            )
            return

        embed = discord.Embed(
            title="🎮 RCON Server Management",
            description="Remote console control for game servers (Path of Titans & The Isle Evrima)",
            color=discord.Color.blue()
        )

        # Primary recommendation: Use the panel
        if has_panel_access:
            embed.add_field(
                name="🎮 Interactive Panel (Recommended)",
                value="**Use `/rcon panel` for easy access to all features:**\n"
                      "• Add and manage RCON server connections\n"
                      "• Player management (kick, ban, announce, DM)\n"
                      "• Send raw console commands\n"
                      "• Control game settings (dinosaurs, AI, whitelist, chat)\n"
                      "• Evrima-specific features (corpse cleanup, humans toggle)\n\n"
                      "*The panel provides an organized interface with categorized dropdown selections.*",
                inline=False
            )

        # Show individual commands if available
        if visible:
            # Group commands by category
            categories = {
                "Server Management": [
                    'rcon_addserver', 'rcon_servers', 'rcon_removeserver', 'rcon_test'
                ],
                "Player Management": [
                    'rcon_kick', 'rcon_ban', 'rcon_announce', 'rcon_dm',
                    'rcon_players', 'rcon_console'
                ],
                "Server Control": [
                    'rcon_save', 'rcon_wipecorpses', 'rcon_allowdinos'
                ],
                "Whitelist": [
                    'rcon_whitelist', 'rcon_whitelistadd', 'rcon_whitelistremove'
                ],
                "Game Settings (Evrima)": [
                    'rcon_globalchat', 'rcon_togglehumans', 'rcon_toggleai',
                    'rcon_disableai', 'rcon_aidensity'
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
                        # Remove 'rcon_' prefix for display
                        display_name = cmd.replace('rcon_', '')
                        desc = COMMAND_DESCRIPTIONS.get(cmd, '')
                        # Remove [Premium] prefix from description
                        desc = desc.replace('[Premium] ', '')
                        cmd_lines.append(f"`/rcon {display_name}` - {desc}")

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

    # ==========================================
    # AUTOCOMPLETE
    # ==========================================

    @remove_server.autocomplete('server')
    @test_connection.autocomplete('server')
    @kick_player.autocomplete('server')
    @ban_player.autocomplete('server')
    @announce.autocomplete('server')
    @list_players.autocomplete('server')
    @dm_player.autocomplete('server')
    @console_command.autocomplete('server')
    @save_server.autocomplete('server')
    @wipe_corpses.autocomplete('server')
    @allow_dinos.autocomplete('server')
    @toggle_whitelist.autocomplete('server')
    @whitelist_add.autocomplete('server')
    @whitelist_remove.autocomplete('server')
    @toggle_global_chat.autocomplete('server')
    @toggle_humans.autocomplete('server')
    @toggle_ai.autocomplete('server')
    @disable_ai.autocomplete('server')
    @ai_density.autocomplete('server')
    async def server_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str
    ) -> list[app_commands.Choice[str]]:
        """Autocomplete for server names."""
        try:
            servers = RCONServerQueries.get_servers(interaction.guild_id, active_only=False)
            choices = [app_commands.Choice(name="All Servers", value="all")]
            choices.extend([
                app_commands.Choice(
                    name=f"{s['server_name']} {'(Default)' if s['is_default'] else ''}".strip(),
                    value=s['server_name']
                )
                for s in servers
            ])
            return [c for c in choices if current.lower() in c.name.lower()][:25]
        except Exception:
            return []

    # ==========================================
    # HELPER METHODS
    # ==========================================

    def _get_target_servers(self, guild_id: int, server_name: Optional[str]) -> list[dict]:
        """Get target servers based on server name parameter."""
        if server_name and server_name.lower() == 'all':
            return RCONServerQueries.get_servers(guild_id)
        elif server_name:
            server = RCONServerQueries.get_server_by_name(guild_id, server_name)
            return [server] if server else []
        else:
            # Default behavior: all servers
            return RCONServerQueries.get_servers(guild_id)

    def _validate_game_type(self, servers: list[dict], required_game: str) -> tuple[bool, str]:
        """Validate that all servers are the required game type.

        Args:
            servers: List of server configs
            required_game: Required game type ('the_isle_evrima' or 'path_of_titans')

        Returns:
            (is_valid, error_message) tuple
        """
        game_names = {
            'the_isle_evrima': 'The Isle Evrima',
            'path_of_titans': 'Path of Titans'
        }

        invalid_servers = [
            s for s in servers
            if s.get('game_type') != required_game
        ]

        if invalid_servers:
            invalid_names = [s['server_name'] for s in invalid_servers]
            game_display = game_names.get(required_game, required_game)
            return False, (
                f"This command only works on **{game_display}** servers.\n\n"
                f"The following server(s) are not compatible:\n"
                + "\n".join(f"• {name}" for name in invalid_names)
            )

        return True, ""

    def _build_results_embed(self, title: str, results: dict, servers: list) -> discord.Embed:
        """Build an embed showing results from multiple servers."""
        success_count = sum(1 for r in results.values() if r.success)
        total = len(results)

        color = discord.Color.green() if success_count == total else (
            discord.Color.orange() if success_count > 0 else discord.Color.red()
        )

        embed = discord.Embed(
            title=title,
            description=f"{success_count}/{total} servers successful",
            color=color
        )

        server_map = {s['id']: s['server_name'] for s in servers}

        for server_id, response in results.items():
            server_name = server_map.get(server_id, f"Server {server_id}")
            status = "Success" if response.success else f"Failed: {response.message}"
            embed.add_field(name=server_name, value=status, inline=False)

        return embed


async def setup(bot: commands.Bot):
    """Load the RCONCommands cog."""
    await bot.add_cog(RCONCommands(bot))
