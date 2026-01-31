# cogs/admin/serverlogs.py
"""
Server Log Monitoring Commands (Premium)

Commands for monitoring game server logs via SFTP:
- Configure SFTP connections
- Set up log channels (chat, kills, admin)
- Start/stop log monitoring
- View monitoring status
"""

import discord
from discord import app_commands
from discord.ext import commands, tasks
from database.queries import (
    GuildQueries, SFTPConfigQueries, LogChannelQueries,
    LogMonitorStateQueries, GuildRCONSettingsQueries, VerificationCodeQueries,
    PlayerQueries, AuditQueries
)
from services.permissions import require_permission
from services.sftp_logs import (
    SFTPLogReader, LogMonitor, log_monitor_manager, LogType,
    GameLogType, ChatLogEntry, KillLogEntry, AdminLogEntry
)
from services.game_ini_cache import GameIniAdminCache
# Import enhanced parser events
try:
    from services.log_parsers import (
        PlayerLoginEvent, PlayerLogoutEvent, PlayerChatEvent,
        AdminCommandEvent, RCONCommandEvent, PlayerDeathEvent, LogType as EnhancedLogType
    )
    from services.log_embed_builder import (
        build_player_login_embed, build_player_logout_embed,
        build_player_chat_embed, build_admin_command_embed,
        build_rcon_command_embed, build_player_death_embed
    )
    ENHANCED_LOGS_AVAILABLE = True
except ImportError:
    ENHANCED_LOGS_AVAILABLE = False

import logging
from typing import Optional, Literal

logger = logging.getLogger(__name__)


class SFTPSetupModal(discord.ui.Modal, title="Configure SFTP Connection"):
    """Modal for SFTP configuration."""

    config_name = discord.ui.TextInput(
        label="Configuration Name",
        placeholder="e.g., Main Server Logs",
        required=True,
        max_length=100
    )

    host = discord.ui.TextInput(
        label="SFTP Host/URL",
        placeholder="sftp://node1.example.com:2022 OR just node1.example.com",
        required=True,
        max_length=255
    )

    port = discord.ui.TextInput(
        label="SFTP Port (leave blank if in URL above)",
        placeholder="22, 2022, or leave blank",
        required=False,
        max_length=5
    )

    username = discord.ui.TextInput(
        label="SFTP Username",
        placeholder="Your SFTP username",
        required=True,
        max_length=100
    )

    password = discord.ui.TextInput(
        label="SFTP Password",
        placeholder="Your SFTP password",
        required=True,
        max_length=512,
        style=discord.TextStyle.short
    )

    def __init__(self, game_type: str, game_display: str):
        super().__init__(title=f"Configure {game_display} SFTP")
        self.game_type = game_type
        self.game_display = game_display
        # Set default port
        self.port.default = "22"

    async def on_submit(self, interaction: discord.Interaction):
        try:
            # Parse host and port from input
            # Handle formats: "sftp://host:port", "host:port", or just "host"
            host_input = self.host.value.strip()
            port_input = self.port.value.strip()

            # Remove sftp:// prefix if present
            if host_input.startswith('sftp://'):
                host_input = host_input[7:]  # Remove 'sftp://'

            # Check if port is in the host string (e.g., "host:2022")
            if ':' in host_input:
                host_parts = host_input.split(':')
                hostname = host_parts[0]
                try:
                    port_from_host = int(host_parts[1])
                    # Use port from host if port field is empty
                    port_num = port_from_host if not port_input else int(port_input)
                except (ValueError, IndexError):
                    await interaction.response.send_message(
                        "❌ Invalid port in host URL. Please check the format.",
                        ephemeral=True
                    )
                    return
            else:
                hostname = host_input
                # Use port from field, default to 22 if empty
                if port_input:
                    try:
                        port_num = int(port_input)
                    except ValueError:
                        await interaction.response.send_message(
                            "❌ Invalid port number. Please enter a number between 1 and 65535.",
                            ephemeral=True
                        )
                        return
                else:
                    port_num = 22  # Default SFTP port

            # Validate port range
            if not (1 <= port_num <= 65535):
                await interaction.response.send_message(
                    "❌ Port number must be between 1 and 65535.",
                    ephemeral=True
                )
                return

            await interaction.response.defer(ephemeral=True)

            # Ensure guild exists
            GuildQueries.get_or_create(interaction.guild_id, interaction.guild.name)

            # Test connection
            reader = SFTPLogReader(
                hostname,
                port_num,
                self.username.value,
                self.password.value,
                GameLogType(self.game_type)
            )
            success, message = await reader.test_connection()

            if not success:
                await interaction.followup.send(
                    f"❌ **SFTP Connection Failed**\n"
                    f"```\n{message}\n```\n"
                    "Please check your credentials and try again.",
                    ephemeral=True
                )
                return

            # Check for duplicate name
            existing = SFTPConfigQueries.get_active_configs(interaction.guild_id)
            if any(c['config_name'] == self.config_name.value for c in existing):
                await interaction.followup.send(
                    f"❌ A configuration named `{self.config_name.value}` already exists. Choose a different name.",
                    ephemeral=True
                )
                return

            # Save configuration
            config_id = SFTPConfigQueries.add_config(
                guild_id=interaction.guild_id,
                config_name=self.config_name.value,
                host=hostname,
                port=port_num,
                username=self.username.value,
                password=self.password.value,
                game_type=self.game_type
            )

            embed = discord.Embed(
                title="✅ SFTP Configuration Added",
                description=f"Configuration `{self.config_name.value}` saved successfully.",
                color=discord.Color.green()
            )
            embed.add_field(name="Host", value=f"`{hostname}:{port_num}`", inline=True)
            embed.add_field(name="Game", value=self.game_display, inline=True)
            embed.add_field(name="Config ID", value=str(config_id), inline=True)
            # Game-specific next steps
            if self.game_type == 'the_isle_evrima':
                next_steps = (
                    "1️⃣ Set log file path with `/logs setpath`\n"
                    "   Example: `/home/container/TheIsle/Saved/Logs/TheIsle.log`\n"
                    "2️⃣ Set output channels with `/logs setchannel`\n"
                    "3️⃣ Start monitoring with `/logs start`\n\n"
                    "💡 The Isle uses **one file** for all logs (chat, kills, admin)"
                )
            else:
                next_steps = (
                    "1️⃣ Set log file path with `/logs setpath`\n"
                    "2️⃣ Set output channels with `/logs setchannel`\n"
                    "3️⃣ Start monitoring with `/logs start`"
                )

            embed.add_field(
                name="📋 Next Steps",
                value=next_steps,
                inline=False
            )
            embed.set_footer(text="Connection test successful")

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Error in SFTP setup modal: {e}", exc_info=True)
            try:
                await interaction.followup.send(
                    f"❌ An error occurred: {e}",
                    ephemeral=True
                )
            except:
                await interaction.response.send_message(
                    f"❌ An error occurred: {e}",
                    ephemeral=True
                )


class SetChannelsView(discord.ui.View):
    """View with channel dropdowns for log configuration."""

    def __init__(self, guild: discord.Guild, current_channels: Optional[dict] = None):
        super().__init__(timeout=300)
        self.guild = guild
        self.current_channels = current_channels or {}
        self.selected_channels = {}

        # Get all text channels
        text_channels = [ch for ch in guild.channels if isinstance(ch, discord.TextChannel)]

        if not text_channels:
            return

        # Create options with "None (Disable)" as first option
        def create_options(selected_id: Optional[int] = None):
            options = [
                discord.SelectOption(
                    label="None (Disable)",
                    value="none",
                    description="Disable this log type",
                    default=(selected_id is None)
                )
            ]

            for ch in sorted(text_channels, key=lambda c: c.position)[:24]:  # Max 25 options, we use 1 for "None"
                is_default = (selected_id == ch.id)
                options.append(
                    discord.SelectOption(
                        label=f"#{ch.name}",
                        value=str(ch.id),
                        description=f"Category: {ch.category.name if ch.category else 'No category'}",
                        default=is_default
                    )
                )
            return options

        # Helper to create placeholder with numbering
        def get_numbered_placeholder(number: int, channel_id):
            if channel_id:
                channel = guild.get_channel(channel_id)
                if channel:
                    return f"[{number}] is set to #{channel.name}"
            return f"[{number}] Set Position {number} or Leave on None (Disable)"

        # Player Login & Logout (Combined) Select
        # Use login channel as primary, fallback to logout if different (though should be same)
        login_logout_current = current_channels.get('player_login_channel_id') or current_channels.get('player_logout_channel_id')
        login_logout_select = discord.ui.Select(
            placeholder=get_numbered_placeholder(1, login_logout_current),
            options=create_options(login_logout_current),
            row=0
        )
        login_logout_select.callback = lambda i: self._on_select(i, 'player_login_logout')
        self.add_item(login_logout_select)

        # Player Chat Select
        chat_current = current_channels.get('player_chat_channel_id')
        chat_select = discord.ui.Select(
            placeholder=get_numbered_placeholder(2, chat_current),
            options=create_options(chat_current),
            row=1
        )
        chat_select.callback = lambda i: self._on_select(i, 'player_chat')
        self.add_item(chat_select)

        # Admin Command Select
        admin_current = current_channels.get('admin_command_channel_id')
        admin_select = discord.ui.Select(
            placeholder=get_numbered_placeholder(3, admin_current),
            options=create_options(admin_current),
            row=2
        )
        admin_select.callback = lambda i: self._on_select(i, 'admin_command')
        self.add_item(admin_select)

        # Player Death Select
        death_current = current_channels.get('player_death_channel_id')
        death_select = discord.ui.Select(
            placeholder=get_numbered_placeholder(4, death_current),
            options=create_options(death_current),
            row=3
        )
        death_select.callback = lambda i: self._on_select(i, 'player_death')
        self.add_item(death_select)

        # RCON Command Select
        rcon_current = current_channels.get('rcon_command_channel_id')
        rcon_select = discord.ui.Select(
            placeholder=get_numbered_placeholder(5, rcon_current),
            options=create_options(rcon_current),
            row=4
        )
        rcon_select.callback = lambda i: self._on_select(i, 'rcon_command')
        self.add_item(rcon_select)

    async def _on_select(self, interaction: discord.Interaction, log_type: str):
        """Handle channel selection and auto-save."""
        try:
            selected_value = interaction.data['values'][0]

            # Build the update dict
            channels_to_update = {}

            # Handle combined login/logout type
            if log_type == 'player_login_logout':
                if selected_value == "none":
                    channels_to_update['player_login'] = None
                    channels_to_update['player_logout'] = None
                    self.selected_channels['player_login'] = None
                    self.selected_channels['player_logout'] = None
                else:
                    ch_id = int(selected_value)
                    channels_to_update['player_login'] = ch_id
                    channels_to_update['player_logout'] = ch_id
                    self.selected_channels['player_login'] = ch_id
                    self.selected_channels['player_logout'] = ch_id
            else:
                if selected_value == "none":
                    channels_to_update[log_type] = None
                    self.selected_channels[log_type] = None
                else:
                    ch_id = int(selected_value)
                    channels_to_update[log_type] = ch_id
                    self.selected_channels[log_type] = ch_id

            # Auto-save to database immediately
            for update_type, channel_id in channels_to_update.items():
                if channel_id is not None:
                    LogChannelQueries.set_channel(interaction.guild_id, update_type, channel_id)
                else:
                    # To disable, we need to set it to NULL - use set_multiple_channels
                    LogChannelQueries.set_multiple_channels(interaction.guild_id, {update_type: 0})  # 0 will be treated as NULL

            # Build feedback message
            type_emoji = {
                'player_login': '🟢',
                'player_logout': '🔴',
                'player_login_logout': '🟢🔴',
                'player_chat': '💬',
                'admin_command': '⚡',
                'player_death': '☠️',
                'rcon_command': '🤖'
            }
            emoji = type_emoji.get(log_type, '📝')

            # Friendly names
            friendly_names = {
                'player_login_logout': 'Player Login & Logout'
            }
            friendly_name = friendly_names.get(log_type, log_type.replace('_', ' ').title())

            if selected_value == "none":
                response_text = f"{emoji} **{friendly_name}** disabled"
            else:
                channel = self.guild.get_channel(int(selected_value))
                response_text = f"{emoji} **{friendly_name}** → {channel.mention if channel else 'Unknown Channel'}"

            await interaction.response.send_message(
                f"✅ {response_text}",
                ephemeral=True,
                delete_after=3
            )

        except Exception as e:
            logger.error(f"Error in channel selection: {e}", exc_info=True)
            await interaction.response.send_message(
                f"❌ Error: {e}",
                ephemeral=True
            )


class ServerLogsCommands(commands.GroupCog, name="logs"):
    """Server log monitoring commands."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._active_monitors: dict[int, int] = {}  # guild_id -> sftp_config_id
        self._posted_logs: set[str] = set()  # Cache of recently posted log identifiers (timestamp + hash)
        self._cache_max_size = 1000  # Maximum cached entries
        super().__init__()

    async def _load_game_ini_admins(self, guild_id: int, config: dict) -> None:
        """
        Load admin Steam IDs from Game.ini and cache them.

        Args:
            guild_id: Discord guild ID
            config: SFTP configuration dict
        """
        try:
            # Determine Game.ini path
            # For The Isle: TheIsle/Saved/Config/LinuxServer/Game.ini
            admin_log_path = config.get('admin_log_path', '')
            if 'TheIsle' in admin_log_path:
                game_ini_path = admin_log_path.replace('Logs/TheIsle.log', 'Config/LinuxServer/Game.ini')
            else:
                # Fallback path
                game_ini_path = 'TheIsle/Saved/Config/LinuxServer/Game.ini'

            logger.debug(f"Guild {guild_id}: Loading Game.ini from {game_ini_path}")

            # Create temporary SFTP reader to fetch Game.ini
            reader = SFTPLogReader(
                config['host'],
                config['port'],
                config['username'],
                config['password'],
                GameLogType(config['game_type'])
            )

            await reader.connect()

            # Read Game.ini file
            import asyncio
            def _read_file():
                try:
                    with reader._sftp.open(game_ini_path, 'r') as f:
                        content = f.read()
                        if isinstance(content, bytes):
                            content = content.decode('utf-8', errors='ignore')
                        return content
                except FileNotFoundError:
                    logger.warning(f"Guild {guild_id}: Game.ini not found at {game_ini_path}")
                    return None
                except Exception as e:
                    logger.error(f"Guild {guild_id}: Error reading Game.ini: {e}")
                    return None

            content = await asyncio.to_thread(_read_file)
            await reader.disconnect()

            if content:
                # Parse admin Steam IDs from Game.ini
                admin_ids = GameIniAdminCache.parse_game_ini_content(content)
                GameIniAdminCache.set_admin_ids(guild_id, admin_ids)
                logger.info(f"Guild {guild_id}: Loaded {len(admin_ids)} admin Steam IDs from Game.ini")
            else:
                logger.warning(f"Guild {guild_id}: Could not load Game.ini")

        except Exception as e:
            logger.error(f"Guild {guild_id}: Failed to load Game.ini admins: {e}", exc_info=True)

    async def cog_load(self):
        """Called when the cog is loaded."""
        # Start the log processor loop
        self.process_logs.start()
        # Start auto-resume task
        self.auto_resume_monitoring.start()

    async def cog_unload(self):
        """Called when the cog is unloaded."""
        self.process_logs.cancel()
        self.auto_resume_monitoring.cancel()
        await log_monitor_manager.stop_all()

    @tasks.loop(count=1)
    async def auto_resume_monitoring(self):
        """Auto-resume log monitoring for all configured guilds on bot startup."""
        await self.bot.wait_until_ready()

        logger.info("Auto-resuming log monitoring for configured guilds...")

        # Get all guilds with active SFTP configs and channel configs
        try:
            from database.connection import get_cursor

            with get_cursor() as cursor:
                cursor.execute("""
                    SELECT DISTINCT s.guild_id, s.id as config_id
                    FROM server_sftp_config s
                    INNER JOIN guild_log_channels c ON s.guild_id = c.guild_id
                    WHERE s.is_active = TRUE
                    AND (c.player_login_channel_id IS NOT NULL
                         OR c.player_logout_channel_id IS NOT NULL
                         OR c.player_chat_channel_id IS NOT NULL
                         OR c.admin_command_channel_id IS NOT NULL
                         OR c.player_death_channel_id IS NOT NULL
                         OR c.chatlog_channel_id IS NOT NULL
                         OR c.adminlog_channel_id IS NOT NULL
                         OR c.killfeed_channel_id IS NOT NULL)
                """)
                guild_configs = cursor.fetchall()

            for row in guild_configs:
                guild_id = row['guild_id']
                config_id = row['config_id']

                # Skip if already monitoring
                if guild_id in self._active_monitors:
                    continue

                try:
                    # Get full config
                    config = SFTPConfigQueries.get_config(config_id, guild_id)
                    if not config:
                        continue

                    # Check if unified log path is set
                    log_path = config.get('chat_log_path')
                    if not log_path:
                        logger.debug(f"Guild {guild_id}: No log path set, skipping auto-resume")
                        continue

                    # Start monitoring
                    from services.sftp_logs import log_monitor_manager, LogType

                    monitor = log_monitor_manager.create_monitor(
                        config_id,
                        host=config['host'],
                        port=config['port'],
                        username=config['username'],
                        password=config['password'],
                        game_type=config['game_type'],
                        unified_mode=True,
                        server_name=config.get('config_name', 'Unknown Server')
                    )

                    # Add unified log file with saved position
                    if config['game_type'] == 'the_isle_evrima':
                        state = LogMonitorStateQueries.get_state(config_id, 'admin')
                        monitor.add_file(
                            log_path,
                            LogType.ADMIN,
                            initial_position=state['last_position'] if state else 0,
                            initial_hash=state['last_line_hash'] if state else ""
                        )

                    # Register callbacks
                    monitor.on_log(LogType.CHAT, lambda e, gid=guild_id, cid=config_id: self._queue_log_entry(gid, cid, e))
                    monitor.on_log(LogType.KILL, lambda e, gid=guild_id, cid=config_id: self._queue_log_entry(gid, cid, e))
                    monitor.on_log(LogType.ADMIN, lambda e, gid=guild_id, cid=config_id: self._queue_log_entry(gid, cid, e))

                    settings = GuildRCONSettingsQueries.get_or_create_settings(guild_id)
                    poll_interval = settings.get('log_poll_interval_seconds', 30)

                    await monitor.start(poll_interval)
                    self._active_monitors[guild_id] = config_id

                    # Load Game.ini admin list
                    await self._load_game_ini_admins(guild_id, config)

                    logger.info(f"Auto-resumed log monitoring for guild {guild_id}")

                except Exception as e:
                    logger.error(f"Failed to auto-resume monitoring for guild {guild_id}: {e}", exc_info=True)

            logger.info(f"Auto-resume complete: {len(self._active_monitors)} guilds monitoring")

        except Exception as e:
            logger.error(f"Error in auto-resume monitoring: {e}", exc_info=True)

    # ==========================================
    # SFTP CONFIGURATION
    # ==========================================

    @app_commands.command(name="setup", description="Configure SFTP connection for log monitoring")
    @app_commands.guild_only()
    @app_commands.describe(
        game="Game type for log parsing"
    )
    async def setup_sftp(
        self,
        interaction: discord.Interaction,
        game: Literal["the_isle_evrima", "path_of_titans"]
    ):
        """Configure SFTP connection for log monitoring."""
        if not await require_permission(interaction, 'logs_setup'):
            return

        # Convert game type to display name
        game_display = "The Isle Evrima" if game == "the_isle_evrima" else "Path of Titans"

        # Open the modal
        modal = SFTPSetupModal(game, game_display)
        await interaction.response.send_modal(modal)

    @app_commands.command(name="setpath", description="Set log file path (unified for The Isle)")
    @app_commands.guild_only()
    @app_commands.describe(
        config="SFTP configuration name",
        path="Full path to the log file (e.g., /home/container/TheIsle/Saved/Logs/TheIsle.log)"
    )
    async def set_log_path(
        self,
        interaction: discord.Interaction,
        config: str,
        path: str
    ):
        """
        Set the log file path.

        For The Isle Evrima: Sets a single unified log file for all log types.
        For Path of Titans: Would require separate setpath commands per type (future implementation).
        """
        if not await require_permission(interaction, 'logs_setup'):
            return

        try:
            configs = SFTPConfigQueries.get_active_configs(interaction.guild_id)
            sftp_config = next((c for c in configs if c['config_name'] == config), None)

            if not sftp_config:
                await interaction.response.send_message(
                    f"❌ Configuration `{config}` not found.",
                    ephemeral=True
                )
                return

            game_type = sftp_config.get('game_type', 'the_isle_evrima')

            from database.connection import get_cursor
            with get_cursor() as cursor:
                if game_type == 'the_isle_evrima':
                    # The Isle uses ONE unified log file for everything
                    # Set all three paths to the same file
                    cursor.execute(
                        """UPDATE server_sftp_config
                           SET chat_log_path = %s,
                               kill_log_path = %s,
                               admin_log_path = %s
                           WHERE id = %s""",
                        (path, path, path, sftp_config['id'])
                    )
                    message = f"✅ Set unified log path to:\n`{path}`\n\nAll log types (chat, kills, admin) will be read from this single file."
                else:
                    # Path of Titans uses separate files (future: make this more flexible)
                    cursor.execute(
                        "UPDATE server_sftp_config SET chat_log_path = %s WHERE id = %s",
                        (path, sftp_config['id'])
                    )
                    message = f"✅ Set chat log path to `{path}`"

            # Check if we can auto-start monitoring
            channels = LogChannelQueries.get_channels(interaction.guild_id)
            has_channels = any([
                channels.get('player_login_channel_id'),
                channels.get('player_logout_channel_id'),
                channels.get('player_chat_channel_id'),
                channels.get('admin_command_channel_id'),
                channels.get('player_death_channel_id'),
                # Fallback to legacy channels
                channels.get('chatlog_channel_id'),
                channels.get('killfeed_channel_id'),
                channels.get('adminlog_channel_id')
            ]) if channels else False

            # Auto-start if not already running
            if has_channels and interaction.guild_id not in self._active_monitors:
                try:
                    # Start monitoring automatically
                    from services.sftp_logs import log_monitor_manager, LogType

                    monitor = log_monitor_manager.create_monitor(
                        sftp_config['id'],
                        host=sftp_config['host'],
                        port=sftp_config['port'],
                        username=sftp_config['username'],
                        password=sftp_config['password'],
                        game_type=sftp_config['game_type'],
                        unified_mode=True,
                        server_name=sftp_config.get('config_name', 'Unknown Server')
                    )

                    # Add unified log file with saved position
                    if sftp_config['game_type'] == 'the_isle_evrima':
                        state = LogMonitorStateQueries.get_state(sftp_config['id'], 'admin')
                        monitor.add_file(
                            path,
                            LogType.ADMIN,
                            initial_position=state['last_position'] if state else 0,
                            initial_hash=state['last_line_hash'] if state else ""
                        )

                    # Register callbacks
                    monitor.on_log(LogType.CHAT, lambda e: self._queue_log_entry(
                        interaction.guild_id, sftp_config['id'], e
                    ))
                    monitor.on_log(LogType.KILL, lambda e: self._queue_log_entry(
                        interaction.guild_id, sftp_config['id'], e
                    ))
                    monitor.on_log(LogType.ADMIN, lambda e: self._queue_log_entry(
                        interaction.guild_id, sftp_config['id'], e
                    ))

                    settings = GuildRCONSettingsQueries.get_or_create_settings(interaction.guild_id)
                    poll_interval = settings.get('log_poll_interval_seconds', 30)

                    await monitor.start(poll_interval)
                    self._active_monitors[interaction.guild_id] = sftp_config['id']

                    # Load Game.ini admin list
                    await self._load_game_ini_admins(interaction.guild_id, sftp_config)

                    message += "\n\n✅ **Auto-started log monitoring!**\nLogs will now appear in your configured channels."
                except Exception as e:
                    logger.error(f"Failed to auto-start monitoring: {e}", exc_info=True)
                    message += "\n\n💡 **Tip:** Use `/logs start` to begin monitoring."
            elif has_channels:
                message += "\n\n💡 **Monitoring already active.**"
            else:
                message += "\n\n💡 **Tip:** Set channels with `/logs setchannel`, then monitoring will auto-start!"

            await interaction.response.send_message(message, ephemeral=True)

        except Exception as e:
            logger.error(f"Error setting log path: {e}", exc_info=True)
            await interaction.response.send_message(
                f"An error occurred: {e}",
                ephemeral=True
            )

    # ==========================================
    # CHANNEL CONFIGURATION
    # ==========================================

    @app_commands.command(name="setchannel", description="Configure Discord channels for log output")
    @app_commands.guild_only()
    async def set_channel(self, interaction: discord.Interaction):
        """Configure Discord channels for different log types using dropdowns."""
        if not await require_permission(interaction, 'logs_setchannel'):
            return

        # Get current channel configuration
        channels = LogChannelQueries.get_channels(interaction.guild_id)

        # Create view with channel dropdowns
        view = SetChannelsView(interaction.guild, channels)

        # Create embed with instructions
        embed = discord.Embed(
            title="📋 Configure Log Channels",
            description=(
                "Select the channel where you want each log type to go.\n"
                "**Changes save instantly when you select from the dropdowns!**\n\n"
                "**Available Log Types:**\n"
                "🟢🔴 **Player Login & Logout** - When players join and leave the server\n"
                "💬 **Player Chat** - Chat messages (Global, Admin, Spatial, etc.)\n"
                "⚡ **Admin Command** - In-game admin commands\n"
                "☠️ **Player Death** - Kill feed events\n"
                "🤖 **RCON Command** - Commands executed via Discord RCON\n\n"
                "💡 **Tip:** You can use the same channel for multiple log types!"
            ),
            color=discord.Color.blue()
        )

        if channels:
            current_config = []

            # Check if login and logout are set to the same channel
            login_ch_id = channels.get('player_login_channel_id')
            logout_ch_id = channels.get('player_logout_channel_id')

            if login_ch_id and logout_ch_id and login_ch_id == logout_ch_id:
                # Show combined entry
                channel = interaction.guild.get_channel(login_ch_id)
                if channel:
                    current_config.append(f"**[1]** 🟢🔴 Player Login & Logout: {channel.mention}")
            else:
                # Show separate entries if different or only one is set
                if login_ch_id:
                    channel = interaction.guild.get_channel(login_ch_id)
                    if channel:
                        current_config.append(f"**[1]** 🟢 Player Login: {channel.mention}")
                if logout_ch_id:
                    channel = interaction.guild.get_channel(logout_ch_id)
                    if channel:
                        current_config.append(f"**[1]** 🔴 Player Logout: {channel.mention}")

            # Player Chat
            chat_ch_id = channels.get('player_chat_channel_id')
            if chat_ch_id:
                channel = interaction.guild.get_channel(chat_ch_id)
                if channel:
                    current_config.append(f"**[2]** 💬 Player Chat: {channel.mention}")

            # Check if admin command and RCON command are set to the same channel
            admin_ch_id = channels.get('admin_command_channel_id')
            rcon_ch_id = channels.get('rcon_command_channel_id')

            if admin_ch_id and rcon_ch_id and admin_ch_id == rcon_ch_id:
                # Show combined entry
                channel = interaction.guild.get_channel(admin_ch_id)
                if channel:
                    current_config.append(f"**[3 & 5]** ⚡🤖 Admin Command & RCON Command: {channel.mention}")
            else:
                # Show separate entries if different or only one is set
                if admin_ch_id:
                    channel = interaction.guild.get_channel(admin_ch_id)
                    if channel:
                        current_config.append(f"**[3]** ⚡ Admin Command: {channel.mention}")

            # Player Death
            death_ch_id = channels.get('player_death_channel_id')
            if death_ch_id:
                channel = interaction.guild.get_channel(death_ch_id)
                if channel:
                    current_config.append(f"**[4]** ☠️ Player Death: {channel.mention}")

            # RCON Command (show separately if not combined with Admin Command above)
            if not (admin_ch_id and rcon_ch_id and admin_ch_id == rcon_ch_id):
                if rcon_ch_id:
                    channel = interaction.guild.get_channel(rcon_ch_id)
                    if channel:
                        current_config.append(f"**[5]** 🤖 RCON Command: {channel.mention}")

            if current_config:
                embed.add_field(
                    name="📌 Current Configuration",
                    value="\n".join(current_config),
                    inline=False
                )

        embed.set_footer(text="Select the channel with the dropdown that corresponds to the number • Dismiss when done")

        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    # ==========================================
    # MONITORING CONTROL
    # ==========================================

    @app_commands.command(name="start", description="Start log monitoring")
    @app_commands.guild_only()
    @app_commands.describe(config="SFTP configuration to monitor")
    async def start_monitoring(
        self,
        interaction: discord.Interaction,
        config: str
    ):
        """Start log monitoring for a configuration."""
        if not await require_permission(interaction, 'logs_start'):
            return

        await interaction.response.defer(ephemeral=True)

        try:
            configs = SFTPConfigQueries.get_active_configs(interaction.guild_id)
            sftp_config = next((c for c in configs if c['config_name'] == config), None)

            if not sftp_config:
                await interaction.followup.send(
                    f"Configuration `{config}` not found.",
                    ephemeral=True
                )
                return

            # Check if already monitoring
            if sftp_config['id'] in self._active_monitors.values():
                await interaction.followup.send(
                    f"Already monitoring `{config}`.",
                    ephemeral=True
                )
                return

            # Check channel configuration
            channels = LogChannelQueries.get_channels(interaction.guild_id)
            if not channels:
                await interaction.followup.send(
                    "No log channels configured. Use `/logs setchannel` first.",
                    ephemeral=True
                )
                return

            # Create and start monitor
            # Get game type from config
            game_type = GameLogType(sftp_config.get('game_type', 'the_isle_evrima'))

            # Check if this is a unified log file (all paths are the same)
            chat_path = sftp_config.get('chat_log_path')
            kill_path = sftp_config.get('kill_log_path')
            admin_path = sftp_config.get('admin_log_path')

            # Unified mode: all paths point to the same file (The Isle Evrima pattern)
            unified_mode = (chat_path and chat_path == kill_path == admin_path)

            monitor = log_monitor_manager.create_monitor(
                config_id=sftp_config['id'],
                host=sftp_config['host'],
                port=sftp_config['port'],
                username=sftp_config['username'],
                password=sftp_config['password'],
                game_type=game_type,
                unified_mode=unified_mode,
                server_name=sftp_config.get('config_name', 'Unknown Server')
            )

            # Add log files to monitor
            if unified_mode and chat_path:
                # Single unified log file - use 'chat' state for tracking position
                state = LogMonitorStateQueries.get_state(sftp_config['id'], 'chat')
                monitor.add_file(
                    chat_path,
                    log_type=None,  # None = unified mode, auto-detect types
                    initial_position=state['last_position'] if state else 0,
                    initial_hash=state['last_line_hash'] if state else ""
                )
            else:
                # Separate files for each log type
                if chat_path:
                    state = LogMonitorStateQueries.get_state(sftp_config['id'], 'chat')
                    monitor.add_file(
                        chat_path,
                        LogType.CHAT,
                        initial_position=state['last_position'] if state else 0,
                        initial_hash=state['last_line_hash'] if state else ""
                    )

                if kill_path and kill_path != chat_path:
                    state = LogMonitorStateQueries.get_state(sftp_config['id'], 'kill')
                    monitor.add_file(
                        kill_path,
                        LogType.KILL,
                        initial_position=state['last_position'] if state else 0,
                        initial_hash=state['last_line_hash'] if state else ""
                    )

                if admin_path and admin_path != chat_path and admin_path != kill_path:
                    state = LogMonitorStateQueries.get_state(sftp_config['id'], 'admin')
                    monitor.add_file(
                        admin_path,
                        LogType.ADMIN,
                        initial_position=state['last_position'] if state else 0,
                        initial_hash=state['last_line_hash'] if state else ""
                    )

            # Register callbacks for posting to Discord
            monitor.on_log(LogType.CHAT, lambda e: self._queue_log_entry(
                interaction.guild_id, sftp_config['id'], e
            ))
            monitor.on_log(LogType.KILL, lambda e: self._queue_log_entry(
                interaction.guild_id, sftp_config['id'], e
            ))
            monitor.on_log(LogType.ADMIN, lambda e: self._queue_log_entry(
                interaction.guild_id, sftp_config['id'], e
            ))

            # Get poll interval from settings
            settings = GuildRCONSettingsQueries.get_or_create_settings(interaction.guild_id)
            poll_interval = settings.get('log_poll_interval_seconds', 30)

            await monitor.start(poll_interval)
            self._active_monitors[interaction.guild_id] = sftp_config['id']

            # Load Game.ini admin list
            await self._load_game_ini_admins(interaction.guild_id, sftp_config)

            # Build success message
            mode_info = "unified log file" if unified_mode else "separate log files"
            log_path_display = chat_path if unified_mode else f"{len([p for p in [chat_path, kill_path, admin_path] if p])} files"

            embed = discord.Embed(
                title="✅ Log Monitoring Started",
                description=f"Now monitoring **{config}** ({mode_info})",
                color=discord.Color.green()
            )
            embed.add_field(name="Log File", value=f"`{log_path_display}`", inline=False)
            embed.add_field(name="Poll Interval", value=f"{poll_interval} seconds", inline=True)
            embed.add_field(name="Mode", value="Unified" if unified_mode else "Multi-file", inline=True)
            embed.set_footer(text="Logs will appear in your configured channels")

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Error starting monitoring: {e}", exc_info=True)
            await interaction.followup.send(
                f"An error occurred: {e}",
                ephemeral=True
            )

    @app_commands.command(name="stop", description="Stop log monitoring")
    @app_commands.guild_only()
    async def stop_monitoring(self, interaction: discord.Interaction):
        """Stop log monitoring for this guild."""
        if not await require_permission(interaction, 'logs_stop'):
            return

        try:
            config_id = self._active_monitors.get(interaction.guild_id)

            if not config_id:
                await interaction.response.send_message(
                    "No active monitoring for this server.",
                    ephemeral=True
                )
                return

            await log_monitor_manager.remove_monitor(config_id)
            del self._active_monitors[interaction.guild_id]

            await interaction.response.send_message(
                "Log monitoring stopped.",
                ephemeral=True
            )

        except Exception as e:
            logger.error(f"Error stopping monitoring: {e}", exc_info=True)
            await interaction.response.send_message(
                f"An error occurred: {e}",
                ephemeral=True
            )

    @app_commands.command(name="fileinfo", description="Check if log file exists and show details (debug)")
    @app_commands.guild_only()
    @app_commands.describe(config="SFTP configuration to check")
    async def fileinfo_logs(self, interaction: discord.Interaction, config: str):
        """Check if log file exists and show file information."""
        if not await require_permission(interaction, 'logs_setup'):
            return

        await interaction.response.defer(ephemeral=True)

        try:
            import asyncio
            from datetime import datetime
            configs = SFTPConfigQueries.get_active_configs(interaction.guild_id)
            sftp_config = next((c for c in configs if c['config_name'] == config), None)

            if not sftp_config:
                await interaction.followup.send(f"❌ Configuration `{config}` not found.", ephemeral=True)
                return

            # Create reader
            game_type = GameLogType(sftp_config.get('game_type', 'the_isle_evrima'))
            reader = SFTPLogReader(
                sftp_config['host'],
                sftp_config['port'],
                sftp_config['username'],
                sftp_config['password'],
                game_type
            )

            await reader.connect()

            log_path = sftp_config.get('chat_log_path')
            if not log_path:
                await interaction.followup.send("❌ No log path configured.", ephemeral=True)
                return

            # Check if file exists and get details
            def _check_file():
                try:
                    stat = reader._sftp.stat(log_path)

                    # Get file details
                    file_size = stat.st_size
                    mod_time = datetime.fromtimestamp(stat.st_mtime)

                    # Try to read first and last few lines
                    with reader._sftp.open(log_path, 'r') as f:
                        # First 3 lines
                        first_lines = []
                        for _ in range(3):
                            line = f.readline()
                            if not line:
                                break
                            if isinstance(line, bytes):
                                line = line.decode('utf-8', errors='replace')
                            first_lines.append(line.strip())

                        # Last 3 lines
                        f.seek(max(0, file_size - 1000))
                        content = f.read()
                        if isinstance(content, bytes):
                            content = content.decode('utf-8', errors='replace')
                        last_lines = content.splitlines()[-3:]

                    return {
                        'exists': True,
                        'size': file_size,
                        'modified': mod_time,
                        'first_lines': first_lines,
                        'last_lines': last_lines
                    }
                except FileNotFoundError:
                    return {'exists': False}
                except Exception as e:
                    return {'exists': False, 'error': str(e)}

            info = await asyncio.to_thread(_check_file)
            await reader.disconnect()

            if not info['exists']:
                error_msg = f": {info.get('error')}" if 'error' in info else ""
                embed = discord.Embed(
                    title="❌ Log File Not Found",
                    description=f"The log file does not exist{error_msg}",
                    color=discord.Color.red()
                )
                embed.add_field(name="Path", value=f"`{log_path}`", inline=False)
                embed.add_field(
                    name="Possible Reasons",
                    value="• Game server hasn't been started yet\n"
                          "• No players have connected (file created on first join)\n"
                          "• The path is incorrect\n"
                          "• The file was deleted",
                    inline=False
                )
                embed.add_field(
                    name="Next Steps",
                    value="1. Start your game server if not running\n"
                          "2. Have a player connect to trigger log creation\n"
                          "3. Wait a few seconds and run this command again\n"
                          "4. Once file exists, logs will appear in Discord",
                    inline=False
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return

            # File exists - show details
            size_kb = info['size'] / 1024
            first_preview = "\n".join(f"{line[:100]}" for line in info['first_lines']) if info['first_lines'] else "(empty)"
            last_preview = "\n".join(f"{line[:100]}" for line in info['last_lines']) if info['last_lines'] else "(empty)"

            embed = discord.Embed(
                title="✅ Log File Found",
                description=f"**Path:** `{log_path}`",
                color=discord.Color.green()
            )
            embed.add_field(name="Size", value=f"{size_kb:.2f} KB ({info['size']} bytes)", inline=True)
            embed.add_field(name="Modified", value=info['modified'].strftime('%Y-%m-%d %H:%M:%S'), inline=True)
            embed.add_field(name="First Lines", value=f"```{first_preview[:500]}```", inline=False)
            embed.add_field(name="Last Lines", value=f"```{last_preview[:500]}```", inline=False)

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Error checking file: {e}", exc_info=True)
            await interaction.followup.send(f"❌ Failed to check file: {e}", ephemeral=True)

    @app_commands.command(name="test", description="Test log file reading (debug)")
    @app_commands.guild_only()
    @app_commands.describe(config="SFTP configuration to test")
    async def test_logs(self, interaction: discord.Interaction, config: str):
        """Test reading from log file and show sample entries."""
        if not await require_permission(interaction, 'logs_setup'):
            return

        await interaction.response.defer(ephemeral=True)

        try:
            import asyncio
            configs = SFTPConfigQueries.get_active_configs(interaction.guild_id)
            sftp_config = next((c for c in configs if c['config_name'] == config), None)

            if not sftp_config:
                await interaction.followup.send(f"❌ Configuration `{config}` not found.", ephemeral=True)
                return

            # Create reader
            game_type = GameLogType(sftp_config.get('game_type', 'the_isle_evrima'))
            reader = SFTPLogReader(
                sftp_config['host'],
                sftp_config['port'],
                sftp_config['username'],
                sftp_config['password'],
                game_type
            )

            # Connect and read last 20 lines
            await reader.connect()

            log_path = sftp_config.get('chat_log_path')
            if not log_path:
                await interaction.followup.send("❌ No log path configured.", ephemeral=True)
                return

            # Read from end of file (last 2000 bytes)
            def _read_tail():
                try:
                    stat = reader._sftp.stat(log_path)
                    file_size = stat.st_size
                    read_from = max(0, file_size - 2000)

                    with reader._sftp.open(log_path, 'r') as f:
                        f.seek(read_from)
                        content = f.read()
                        if isinstance(content, bytes):
                            content = content.decode('utf-8', errors='replace')
                        return content.splitlines()[-20:]  # Last 20 lines
                except FileNotFoundError:
                    return None

            lines = await asyncio.to_thread(_read_tail)
            await reader.disconnect()

            if lines is None:
                embed = discord.Embed(
                    title="❌ Log File Not Found",
                    description=f"The log file does not exist at:\n`{log_path}`",
                    color=discord.Color.red()
                )
                embed.add_field(
                    name="Next Step",
                    value=f"Run `/logs fileinfo config:{config}` for more details.",
                    inline=False
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return

            # Try parsing each line
            parsed_lines = []
            for line in lines:
                if hasattr(reader.parser, 'parse_any_line'):
                    entry = reader.parser.parse_any_line(line)
                    if entry:
                        parsed_lines.append(f"✅ {entry.log_type.value}: {line[:80]}")
                    else:
                        parsed_lines.append(f"❌ NO MATCH: {line[:80]}")

            result = "\n".join(parsed_lines) if parsed_lines else "No lines found"

            embed = discord.Embed(
                title="📄 Log File Test",
                description=f"File: `{log_path}`\n\nLast 20 lines:",
                color=discord.Color.blue()
            )
            embed.add_field(name="Results", value=f"```\n{result[:1000]}\n```", inline=False)

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Error testing logs: {e}", exc_info=True)
            await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)

    @app_commands.command(name="readfile", description="Read contents of a file (debug)")
    @app_commands.guild_only()
    @app_commands.describe(
        config="SFTP configuration to use",
        file_path="Full path to the file (e.g., TheIsle/Saved/Logs/TheIsle.log)"
    )
    async def read_file(self, interaction: discord.Interaction, config: str, file_path: str):
        """Read and display contents of a file."""
        if not await require_permission(interaction, 'logs_setup'):
            return

        await interaction.response.defer(ephemeral=True)

        try:
            import asyncio
            from datetime import datetime
            configs = SFTPConfigQueries.get_active_configs(interaction.guild_id)
            sftp_config = next((c for c in configs if c['config_name'] == config), None)

            if not sftp_config:
                await interaction.followup.send(f"❌ Configuration `{config}` not found.", ephemeral=True)
                return

            # Create reader
            game_type = GameLogType(sftp_config.get('game_type', 'the_isle_evrima'))
            reader = SFTPLogReader(
                sftp_config['host'],
                sftp_config['port'],
                sftp_config['username'],
                sftp_config['password'],
                game_type
            )

            await reader.connect()

            def _read_file():
                try:
                    stat = reader._sftp.stat(file_path)
                    file_size = stat.st_size
                    mod_time = datetime.fromtimestamp(stat.st_mtime)

                    # Read last 3000 bytes (last ~30-50 lines)
                    read_from = max(0, file_size - 3000)
                    with reader._sftp.open(file_path, 'r') as f:
                        f.seek(read_from)
                        content = f.read()
                        if isinstance(content, bytes):
                            content = content.decode('utf-8', errors='replace')
                        lines = content.splitlines()[-30:]  # Last 30 lines

                    return {
                        'success': True,
                        'size': file_size,
                        'modified': mod_time,
                        'lines': lines
                    }
                except FileNotFoundError:
                    return {'success': False, 'error': 'File not found'}
                except PermissionError:
                    return {'success': False, 'error': 'Permission denied'}
                except Exception as e:
                    return {'success': False, 'error': str(e)}

            result = await asyncio.to_thread(_read_file)
            await reader.disconnect()

            if not result['success']:
                await interaction.followup.send(
                    f"❌ Failed to read file: {result['error']}\nPath: `{file_path}`",
                    ephemeral=True
                )
                return

            # Build embed with file contents
            size_kb = result['size'] / 1024
            content_preview = "\n".join(result['lines'][-15:])  # Last 15 lines

            embed = discord.Embed(
                title="📄 File Contents",
                description=f"**Path:** `{file_path}`\n**Size:** {size_kb:.2f} KB\n**Modified:** {result['modified'].strftime('%Y-%m-%d %H:%M:%S')}",
                color=discord.Color.blue()
            )

            embed.add_field(
                name="Last 15 Lines",
                value=f"```\n{content_preview[:1000]}\n```",
                inline=False
            )

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Error reading file: {e}", exc_info=True)
            await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)

    @app_commands.command(name="browse", description="Browse SFTP server directory (debug)")
    @app_commands.guild_only()
    @app_commands.describe(
        config="SFTP configuration to use",
        path="Directory path to browse (shortcuts: logs, saved, root)"
    )
    async def browse_sftp(self, interaction: discord.Interaction, config: str, path: str = None):
        """Browse SFTP server to see files and directories."""
        if not await require_permission(interaction, 'logs_setup'):
            return

        await interaction.response.defer(ephemeral=True)

        try:
            import asyncio
            from datetime import datetime
            configs = SFTPConfigQueries.get_active_configs(interaction.guild_id)
            sftp_config = next((c for c in configs if c['config_name'] == config), None)

            if not sftp_config:
                await interaction.followup.send(f"❌ Configuration `{config}` not found.", ephemeral=True)
                return

            # Handle shortcuts
            if path:
                path = path.strip()
                if path.lower() == 'logs':
                    path = 'TheIsle/Saved/Logs'
                elif path.lower() == 'saved':
                    path = 'TheIsle/Saved'
                elif path.lower() == 'root':
                    path = '.'

            # Create reader
            game_type = GameLogType(sftp_config.get('game_type', 'the_isle_evrima'))
            reader = SFTPLogReader(
                sftp_config['host'],
                sftp_config['port'],
                sftp_config['username'],
                sftp_config['password'],
                game_type
            )

            await reader.connect()

            # Default to current directory or use provided path
            browse_path = path if path else '.'

            def _list_directory():
                try:
                    import stat
                    items = []
                    # List directory contents
                    for item in reader._sftp.listdir_attr(browse_path):
                        # Check if directory using stat module
                        is_directory = stat.S_ISDIR(item.st_mode) if item.st_mode else False
                        is_dir = '📁' if is_directory else '📄'
                        size = f"{item.st_size / 1024:.1f} KB" if item.st_size else "0 KB"
                        mod_time = datetime.fromtimestamp(item.st_mtime).strftime('%Y-%m-%d %H:%M') if item.st_mtime else "Unknown"

                        items.append({
                            'name': item.filename,
                            'type': is_dir,
                            'size': size,
                            'modified': mod_time,
                            'is_dir': is_directory
                        })

                    # Sort: directories first, then files, alphabetically
                    items.sort(key=lambda x: (not x['is_dir'], x['name'].lower()))
                    return items
                except FileNotFoundError:
                    return None
                except PermissionError:
                    return 'permission_error'
                except Exception as e:
                    return f'error: {str(e)}'

            result = await asyncio.to_thread(_list_directory)
            await reader.disconnect()

            if result is None:
                await interaction.followup.send(
                    f"❌ Directory not found: `{browse_path}`",
                    ephemeral=True
                )
                return
            elif result == 'permission_error':
                await interaction.followup.send(
                    f"❌ Permission denied accessing: `{browse_path}`",
                    ephemeral=True
                )
                return
            elif isinstance(result, str) and result.startswith('error:'):
                await interaction.followup.send(
                    f"❌ Error: {result[7:]}",
                    ephemeral=True
                )
                return

            # Get parent directory for "Go Up" button
            parent_path = None
            if browse_path and browse_path != '.' and browse_path != '/':
                parts = browse_path.rstrip('/').split('/')
                if len(parts) > 1:
                    parent_path = '/'.join(parts[:-1])
                else:
                    parent_path = '.'

            # Build embed with directory listing
            embed = discord.Embed(
                title=f"📂 SFTP Directory Browser",
                description=f"**Current Path:** `{browse_path}`\n**Items:** {len(result)}",
                color=discord.Color.blue()
            )

            if not result:
                embed.add_field(
                    name="Empty Directory",
                    value="No files or folders found",
                    inline=False
                )
            else:
                # Show directories and files separately
                dirs = [item for item in result if item['is_dir']]
                files = [item for item in result if not item['is_dir']]

                # Show directories (up to 10)
                if dirs:
                    dirs_text = []
                    for item in dirs[:10]:
                        # Create clickable path hint
                        new_path = f"{browse_path}/{item['name']}".replace('./', '').replace('//', '/')
                        dirs_text.append(f"📁 **{item['name']}**")

                    dirs_value = "\n".join(dirs_text)
                    if len(dirs) > 10:
                        dirs_value += f"\n...and {len(dirs) - 10} more folders"

                    embed.add_field(
                        name=f"📂 Folders ({len(dirs)})",
                        value=dirs_value,
                        inline=False
                    )

                # Show files (up to 15, condensed)
                if files:
                    files_text = []
                    for item in files[:15]:
                        files_text.append(f"📄 `{item['name']}` ({item['size']})")

                    files_value = "\n".join(files_text)
                    if len(files) > 15:
                        files_value += f"\n...and {len(files) - 15} more files"

                    embed.add_field(
                        name=f"📄 Files ({len(files)})",
                        value=files_value,
                        inline=False
                    )

            # Add navigation instructions
            nav_text = []

            # Show parent directory option
            if parent_path is not None:
                nav_text.append(f"⬆️ **Go Up:** `path:{parent_path}`")

            # Show subdirectory navigation
            if dirs:
                example_dir = dirs[0]['name']
                new_path = f"{browse_path}/{example_dir}".replace('./', '').replace('//', '/')
                nav_text.append(f"➡️ **Enter Folder:** `path:{new_path}`")

            # Add shortcuts
            nav_text.append(f"\n**🔗 Quick Shortcuts:**")
            nav_text.append(f"• `path:logs` → TheIsle/Saved/Logs")
            nav_text.append(f"• `path:saved` → TheIsle/Saved")
            nav_text.append(f"• `path:root` → Home directory")

            embed.add_field(
                name="🧭 Navigation",
                value="\n".join(nav_text),
                inline=False
            )

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Error browsing SFTP: {e}", exc_info=True)
            await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)

    @app_commands.command(name="status", description="Show log monitoring status")
    @app_commands.guild_only()
    async def monitoring_status(self, interaction: discord.Interaction):
        """Show current monitoring status."""
        if not await require_permission(interaction, 'logs_status'):
            return

        try:
            config_id = self._active_monitors.get(interaction.guild_id)
            configs = SFTPConfigQueries.get_active_configs(interaction.guild_id)
            channels = LogChannelQueries.get_channels(interaction.guild_id)

            embed = discord.Embed(
                title="Log Monitoring Status",
                color=discord.Color.blue()
            )

            # Monitoring status
            if config_id:
                config = next((c for c in configs if c['id'] == config_id), None)
                config_name = config['config_name'] if config else "Unknown"
                embed.add_field(
                    name="Status",
                    value=f"🟢 Active - Monitoring `{config_name}`",
                    inline=False
                )
            else:
                embed.add_field(
                    name="Status",
                    value="🔴 Inactive",
                    inline=False
                )

            # Configured channels
            if channels:
                channel_list = []
                if channels.get('chatlog_channel_id'):
                    channel_list.append(f"**Chat:** <#{channels['chatlog_channel_id']}>")
                if channels.get('killfeed_channel_id'):
                    channel_list.append(f"**Kills:** <#{channels['killfeed_channel_id']}>")
                if channels.get('adminlog_channel_id'):
                    channel_list.append(f"**Admin:** <#{channels['adminlog_channel_id']}>")

                if channel_list:
                    embed.add_field(
                        name="Channels",
                        value="\n".join(channel_list),
                        inline=False
                    )
            else:
                embed.add_field(
                    name="Channels",
                    value="No channels configured",
                    inline=False
                )

            # SFTP configurations
            if configs:
                config_list = []
                for c in configs:
                    paths = []
                    if c.get('chat_log_path'):
                        paths.append("chat")
                    if c.get('kill_log_path'):
                        paths.append("kill")
                    if c.get('admin_log_path'):
                        paths.append("admin")
                    path_str = ", ".join(paths) if paths else "no paths"
                    config_list.append(f"• **{c['config_name']}** ({path_str})")

                embed.add_field(
                    name="SFTP Configurations",
                    value="\n".join(config_list),
                    inline=False
                )
            else:
                embed.add_field(
                    name="SFTP Configurations",
                    value="None configured",
                    inline=False
                )

            await interaction.response.send_message(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Error getting status: {e}", exc_info=True)
            await interaction.response.send_message(
                f"An error occurred: {e}",
                ephemeral=True
            )

    # ==========================================
    # AUTOCOMPLETE
    # ==========================================

    @set_log_path.autocomplete('config')
    @start_monitoring.autocomplete('config')
    @browse_sftp.autocomplete('config')
    @fileinfo_logs.autocomplete('config')
    @test_logs.autocomplete('config')
    async def config_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str
    ) -> list[app_commands.Choice[str]]:
        """Autocomplete for SFTP config names."""
        try:
            configs = SFTPConfigQueries.get_active_configs(interaction.guild_id)
            return [
                app_commands.Choice(name=c['config_name'], value=c['config_name'])
                for c in configs
                if current.lower() in c['config_name'].lower()
            ][:25]
        except Exception:
            return []

    # ==========================================
    # LOG PROCESSING
    # ==========================================

    _log_queue: list[tuple[int, int, any]] = []  # (guild_id, config_id, entry)

    def _queue_log_entry(self, guild_id: int, config_id: int, entry):
        """Queue a log entry for processing."""
        self._log_queue.append((guild_id, config_id, entry))

    @tasks.loop(seconds=5)
    async def process_logs(self):
        """Process queued log entries and post to Discord."""
        if not self._log_queue:
            return

        # Process up to 20 entries per loop
        entries_to_process = self._log_queue[:20]
        self._log_queue = self._log_queue[20:]

        for guild_id, config_id, entry in entries_to_process:
            try:
                await self._post_log_entry(guild_id, config_id, entry)

                # Update state in database (only for legacy events with log_type attribute)
                # Enhanced events don't need per-type state tracking since they use unified log files
                if hasattr(entry, 'log_type'):
                    monitor = log_monitor_manager.get_monitor(config_id)
                    if monitor:
                        # Get file path for this entry type
                        config = SFTPConfigQueries.get_config(config_id, guild_id)
                        if config:
                            path_map = {
                                LogType.CHAT: config.get('chat_log_path'),
                                LogType.KILL: config.get('kill_log_path'),
                                LogType.ADMIN: config.get('admin_log_path'),
                            }
                            file_path = path_map.get(entry.log_type)
                            if file_path:
                                state = monitor.get_state(file_path)
                                if state:
                                    LogMonitorStateQueries.update_state(
                                        config_id,
                                        entry.log_type.value,
                                        file_path,
                                        state['position'],
                                        state['hash']
                                    )

            except Exception as e:
                logger.error(f"Error processing log entry: {e}", exc_info=True)

    @process_logs.before_loop
    async def before_process_logs(self):
        """Wait for bot to be ready before starting loop."""
        await self.bot.wait_until_ready()

    async def _check_verification_code(self, guild_id: int, entry: ChatLogEntry):
        """
        Check if a chat message contains a verification code.
        If valid, link the player's ID to their Discord account.
        """
        # Extract potential verification code from message (6 uppercase alphanumeric characters)
        import re
        code_match = re.search(r'\b([A-Z0-9]{6})\b', entry.message.upper())
        if not code_match:
            return

        code = code_match.group(1)

        # Verify the code
        verification = VerificationCodeQueries.verify_code(guild_id, code)
        if not verification:
            return

        # Valid code found! Link the player
        try:
            # Determine which ID to link based on game type
            if verification['game_type'] == 'the_isle_evrima':
                # Steam ID from The Isle
                steam_id = entry.player_id

                # Link Steam ID
                PlayerQueries.link_steam(
                    guild_id=guild_id,
                    user_id=verification['user_id'],
                    username="",  # We don't have username from log
                    steam_id=steam_id,
                    player_name=entry.player_name,
                    verification_method='chat_log'
                )

                # Mark code as verified
                VerificationCodeQueries.mark_verified(verification['id'])

                # Log to audit
                AuditQueries.log(
                    guild_id=guild_id,
                    action_type=AuditQueries.ACTION_PLAYER_LINKED,
                    performed_by_id=verification['user_id'],
                    performed_by_name=f"User {verification['user_id']}",
                    target_user_id=verification['user_id'],
                    details={
                        'steam_id': steam_id,
                        'player_name': entry.player_name,
                        'verification_method': 'chat_log',
                        'type': 'steam'
                    }
                )

                # Send confirmation to link channel
                link_channel_id = LogChannelQueries.get_channels(guild_id).get('link_channel_id')
                if link_channel_id:
                    channel = self.bot.get_channel(link_channel_id)
                    if channel:
                        # Get the user
                        user = await self.bot.fetch_user(verification['user_id'])
                        embed = discord.Embed(
                            title="✅ Player Verified via Chat Log",
                            description=f"{user.mention} has been verified!",
                            color=discord.Color.green()
                        )
                        embed.add_field(name="Player Name", value=entry.player_name, inline=True)
                        embed.add_field(name="Steam ID", value=f"`{steam_id}`", inline=True)
                        embed.set_footer(text="Verified by typing code in-game")
                        await channel.send(embed=embed)

                        # Also DM the user
                        try:
                            await user.send(
                                f"✅ **Verification Successful!**\n\n"
                                f"Your Discord account has been linked to:\n"
                                f"**Player Name:** {entry.player_name}\n"
                                f"**Steam ID:** `{steam_id}`\n\n"
                                f"Your ID is now locked for security."
                            )
                        except discord.Forbidden:
                            pass  # User has DMs disabled

            elif verification['game_type'] == 'path_of_titans':
                # Alderon ID from Path of Titans
                alderon_id = entry.player_id

                # Link Alderon ID
                PlayerQueries.link_alderon(
                    guild_id=guild_id,
                    user_id=verification['user_id'],
                    username="",
                    player_id=alderon_id,
                    player_name=entry.player_name,
                    verification_method='chat_log'
                )

                # Mark code as verified
                VerificationCodeQueries.mark_verified(verification['id'])

                # Log to audit
                AuditQueries.log(
                    guild_id=guild_id,
                    action_type=AuditQueries.ACTION_PLAYER_LINKED,
                    performed_by_id=verification['user_id'],
                    performed_by_name=f"User {verification['user_id']}",
                    target_user_id=verification['user_id'],
                    details={
                        'player_id': alderon_id,
                        'player_name': entry.player_name,
                        'verification_method': 'chat_log',
                        'type': 'alderon'
                    }
                )

                # Send confirmation to link channel
                link_channel_id = LogChannelQueries.get_channels(guild_id).get('link_channel_id')
                if link_channel_id:
                    channel = self.bot.get_channel(link_channel_id)
                    if channel:
                        user = await self.bot.fetch_user(verification['user_id'])
                        embed = discord.Embed(
                            title="✅ Player Verified via Chat Log",
                            description=f"{user.mention} has been verified!",
                            color=discord.Color.green()
                        )
                        embed.add_field(name="Player Name", value=entry.player_name, inline=True)
                        embed.add_field(name="Alderon ID", value=f"`{alderon_id}`", inline=True)
                        embed.set_footer(text="Verified by typing code in-game")
                        await channel.send(embed=embed)

                        # Also DM the user
                        try:
                            await user.send(
                                f"✅ **Verification Successful!**\n\n"
                                f"Your Discord account has been linked to:\n"
                                f"**Player Name:** {entry.player_name}\n"
                                f"**Alderon ID:** `{alderon_id}`\n\n"
                                f"Your ID is now locked for security."
                            )
                        except discord.Forbidden:
                            pass

            logger.info(f"Player verified via chat log: User {verification['user_id']} -> {entry.player_name}")

        except Exception as e:
            logger.error(f"Error processing verification code from chat: {e}", exc_info=True)

    def _get_log_identifier(self, entry) -> str:
        """
        Generate a unique identifier for a log entry using timestamp + content hash.

        Returns a string like: "2026.01.28-00.35.59:819_abc123"
        """
        import hashlib

        # Get timestamp from entry
        timestamp = None
        if hasattr(entry, 'timestamp'):
            timestamp = entry.timestamp
        elif hasattr(entry, 'raw_line'):
            # Extract timestamp from raw line: [2026.01.28-00.35.59:819]
            import re
            match = re.search(r'\[(\d{4}\.\d{2}\.\d{2}-\d{2}\.\d{2}\.\d{2}:\d{3})\]', entry.raw_line)
            if match:
                timestamp = match.group(1)

        # Get content for hashing
        content = entry.raw_line if hasattr(entry, 'raw_line') else str(entry)
        content_hash = hashlib.md5(content.encode()).hexdigest()[:8]

        # Combine timestamp and hash
        if timestamp:
            return f"{timestamp}_{content_hash}"
        else:
            return content_hash

    async def _post_log_entry(self, guild_id: int, config_id: int, entry):
        """Post a log entry to the appropriate Discord channel."""
        # Check for duplicates
        log_id = self._get_log_identifier(entry)
        if log_id in self._posted_logs:
            logger.debug(f"Skipping duplicate log entry: {log_id}")
            return

        # Add to cache (with size limit)
        self._posted_logs.add(log_id)
        if len(self._posted_logs) > self._cache_max_size:
            # Remove oldest 200 entries (simple FIFO)
            entries_to_remove = list(self._posted_logs)[:200]
            for entry_id in entries_to_remove:
                self._posted_logs.discard(entry_id)

        channels = LogChannelQueries.get_channels(guild_id)
        if not channels:
            return

        channel_id = None
        embed = None
        guild = self.bot.get_guild(guild_id)

        # Get server name for enhanced embeds
        config = SFTPConfigQueries.get_config(config_id, guild_id)
        server_name = config.get('config_name', 'Server') if config else 'Server'

        # Handle enhanced log events (new parser)
        if ENHANCED_LOGS_AVAILABLE:
            if isinstance(entry, PlayerLoginEvent):
                channel_id = channels.get('player_login_channel_id')
                embed = await build_player_login_embed(entry, server_name, guild)

            elif isinstance(entry, PlayerLogoutEvent):
                channel_id = channels.get('player_logout_channel_id')
                embed = await build_player_logout_embed(entry, server_name, guild)

            elif isinstance(entry, PlayerChatEvent):
                channel_id = channels.get('player_chat_channel_id')
                embed = await build_player_chat_embed(entry, guild)

            elif isinstance(entry, AdminCommandEvent):
                channel_id = channels.get('admin_command_channel_id')
                embed = await build_admin_command_embed(entry, server_name, guild)

            elif isinstance(entry, RCONCommandEvent):
                # RCON commands default to admin channel if rcon channel not set (due to UI row limit)
                channel_id = channels.get('rcon_command_channel_id') or channels.get('admin_command_channel_id')
                embed = await build_rcon_command_embed(entry, server_name)

            elif isinstance(entry, PlayerDeathEvent):
                channel_id = channels.get('player_death_channel_id')
                embed = await build_player_death_embed(entry, server_name, guild)

        # Handle legacy log events (old parser - fallback)
        if isinstance(entry, ChatLogEntry):
            # Check for verification codes in chat messages
            await self._check_verification_code(guild_id, entry)

            # Use new channel if available, fallback to legacy
            if not channel_id:
                channel_id = channels.get('player_chat_channel_id') or channels.get('chatlog_channel_id')
            if not embed:
                embed = discord.Embed(
                    description=f"**[{entry.channel}]** {entry.player_name}: {entry.message}",
                    color=discord.Color.blue(),
                    timestamp=entry.timestamp
                )
                embed.set_footer(text=f"Steam ID: {entry.player_id}")

        elif isinstance(entry, KillLogEntry):
            if not channel_id:
                channel_id = channels.get('player_death_channel_id') or channels.get('killfeed_channel_id')
            if not embed:
                embed = discord.Embed(
                    description=f"💀 **{entry.killer_name}** killed **{entry.victim_name}**",
                    color=discord.Color.red(),
                    timestamp=entry.timestamp
                )
                embed.add_field(name="Killer ID", value=f"`{entry.killer_id}`", inline=True)
                embed.add_field(name="Victim ID", value=f"`{entry.victim_id}`", inline=True)

        elif isinstance(entry, AdminLogEntry):
            if not channel_id:
                channel_id = channels.get('admin_command_channel_id') or channels.get('adminlog_channel_id')
            if not embed:
                embed = discord.Embed(
                    description=f"⚡ **{entry.admin_name}** executed: `{entry.action}`",
                    color=discord.Color.orange(),
                    timestamp=entry.timestamp
                )
                if entry.target:
                    embed.add_field(name="Target", value=entry.target, inline=True)
                embed.set_footer(text=f"Admin ID: {entry.admin_id}")

        if channel_id and embed:
            channel = self.bot.get_channel(channel_id)
            if channel:
                try:
                    await channel.send(embed=embed)
                except discord.Forbidden:
                    logger.warning(f"Cannot send to channel {channel_id} - missing permissions")
                except Exception as e:
                    logger.error(f"Error sending to channel: {e}")


async def setup(bot: commands.Bot):
    """Load the ServerLogsCommands cog."""
    await bot.add_cog(ServerLogsCommands(bot))
