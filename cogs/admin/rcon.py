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
    GuildQueries, RCONServerQueries, RCONCommandLogQueries,
    VerificationCodeQueries, GuildRCONSettingsQueries, PlayerQueries
)
from services.permissions import require_permission
from services.rcon import get_rcon_client, GameType, RCONManager, rcon_manager
import logging
from typing import Optional

logger = logging.getLogger(__name__)


# Game type choices for dropdowns
GAME_CHOICES = [
    discord.SelectOption(label="The Isle Evrima", value="the_isle_evrima", description="The Isle Evrima RCON"),
    discord.SelectOption(label="Path of Titans", value="path_of_titans", description="Path of Titans RCON"),
]


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


class AllowDinosModal(discord.ui.Modal, title="Update Playable Dinosaurs"):
    """Modal for updating playable dinosaurs."""

    dino_list = discord.ui.TextInput(
        label="Dinosaur Names (one per line)",
        placeholder="Tyrannosaurus\nTriceratops\nStegosaurus",
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

            results = await rcon_manager.execute_on_servers(self.servers, 'update_playables', dino_str)
            embed = self.cog._build_results_embed("Update Playables Results", results, self.servers)

            embed.insert_field_at(
                0,
                name="Dinosaurs Allowed",
                value=f"```{chr(10).join(lines[:20])}{'...' if len(lines) > 20 else ''}```",
                inline=False
            )

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Error in AllowDinosModal: {e}", exc_info=True)
            await interaction.followup.send(f"An error occurred: {e}", ephemeral=True)


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


class RCONCommands(commands.GroupCog, name="rcon"):
    """RCON server management commands."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        super().__init__()

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
    @app_commands.describe(
        player_id="Player's game ID",
        message="Message to send",
        server="Target server (leave empty for first available)"
    )
    async def dm_player(
        self,
        interaction: discord.Interaction,
        player_id: str,
        message: str,
        server: str = None
    ):
        """Send a direct message to a player in-game."""
        if not await require_permission(interaction, 'rcon_dm'):
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

            response = await client.dm(player_id, message)

            if response.success:
                await interaction.followup.send(
                    f"Message sent to `{player_id}` on {server_config['server_name']}",
                    ephemeral=True
                )
            else:
                await interaction.followup.send(
                    f"Failed to send message: {response.message}",
                    ephemeral=True
                )

        except Exception as e:
            logger.error(f"Error sending DM: {e}", exc_info=True)
            await interaction.followup.send(
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
        """Update playable dinosaurs list using a modal."""
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

            # Open modal for dinosaur list input
            modal = AllowDinosModal(self, servers)
            await interaction.response.send_modal(modal)

        except Exception as e:
            logger.error(f"Error opening allowdinos modal: {e}", exc_info=True)
            await interaction.response.send_message(f"An error occurred: {e}", ephemeral=True)

    @app_commands.command(name="whitelist", description="Toggle server whitelist on/off (Evrima only)")
    @app_commands.guild_only()
    @app_commands.describe(
        enabled="Enable or disable whitelist",
        server="Server to configure"
    )
    @app_commands.choices(enabled=[
        app_commands.Choice(name="Enable", value=1),
        app_commands.Choice(name="Disable", value=0),
    ])
    async def toggle_whitelist(self, interaction: discord.Interaction, enabled: int, server: str = None):
        """Toggle whitelist."""
        if not await require_permission(interaction, 'rcon_whitelist'):
            return

        await interaction.response.defer(ephemeral=True)

        try:
            servers = self._get_target_servers(interaction.guild_id, server)
            if not servers:
                await interaction.followup.send("No servers configured.", ephemeral=True)
                return

            # Validate game type
            is_valid, error_msg = self._validate_game_type(servers, 'the_isle_evrima')
            if not is_valid:
                await interaction.followup.send(error_msg, ephemeral=True)
                return

            results = await rcon_manager.execute_on_servers(servers, 'toggle_whitelist', bool(enabled))
            embed = self._build_results_embed("Whitelist Toggle Results", results, servers)

            # Add what was changed
            embed.insert_field_at(
                0,
                name="Action",
                value=f"Whitelist **{'Enabled' if enabled else 'Disabled'}**",
                inline=False
            )

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Error toggling whitelist: {e}", exc_info=True)
            await interaction.followup.send(f"An error occurred: {e}", ephemeral=True)

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
    @app_commands.describe(
        enabled="Enable or disable global chat",
        server="Server to configure"
    )
    @app_commands.choices(enabled=[
        app_commands.Choice(name="Enable", value=1),
        app_commands.Choice(name="Disable", value=0),
    ])
    async def toggle_global_chat(self, interaction: discord.Interaction, enabled: int, server: str = None):
        """Toggle global chat."""
        if not await require_permission(interaction, 'rcon_globalchat'):
            return

        await interaction.response.defer(ephemeral=True)

        try:
            servers = self._get_target_servers(interaction.guild_id, server)
            if not servers:
                await interaction.followup.send("No servers configured.", ephemeral=True)
                return

            results = await rcon_manager.execute_on_servers(servers, 'toggle_global_chat', bool(enabled))
            embed = self._build_results_embed("Global Chat Toggle Results", results, servers)

            # Show what was changed
            embed.insert_field_at(
                0,
                name="Action",
                value=f"Global Chat **{'Enabled' if enabled else 'Disabled'}**",
                inline=False
            )

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Error toggling global chat: {e}", exc_info=True)
            await interaction.followup.send(f"An error occurred: {e}", ephemeral=True)

    @app_commands.command(name="togglehumans", description="Toggle human players on/off (Evrima only)")
    @app_commands.guild_only()
    @app_commands.describe(
        enabled="Enable or disable humans",
        server="Server to configure"
    )
    @app_commands.choices(enabled=[
        app_commands.Choice(name="Enable", value=1),
        app_commands.Choice(name="Disable", value=0),
    ])
    async def toggle_humans(self, interaction: discord.Interaction, enabled: int, server: str = None):
        """Toggle humans."""
        if not await require_permission(interaction, 'rcon_togglehumans'):
            return

        await interaction.response.defer(ephemeral=True)

        try:
            servers = self._get_target_servers(interaction.guild_id, server)
            if not servers:
                await interaction.followup.send("No servers configured.", ephemeral=True)
                return

            results = await rcon_manager.execute_on_servers(servers, 'toggle_humans', bool(enabled))
            embed = self._build_results_embed("Toggle Humans Results", results, servers)

            # Show what was changed
            embed.insert_field_at(
                0,
                name="Action",
                value=f"Human Players **{'Enabled' if enabled else 'Disabled'}**",
                inline=False
            )

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Error toggling humans: {e}", exc_info=True)
            await interaction.followup.send(f"An error occurred: {e}", ephemeral=True)

    @app_commands.command(name="toggleai", description="Toggle AI on/off (Evrima only)")
    @app_commands.guild_only()
    @app_commands.describe(
        enabled="Enable or disable AI",
        server="Server to configure"
    )
    @app_commands.choices(enabled=[
        app_commands.Choice(name="Enable", value=1),
        app_commands.Choice(name="Disable", value=0),
    ])
    async def toggle_ai(self, interaction: discord.Interaction, enabled: int, server: str = None):
        """Toggle AI."""
        if not await require_permission(interaction, 'rcon_toggleai'):
            return

        await interaction.response.defer(ephemeral=True)

        try:
            servers = self._get_target_servers(interaction.guild_id, server)
            if not servers:
                await interaction.followup.send("No servers configured.", ephemeral=True)
                return

            results = await rcon_manager.execute_on_servers(servers, 'toggle_ai', bool(enabled))
            embed = self._build_results_embed("Toggle AI Results", results, servers)

            # Show what was changed
            embed.insert_field_at(
                0,
                name="Action",
                value=f"AI Spawns **{'Enabled' if enabled else 'Disabled'}**",
                inline=False
            )

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Error toggling AI: {e}", exc_info=True)
            await interaction.followup.send(f"An error occurred: {e}", ephemeral=True)

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
    # VERIFICATION
    # ==========================================

    @app_commands.command(name="startverify", description="Start RCON verification process")
    @app_commands.guild_only()
    @app_commands.describe(
        player_id="Your in-game ID (Steam ID or Alderon ID)",
        game="Game type"
    )
    @app_commands.choices(game=[
        app_commands.Choice(name="The Isle Evrima", value="the_isle_evrima"),
        app_commands.Choice(name="Path of Titans", value="path_of_titans"),
    ])
    async def start_verify(
        self,
        interaction: discord.Interaction,
        player_id: str,
        game: app_commands.Choice[str]
    ):
        """Start the RCON verification process."""
        await interaction.response.defer(ephemeral=True)

        try:
            settings = GuildRCONSettingsQueries.get_or_create_settings(interaction.guild_id)
            if not settings.get('verification_enabled', True):
                await interaction.followup.send(
                    "RCON verification is not enabled on this server.",
                    ephemeral=True
                )
                return

            # Get default server for this game type
            servers = RCONServerQueries.get_servers(interaction.guild_id)
            server_config = next(
                (s for s in servers if s['game_type'] == game.value),
                None
            )

            if not server_config:
                await interaction.followup.send(
                    f"No {game.name} server configured.",
                    ephemeral=True
                )
                return

            # Determine ID type
            steam_id = player_id if len(player_id) == 17 and player_id.isdigit() else None
            alderon_id = player_id if '-' in player_id else None

            # Generate verification code
            timeout = settings.get('verification_timeout_minutes', 10)
            code = VerificationCodeQueries.create_code(
                guild_id=interaction.guild_id,
                user_id=interaction.user.id,
                game_type=game.value,
                target_steam_id=steam_id,
                target_alderon_id=alderon_id,
                server_id=server_config['id'],
                timeout_minutes=timeout
            )

            # Send code to player in-game
            client = get_rcon_client(
                server_config['game_type'],
                server_config['host'],
                server_config['port'],
                server_config['password']
            )

            dm_message = f"Your Discord verification code is: {code} - Use /rcon verify {code} on Discord"
            response = await client.dm(player_id, dm_message)

            if response.success:
                embed = discord.Embed(
                    title="Verification Code Sent",
                    description=f"A verification code has been sent to you in-game.",
                    color=discord.Color.blue()
                )
                embed.add_field(
                    name="Next Step",
                    value=f"Check your in-game messages and run `/rcon verify <code>`\n"
                          f"The code expires in {timeout} minutes.",
                    inline=False
                )
                embed.add_field(name="Server", value=server_config['server_name'], inline=True)
                embed.add_field(name="Player ID", value=f"`{player_id}`", inline=True)
            else:
                embed = discord.Embed(
                    title="Verification Failed",
                    description="Could not send verification code in-game.",
                    color=discord.Color.red()
                )
                embed.add_field(
                    name="Reason",
                    value=f"{response.message}\n\nMake sure you are online on the server.",
                    inline=False
                )

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Error starting verification: {e}", exc_info=True)
            await interaction.followup.send(
                f"An error occurred: {e}",
                ephemeral=True
            )

    @app_commands.command(name="verify", description="Complete RCON verification with your code")
    @app_commands.guild_only()
    @app_commands.describe(code="The verification code from in-game")
    async def verify(self, interaction: discord.Interaction, code: str):
        """Complete RCON verification."""
        await interaction.response.defer(ephemeral=True)

        try:
            record = VerificationCodeQueries.verify_code(interaction.guild_id, code.upper())

            if not record:
                await interaction.followup.send(
                    "Invalid or expired verification code. Please try again with `/rcon startverify`.",
                    ephemeral=True
                )
                return

            # Check user matches
            if record['user_id'] != interaction.user.id:
                await interaction.followup.send(
                    "This verification code was not generated for your account.",
                    ephemeral=True
                )
                return

            # Mark as verified
            VerificationCodeQueries.mark_verified(record['id'])

            # Link the player ID
            if record['target_steam_id']:
                PlayerQueries.link_steam(
                    guild_id=interaction.guild_id,
                    user_id=interaction.user.id,
                    username=str(interaction.user),
                    steam_id=record['target_steam_id'],
                    steam_name=f"Verified via RCON"
                )
            elif record['target_alderon_id']:
                PlayerQueries.link_alderon(
                    guild_id=interaction.guild_id,
                    user_id=interaction.user.id,
                    username=str(interaction.user),
                    player_id=record['target_alderon_id'],
                    player_name=f"Verified via RCON"
                )

            embed = discord.Embed(
                title="Verification Complete",
                description="Your game account has been linked and verified!",
                color=discord.Color.green()
            )

            if record['target_steam_id']:
                embed.add_field(name="Steam ID", value=f"`{record['target_steam_id']}`", inline=True)
            if record['target_alderon_id']:
                embed.add_field(name="Alderon ID", value=f"`{record['target_alderon_id']}`", inline=True)

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Error verifying: {e}", exc_info=True)
            await interaction.followup.send(
                f"An error occurred: {e}",
                ephemeral=True
            )

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
