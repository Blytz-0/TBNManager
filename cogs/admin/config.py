# cogs/admin/config.py
"""
Server Configuration Commands

Admin commands for configuring the bot per-server.
"""

import discord
from discord import app_commands
from discord.ext import commands
from database.queries import GuildQueries, AuditQueries
from services.permissions import require_admin, require_owner
from config.settings import DEFAULT_FEATURES, PREMIUM_FEATURES
import logging

logger = logging.getLogger(__name__)


class ConfigCommands(commands.Cog):
    """Server configuration commands."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="setup",
        description="View or configure bot settings for this server"
    )
    @app_commands.guild_only()
    async def setup(self, interaction: discord.Interaction):
        """Display current bot configuration."""

        if not await require_admin(interaction):
            return

        try:
            guild_id = interaction.guild_id
            guild_data = GuildQueries.get_or_create(guild_id, interaction.guild.name)

            # Get admin roles
            admin_roles = GuildQueries.get_admin_roles(guild_id)

            # Get channel configs
            log_channel_id = GuildQueries.get_channel(guild_id, 'logs')
            announce_channel_id = GuildQueries.get_channel(guild_id, 'announcements')

            embed = discord.Embed(
                title=f"Bot Configuration - {interaction.guild.name}",
                color=discord.Color.blue()
            )

            # Premium status
            if guild_data.get('is_premium'):
                premium_until = guild_data.get('premium_until')
                premium_text = f"Active until {premium_until.strftime('%Y-%m-%d')}" if premium_until else "Active"
            else:
                premium_text = "Not active"
            embed.add_field(name="Premium Status", value=premium_text, inline=True)

            # Admin roles - organized by level
            if admin_roles:
                level_names = {1: 'Mod', 2: 'Admin', 3: 'Owner'}
                by_level = {3: [], 2: [], 1: []}
                for r in admin_roles:
                    level = r['permission_level']
                    if level in by_level:
                        by_level[level].append(f"<@&{r['role_id']}>")

                role_lines = []
                for level in [3, 2, 1]:
                    if by_level[level]:
                        role_lines.append(f"**{level_names[level]}:** {', '.join(by_level[level])}")

                role_text = "\n".join(role_lines) if role_lines else "No roles configured"
            else:
                role_text = "_Using defaults: Owner, Headadmin, Admin, Moderator_\nUse `/setadminrole` to customize"
            embed.add_field(name="Permission Roles", value=role_text, inline=False)

            # Channels
            channels_text = []
            if log_channel_id:
                channels_text.append(f"Logs: <#{log_channel_id}>")
            if announce_channel_id:
                channels_text.append(f"Announcements: <#{announce_channel_id}>")
            if not channels_text:
                channels_text.append("No channels configured")
            embed.add_field(name="Configured Channels", value="\n".join(channels_text), inline=False)

            # Features
            feature_status = []
            for feature in DEFAULT_FEATURES:
                enabled = GuildQueries.is_feature_enabled(guild_id, feature)
                status = "✅" if enabled else "❌"
                feature_status.append(f"{status} {feature}")

            embed.add_field(
                name="Features",
                value="\n".join(feature_status),
                inline=True
            )

            # Premium features
            premium_status = []
            for feature in PREMIUM_FEATURES:
                enabled = GuildQueries.is_feature_enabled(guild_id, feature)
                if guild_data.get('is_premium'):
                    status = "✅" if enabled else "❌"
                else:
                    status = "🔒"
                premium_status.append(f"{status} {feature}")

            embed.add_field(
                name="Premium Features",
                value="\n".join(premium_status),
                inline=True
            )

            embed.set_footer(text="Use /setadminrole, /setchannel, /feature to configure")

            await interaction.response.send_message(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Error in /setup: {e}", exc_info=True)
            await interaction.response.send_message(
                "An error occurred while loading configuration.",
                ephemeral=True
            )

    @app_commands.command(
        name="setadminrole",
        description="Add or update an admin role"
    )
    @app_commands.guild_only()
    @app_commands.describe(
        role="The role to add as admin",
        level="Permission level (1=Mod, 2=Admin, 3=Owner)"
    )
    @app_commands.choices(level=[
        app_commands.Choice(name="Moderator (1)", value=1),
        app_commands.Choice(name="Admin (2)", value=2),
        app_commands.Choice(name="Owner (3)", value=3),
    ])
    async def set_admin_role(self, interaction: discord.Interaction,
                             role: discord.Role,
                             level: int):
        """Add or update an admin role."""

        # Only owners can set owner-level roles
        if level == 3:
            if not await require_owner(interaction):
                return
        else:
            if not await require_admin(interaction, min_level=2):
                return

        try:
            guild_id = interaction.guild_id
            GuildQueries.set_admin_role(guild_id, role.id, level)

            level_names = {1: 'Moderator', 2: 'Admin', 3: 'Owner'}

            AuditQueries.log(
                guild_id=guild_id,
                action_type=AuditQueries.ACTION_CONFIG_CHANGE,
                performed_by_id=interaction.user.id,
                performed_by_name=str(interaction.user),
                details={
                    'setting': 'admin_role',
                    'role_id': role.id,
                    'role_name': role.name,
                    'level': level
                }
            )

            await interaction.response.send_message(
                f"Role {role.mention} set as **{level_names[level]}** (Level {level}).",
                ephemeral=True
            )

        except Exception as e:
            logger.error(f"Error in /setadminrole: {e}", exc_info=True)
            await interaction.response.send_message(
                "An error occurred while setting the admin role.",
                ephemeral=True
            )

    @app_commands.command(
        name="removeadminrole",
        description="Remove an admin role"
    )
    @app_commands.guild_only()
    @app_commands.describe(
        role="The role to remove from admins"
    )
    async def remove_admin_role(self, interaction: discord.Interaction,
                                role: discord.Role):
        """Remove an admin role."""

        if not await require_admin(interaction, min_level=2):
            return

        try:
            guild_id = interaction.guild_id
            GuildQueries.remove_admin_role(guild_id, role.id)

            AuditQueries.log(
                guild_id=guild_id,
                action_type=AuditQueries.ACTION_CONFIG_CHANGE,
                performed_by_id=interaction.user.id,
                performed_by_name=str(interaction.user),
                details={
                    'setting': 'admin_role_removed',
                    'role_id': role.id,
                    'role_name': role.name
                }
            )

            await interaction.response.send_message(
                f"Role {role.mention} removed from admin roles.",
                ephemeral=True
            )

        except Exception as e:
            logger.error(f"Error in /removeadminrole: {e}", exc_info=True)
            await interaction.response.send_message(
                "An error occurred while removing the admin role.",
                ephemeral=True
            )

    @app_commands.command(
        name="adminroles",
        description="List all configured admin roles and their permission levels"
    )
    @app_commands.guild_only()
    async def list_admin_roles(self, interaction: discord.Interaction):
        """List all configured admin roles."""

        if not await require_admin(interaction):
            return

        try:
            guild_id = interaction.guild_id
            admin_roles = GuildQueries.get_admin_roles(guild_id)

            embed = discord.Embed(
                title="Admin Role Configuration",
                color=discord.Color.blue()
            )

            level_names = {1: 'Moderator', 2: 'Admin', 3: 'Owner'}

            if admin_roles:
                # Group by permission level
                by_level = {3: [], 2: [], 1: []}
                for r in admin_roles:
                    level = r['permission_level']
                    if level in by_level:
                        by_level[level].append(r['role_id'])

                for level in [3, 2, 1]:
                    if by_level[level]:
                        role_mentions = [f"<@&{rid}>" for rid in by_level[level]]
                        embed.add_field(
                            name=f"Level {level} - {level_names[level]}",
                            value="\n".join(role_mentions),
                            inline=False
                        )

                embed.set_footer(text="Use /setadminrole to add roles, /removeadminrole to remove them")
            else:
                embed.description = (
                    "No custom admin roles configured.\n\n"
                    "**Fallback Behavior:**\n"
                    "• Server owner and Discord Administrators always have full access\n"
                    "• Roles named 'Owner' → Level 3\n"
                    "• Roles named 'Headadmin' or 'Admin' → Level 2\n"
                    "• Roles named 'Moderator' → Level 1\n\n"
                    "Use `/setadminrole` to configure custom permissions."
                )

            # Add permission level explanation
            embed.add_field(
                name="Permission Levels",
                value="**Level 3 (Owner):** All commands including owner-level settings\n"
                      "**Level 2 (Admin):** Most commands, can manage strikes/bans\n"
                      "**Level 1 (Mod):** Basic moderation commands",
                inline=False
            )

            await interaction.response.send_message(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Error in /adminroles: {e}", exc_info=True)
            await interaction.response.send_message(
                "An error occurred while listing admin roles.",
                ephemeral=True
            )

    @app_commands.command(
        name="setchannel",
        description="Set a channel for a specific purpose"
    )
    @app_commands.guild_only()
    @app_commands.describe(
        purpose="What the channel will be used for",
        channel="The channel to use"
    )
    @app_commands.choices(purpose=[
        app_commands.Choice(name="Logs (audit log messages)", value="logs"),
        app_commands.Choice(name="Announcements (default announce channel)", value="announcements"),
        app_commands.Choice(name="Rules", value="rules"),
        app_commands.Choice(name="Role Selection", value="role_selection"),
    ])
    async def set_channel(self, interaction: discord.Interaction,
                          purpose: str,
                          channel: discord.TextChannel):
        """Set a channel for a specific purpose."""

        if not await require_admin(interaction):
            return

        try:
            guild_id = interaction.guild_id
            GuildQueries.set_channel(guild_id, purpose, channel.id)

            AuditQueries.log(
                guild_id=guild_id,
                action_type=AuditQueries.ACTION_CONFIG_CHANGE,
                performed_by_id=interaction.user.id,
                performed_by_name=str(interaction.user),
                details={
                    'setting': 'channel',
                    'purpose': purpose,
                    'channel_id': channel.id
                }
            )

            await interaction.response.send_message(
                f"Channel {channel.mention} set for **{purpose}**.",
                ephemeral=True
            )

        except Exception as e:
            logger.error(f"Error in /setchannel: {e}", exc_info=True)
            await interaction.response.send_message(
                "An error occurred while setting the channel.",
                ephemeral=True
            )

    @app_commands.command(
        name="feature",
        description="Enable or disable a feature"
    )
    @app_commands.guild_only()
    @app_commands.describe(
        feature="The feature to toggle",
        enabled="Enable or disable the feature"
    )
    @app_commands.choices(feature=[
        app_commands.Choice(name="Strikes", value="strikes"),
        app_commands.Choice(name="Tickets", value="tickets"),
        app_commands.Choice(name="Player Linking", value="player_linking"),
        app_commands.Choice(name="Role Selection", value="role_selection"),
        app_commands.Choice(name="Announcements", value="announcements"),
        app_commands.Choice(name="Audit Log", value="audit_log"),
        app_commands.Choice(name="Auto-Ban on 3rd Strike", value="auto_ban"),
        app_commands.Choice(name="DM Notifications", value="dm_notifications"),
    ])
    async def toggle_feature(self, interaction: discord.Interaction,
                             feature: str,
                             enabled: bool):
        """Enable or disable a feature."""

        if not await require_admin(interaction, min_level=2):
            return

        try:
            guild_id = interaction.guild_id
            GuildQueries.set_feature(guild_id, feature, enabled)

            AuditQueries.log(
                guild_id=guild_id,
                action_type=AuditQueries.ACTION_FEATURE_TOGGLE,
                performed_by_id=interaction.user.id,
                performed_by_name=str(interaction.user),
                details={
                    'feature': feature,
                    'enabled': enabled
                }
            )

            status = "enabled" if enabled else "disabled"
            await interaction.response.send_message(
                f"Feature **{feature}** has been **{status}**.",
                ephemeral=True
            )

        except Exception as e:
            logger.error(f"Error in /feature: {e}", exc_info=True)
            await interaction.response.send_message(
                "An error occurred while toggling the feature.",
                ephemeral=True
            )

    @app_commands.command(
        name="help",
        description="List all available commands"
    )
    @app_commands.guild_only()
    async def help_command(self, interaction: discord.Interaction):
        """Display help information."""

        embed = discord.Embed(
            title="TBNManager Commands",
            description="Here are all available commands:",
            color=discord.Color.green()
        )

        # Player commands
        player_cmds = [
            "`/alderonid` - Link your Discord to your Alderon ID",
            "`/playerid` - Look up player info",
            "`/myid` - View your linked ID",
        ]
        embed.add_field(
            name="Player Commands",
            value="\n".join(player_cmds),
            inline=False
        )

        # Strike commands
        strike_cmds = [
            "`/addstrike` - Add a strike to a player (opens form)",
            "`/strikes` - View active strikes (last 3)",
            "`/strikehistory` - View full strike history",
            "`/removestrike` - Remove a specific strike",
            "`/clearstrikes` - Clear all active strikes for a player",
            "`/ban` - Directly ban a player (opens form)",
            "`/wipehistory` - Permanently delete all records for a player",
            "`/recentstrikes` - View recent strikes server-wide",
            "`/unban` - Unban a player",
            "`/bans` - List all banned players",
        ]
        embed.add_field(
            name="Strike & Ban Commands (Admin)",
            value="\n".join(strike_cmds),
            inline=False
        )

        # Moderation commands
        mod_cmds = [
            "`/announce` - Send a formatted announcement (opens form)",
            "`/say` - Send a message as the bot",
            "`/clear` - Delete messages from a channel",
            "`/rolepanel` - Create a role selection panel",
            "`/serverinfo` - View server information",
            "`/userinfo` - View user information",
        ]
        embed.add_field(
            name="Moderation Commands (Admin)",
            value="\n".join(mod_cmds),
            inline=False
        )

        # Config commands
        config_cmds = [
            "`/setup` - View complete bot configuration",
            "`/adminroles` - View configured permission roles",
            "`/setadminrole` - Add/update a role's permission level",
            "`/removeadminrole` - Remove a role from permissions",
            "`/setchannel` - Set a channel for logs, announcements, etc.",
            "`/feature` - Enable/disable bot features",
        ]
        embed.add_field(
            name="Configuration Commands (Admin)",
            value="\n".join(config_cmds),
            inline=False
        )

        # Ticket commands
        ticket_cmds = [
            "`/ticketpanel` - Create a new ticket panel",
            "`/addbutton` - Add a button to a ticket panel",
            "`/refreshpanel` - Refresh a panel after changes",
            "`/listpanels` - List all ticket panels",
            "`/tickets` - View all open tickets",
            "`/close` - Close current ticket (in ticket channel)",
            "`/claim` - Claim a ticket to handle it",
            "`/adduser` / `/removeuser` - Manage ticket participants",
        ]
        embed.add_field(
            name="Ticket Commands (Admin)",
            value="\n".join(ticket_cmds),
            inline=False
        )

        embed.set_footer(text="TBNManager - Server Administration Bot | Use /adminroles to configure permissions")

        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    """Load the ConfigCommands cog."""
    await bot.add_cog(ConfigCommands(bot))
