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
    LogMonitorStateQueries, GuildRCONSettingsQueries
)
from services.permissions import require_permission
from services.sftp_logs import (
    SFTPLogReader, LogMonitor, log_monitor_manager, LogType,
    GameLogType, ChatLogEntry, KillLogEntry, AdminLogEntry
)
import logging
from typing import Optional, Literal

logger = logging.getLogger(__name__)


class ServerLogsCommands(commands.GroupCog, name="logs"):
    """Server log monitoring commands."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._active_monitors: dict[int, int] = {}  # guild_id -> sftp_config_id
        super().__init__()

    async def cog_load(self):
        """Called when the cog is loaded."""
        # Start the log processor loop
        self.process_logs.start()

    async def cog_unload(self):
        """Called when the cog is unloaded."""
        self.process_logs.cancel()
        await log_monitor_manager.stop_all()

    # ==========================================
    # SFTP CONFIGURATION
    # ==========================================

    @app_commands.command(name="setup", description="Configure SFTP connection for log monitoring")
    @app_commands.guild_only()
    @app_commands.describe(
        name="Friendly name for this configuration",
        host="SFTP server hostname or IP",
        port="SFTP port (default: 22)",
        username="SFTP username",
        password="SFTP password",
        game="Game type for log parsing"
    )
    async def setup_sftp(
        self,
        interaction: discord.Interaction,
        name: str,
        host: str,
        username: str,
        password: str,
        game: Literal["the_isle_evrima", "path_of_titans"],
        port: int = 22
    ):
        """Configure SFTP connection for log monitoring."""
        if not await require_permission(interaction, 'logs_setup'):
            return

        await interaction.response.defer(ephemeral=True)

        GuildQueries.get_or_create(interaction.guild_id, interaction.guild.name)

        try:
            # Test connection
            reader = SFTPLogReader(host, port, username, password, GameLogType(game))
            success, message = await reader.test_connection()

            if not success:
                await interaction.followup.send(
                    f"SFTP connection failed: {message}\n"
                    "Please check your credentials.",
                    ephemeral=True
                )
                return

            # Save configuration
            config_id = SFTPConfigQueries.add_config(
                guild_id=interaction.guild_id,
                config_name=name,
                host=host,
                port=port,
                username=username,
                password=password
            )

            embed = discord.Embed(
                title="SFTP Configuration Added",
                description=f"Configuration `{name}` saved successfully.",
                color=discord.Color.green()
            )
            embed.add_field(name="Host", value=f"`{host}:{port}`", inline=True)
            embed.add_field(name="Game", value=game.replace('_', ' ').title(), inline=True)
            embed.add_field(
                name="Next Steps",
                value="1. Set log file paths with `/logs setpath`\n"
                      "2. Set output channels with `/logs setchannel`\n"
                      "3. Start monitoring with `/logs start`",
                inline=False
            )

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Error setting up SFTP: {e}", exc_info=True)
            await interaction.followup.send(
                f"An error occurred: {e}",
                ephemeral=True
            )

    @app_commands.command(name="setpath", description="Set log file path for a log type")
    @app_commands.guild_only()
    @app_commands.describe(
        config="SFTP configuration name",
        log_type="Type of log",
        path="Full path to the log file"
    )
    async def set_log_path(
        self,
        interaction: discord.Interaction,
        config: str,
        log_type: Literal["chat", "kill", "admin"],
        path: str
    ):
        """Set the file path for a log type."""
        if not await require_permission(interaction, 'logs_setup'):
            return

        try:
            configs = SFTPConfigQueries.get_active_configs(interaction.guild_id)
            sftp_config = next((c for c in configs if c['config_name'] == config), None)

            if not sftp_config:
                await interaction.response.send_message(
                    f"Configuration `{config}` not found.",
                    ephemeral=True
                )
                return

            # Update the appropriate path column
            column_map = {
                'chat': 'chat_log_path',
                'kill': 'kill_log_path',
                'admin': 'admin_log_path'
            }

            # We need to add an update method - for now use raw query approach
            from database.connection import get_cursor
            with get_cursor() as cursor:
                cursor.execute(
                    f"UPDATE server_sftp_config SET {column_map[log_type]} = %s WHERE id = %s",
                    (path, sftp_config['id'])
                )

            await interaction.response.send_message(
                f"Set `{log_type}` log path to `{path}` for configuration `{config}`.",
                ephemeral=True
            )

        except Exception as e:
            logger.error(f"Error setting log path: {e}", exc_info=True)
            await interaction.response.send_message(
                f"An error occurred: {e}",
                ephemeral=True
            )

    # ==========================================
    # CHANNEL CONFIGURATION
    # ==========================================

    @app_commands.command(name="setchannel", description="Set Discord channel for log output")
    @app_commands.guild_only()
    @app_commands.describe(
        channel_type="Type of log channel",
        channel="Discord channel to send logs to"
    )
    async def set_channel(
        self,
        interaction: discord.Interaction,
        channel_type: Literal["chatlog", "killfeed", "adminlog"],
        channel: discord.TextChannel
    ):
        """Set a Discord channel for log output."""
        if not await require_permission(interaction, 'logs_setchannel'):
            return

        try:
            LogChannelQueries.set_channel(
                interaction.guild_id,
                channel_type,
                channel.id
            )

            type_names = {
                'chatlog': 'Chat Log',
                'killfeed': 'Kill Feed',
                'adminlog': 'Admin Log'
            }

            await interaction.response.send_message(
                f"{type_names[channel_type]} channel set to {channel.mention}",
                ephemeral=True
            )

        except Exception as e:
            logger.error(f"Error setting channel: {e}", exc_info=True)
            await interaction.response.send_message(
                f"An error occurred: {e}",
                ephemeral=True
            )

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
            # Determine game type from config (we'd need to store this)
            game_type = GameLogType.THE_ISLE_EVRIMA  # Default for now

            monitor = log_monitor_manager.create_monitor(
                config_id=sftp_config['id'],
                host=sftp_config['host'],
                port=sftp_config['port'],
                username=sftp_config['username'],
                password=sftp_config['password'],
                game_type=game_type
            )

            # Add log files to monitor
            if sftp_config.get('chat_log_path'):
                state = LogMonitorStateQueries.get_state(sftp_config['id'], 'chat')
                monitor.add_file(
                    sftp_config['chat_log_path'],
                    LogType.CHAT,
                    initial_position=state['last_position'] if state else 0,
                    initial_hash=state['last_line_hash'] if state else ""
                )

            if sftp_config.get('kill_log_path'):
                state = LogMonitorStateQueries.get_state(sftp_config['id'], 'kill')
                monitor.add_file(
                    sftp_config['kill_log_path'],
                    LogType.KILL,
                    initial_position=state['last_position'] if state else 0,
                    initial_hash=state['last_line_hash'] if state else ""
                )

            if sftp_config.get('admin_log_path'):
                state = LogMonitorStateQueries.get_state(sftp_config['id'], 'admin')
                monitor.add_file(
                    sftp_config['admin_log_path'],
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

            await interaction.followup.send(
                f"Started monitoring `{config}`. Logs will appear in configured channels.",
                ephemeral=True
            )

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

                # Update state in database
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
                logger.error(f"Error processing log entry: {e}")

    @process_logs.before_loop
    async def before_process_logs(self):
        """Wait for bot to be ready before starting loop."""
        await self.bot.wait_until_ready()

    async def _post_log_entry(self, guild_id: int, config_id: int, entry):
        """Post a log entry to the appropriate Discord channel."""
        channels = LogChannelQueries.get_channels(guild_id)
        if not channels:
            return

        channel_id = None
        embed = None

        if isinstance(entry, ChatLogEntry):
            channel_id = channels.get('chatlog_channel_id')
            embed = discord.Embed(
                description=f"**[{entry.channel}]** {entry.player_name}: {entry.message}",
                color=discord.Color.blue(),
                timestamp=entry.timestamp
            )
            embed.set_footer(text=f"Steam ID: {entry.player_id}")

        elif isinstance(entry, KillLogEntry):
            channel_id = channels.get('killfeed_channel_id')
            embed = discord.Embed(
                description=f"💀 **{entry.killer_name}** killed **{entry.victim_name}**",
                color=discord.Color.red(),
                timestamp=entry.timestamp
            )
            embed.add_field(name="Killer ID", value=f"`{entry.killer_id}`", inline=True)
            embed.add_field(name="Victim ID", value=f"`{entry.victim_id}`", inline=True)

        elif isinstance(entry, AdminLogEntry):
            channel_id = channels.get('adminlog_channel_id')
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
