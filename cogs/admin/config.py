# cogs/admin/config.py
"""
Server Configuration Commands

Admin commands for configuring the bot per-server.
"""

import discord
from discord import app_commands
from discord.ext import commands
from database.queries import GuildQueries, AuditQueries, PermissionQueries
from services.permissions import require_admin, require_owner, require_permission, get_user_allowed_commands
from services.ini_parser import parse_permissions_ini, generate_permissions_ini, validate_permissions, get_permissions_diff, INIParseError
from config.settings import DEFAULT_FEATURES, PREMIUM_FEATURES
from config.commands import COMMAND_CATEGORIES, COMMAND_DESCRIPTIONS, FEATURE_COMMANDS, get_all_commands, get_command_count
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

            # Permission Roles - show configured roles with command counts
            configured_roles = PermissionQueries.get_configured_roles(guild_id)
            total_commands = get_command_count()

            if configured_roles:
                role_lines = []
                for role_data in configured_roles:
                    role_id = role_data['role_id']
                    allowed_count = role_data['allowed_count']

                    # Check if role still exists in guild
                    role = interaction.guild.get_role(role_id)
                    if role:
                        if allowed_count == total_commands:
                            role_lines.append(f"<@&{role_id}> - Full Access ({total_commands} commands)")
                        else:
                            role_lines.append(f"<@&{role_id}> - {allowed_count} commands")

                if role_lines:
                    role_text = "Use `/roleperms` to edit\n" + "\n".join(role_lines)
                else:
                    role_text = "No roles configured.\nUse `/roleperms` to set up permissions."
            else:
                role_text = "No roles configured.\nUse `/roleperms` to set up permissions."

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

            embed.set_footer(text="Use /roleperms, /setchannel, /feature to configure")

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
        name="roleperms",
        description="Configure command permissions for a role"
    )
    @app_commands.guild_only()
    async def role_perms(self, interaction: discord.Interaction):
        """Configure permissions for a role - shows role selector."""

        # Only server owner or users with roleperms permission can use this
        if not await require_permission(interaction, 'roleperms'):
            return

        # Show role selector dropdown
        view = RoleSelectView(interaction.guild_id)
        await interaction.response.send_message(
            "**Role Permission Configuration**\n\n"
            "Select a role to configure its command permissions.\n"
            "You can enable/disable access to each command individually.",
            view=view,
            ephemeral=True
        )

    @app_commands.command(
        name="help",
        description="List all available commands"
    )
    @app_commands.guild_only()
    async def help_command(self, interaction: discord.Interaction):
        """Display dynamic help based on user's permissions."""

        guild_id = interaction.guild_id
        member = interaction.user

        # Get commands this user can access
        allowed = get_user_allowed_commands(guild_id, member)

        # Filter by enabled features
        for feature, commands in FEATURE_COMMANDS.items():
            if not GuildQueries.is_feature_enabled(guild_id, feature):
                allowed -= set(commands)

        embed = discord.Embed(
            title="TBNManager Commands",
            description="Commands you have access to:",
            color=discord.Color.green()
        )

        # Build help by category
        for category, commands in COMMAND_CATEGORIES.items():
            visible = [cmd for cmd in commands if cmd in allowed]
            if visible:
                cmd_lines = []
                for cmd in visible:
                    desc = COMMAND_DESCRIPTIONS.get(cmd, '')
                    cmd_lines.append(f"`/{cmd}` - {desc}")
                embed.add_field(
                    name=category,
                    value="\n".join(cmd_lines),
                    inline=False
                )

        if not any(embed.fields):
            embed.description = (
                "You don't have access to any commands.\n\n"
                "Contact a server administrator to request permissions."
            )

        total_commands = get_command_count()
        embed.set_footer(text=f"You have access to {len(allowed)} of {total_commands} commands | Use /roleperms to configure")

        await interaction.response.send_message(embed=embed, ephemeral=True)


class RoleSelectView(discord.ui.View):
    """View with role selector dropdown for permission configuration."""

    def __init__(self, guild_id: int):
        super().__init__(timeout=300)  # 5 minute timeout
        self.guild_id = guild_id

    @discord.ui.select(cls=discord.ui.RoleSelect, placeholder="Select a role to configure...")
    async def role_select(self, interaction: discord.Interaction, select: discord.ui.RoleSelect):
        role = select.values[0]

        # Don't allow configuring @everyone or bot roles
        if role.is_default():
            await interaction.response.send_message(
                "Cannot configure permissions for @everyone.",
                ephemeral=True
            )
            return

        if role.is_bot_managed():
            await interaction.response.send_message(
                "Cannot configure permissions for bot-managed roles.",
                ephemeral=True
            )
            return

        # Get current permissions for this role
        current = PermissionQueries.get_role_permissions(interaction.guild_id, role.id)
        ini_text = generate_permissions_ini(current)

        # Show the modal
        modal = RolePermissionsModal(role, ini_text)
        await interaction.response.send_modal(modal)


class RolePermissionsModal(discord.ui.Modal):
    """Modal for editing role permissions in INI format."""

    def __init__(self, role: discord.Role, current_ini: str):
        # Truncate role name if needed for title
        title = f"Permissions: {role.name[:20]}"
        super().__init__(title=title)
        self.role = role

        self.permissions = discord.ui.TextInput(
            label="Edit permissions (true/false)",
            style=discord.TextStyle.paragraph,
            default=current_ini,
            max_length=4000,
            required=True,
            placeholder="[Category]\ncommand=true\ncommand=false"
        )
        self.add_item(self.permissions)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            # Parse the INI
            new_perms = parse_permissions_ini(self.permissions.value)

            # Validate - check all commands exist
            is_valid, errors = validate_permissions(new_perms)
            if not is_valid:
                await interaction.response.send_message(
                    f"**Invalid configuration:**\n" + "\n".join(f"• {e}" for e in errors),
                    ephemeral=True
                )
                return

            # Get old permissions for diff
            old_perms = PermissionQueries.get_role_permissions(interaction.guild_id, self.role.id)

            # Save to database
            PermissionQueries.set_role_permissions(
                interaction.guild_id, self.role.id, new_perms
            )

            # Calculate changes
            diff = get_permissions_diff(old_perms, new_perms)

            # Build response
            response_lines = [f"**Permissions updated for {self.role.mention}**\n"]

            if diff['added'] or diff['removed']:
                response_lines.append("**Changes:**")
                if diff['added']:
                    response_lines.append(f"+ Newly enabled: {', '.join(sorted(diff['added']))}")
                if diff['removed']:
                    response_lines.append(f"- Newly disabled: {', '.join(sorted(diff['removed']))}")
            else:
                response_lines.append("*No changes made*")

            total_commands = get_command_count()
            response_lines.append(f"\n**Total:** {diff['total_enabled']} of {total_commands} commands enabled")

            # Log the change
            AuditQueries.log(
                guild_id=interaction.guild_id,
                action_type=AuditQueries.ACTION_CONFIG_CHANGE,
                performed_by_id=interaction.user.id,
                performed_by_name=str(interaction.user),
                details={
                    'setting': 'role_permissions',
                    'role_id': self.role.id,
                    'role_name': self.role.name,
                    'commands_enabled': diff['total_enabled'],
                    'changes': len(diff['changed'])
                }
            )

            await interaction.response.send_message(
                "\n".join(response_lines),
                ephemeral=True
            )

        except INIParseError as e:
            await interaction.response.send_message(
                f"**Error parsing permissions:**\n{e}",
                ephemeral=True
            )
        except Exception as e:
            logger.error(f"Error saving permissions: {e}", exc_info=True)
            await interaction.response.send_message(
                "An error occurred while saving permissions.",
                ephemeral=True
            )


async def setup(bot: commands.Bot):
    """Load the ConfigCommands cog."""
    await bot.add_cog(ConfigCommands(bot))
