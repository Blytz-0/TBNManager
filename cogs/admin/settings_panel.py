# cogs/admin/settings_panel.py
"""
Settings Panel - Unified bot configuration interface (Owner only)

Provides a dropdown-based interface for bot settings and configuration.
"""

import discord
from discord import app_commands
from discord.ext import commands
from services.permissions import get_user_allowed_commands
from services import guild_config_service
from config.settings import DEFAULT_FEATURES, FEATURE_DESCRIPTIONS
import logging

logger = logging.getLogger(__name__)


SETTINGS_ACTIONS = [
    ("View Configuration", "View bot setup", "inpanel_settings_view", "⚙️"),
    ("Toggle Features", "Enable/disable features", "inpanel_settings_features", "🔧"),
    ("Set Channel", "Configure log channels", "inpanel_settings_setchannel", "📺"),
    ("Set Admin Role", "Add admin role", "inpanel_settings_setadminrole", "➕"),
    ("Remove Admin Role", "Remove admin role", "inpanel_settings_removeadminrole", "➖"),
    ("List Admin Roles", "View admin roles", "inpanel_settings_adminroles", "📋"),
    ("Role Permissions", "Configure role permissions", "inpanel_settings_permissions", "👥"),
    ("Premium Status", "View premium subscription (Coming Soon)", "inpanel_settings_premium", "💎"),
    ("Subscription", "Manage subscription (Coming Soon)", "inpanel_settings_subscription", "💳"),
]


class SettingsCommandSelect(discord.ui.Select):
    def __init__(self, cog, user_permissions: set, panel_message=None):
        self.cog = cog
        self.user_permissions = user_permissions
        self.panel_message = panel_message
        options = []
        for label, desc, permission, emoji in SETTINGS_ACTIONS:
            if permission in user_permissions:
                options.append(discord.SelectOption(label=label, description=desc, value=permission, emoji=emoji))

        super().__init__(placeholder="Choose a settings action...", options=options, row=0)

    async def callback(self, interaction: discord.Interaction):
        selected = self.values[0]

        # Route to appropriate action handler
        if selected == "inpanel_settings_view":
            await self.cog._action_view_config(interaction, self.panel_message, self.user_permissions)
        elif selected == "inpanel_settings_features":
            await self.cog._action_toggle_features(interaction, self.panel_message, self.user_permissions)
        elif selected == "inpanel_settings_setchannel":
            await self.cog._action_set_channel(interaction, self.panel_message, self.user_permissions)
        elif selected == "inpanel_settings_setadminrole":
            await self.cog._action_set_admin_role(interaction, self.panel_message, self.user_permissions)
        elif selected == "inpanel_settings_removeadminrole":
            await self.cog._action_remove_admin_role(interaction, self.panel_message, self.user_permissions)
        elif selected == "inpanel_settings_adminroles":
            await self.cog._action_admin_roles(interaction, self.panel_message, self.user_permissions)
        elif selected == "inpanel_settings_permissions":
            await self.cog._action_role_permissions(interaction, self.panel_message, self.user_permissions)
        elif selected == "inpanel_settings_premium":
            await self.cog._action_premium_status(interaction, self.panel_message, self.user_permissions)
        elif selected == "inpanel_settings_subscription":
            await self.cog._action_subscription(interaction, self.panel_message, self.user_permissions)


class SettingsCommandView(discord.ui.View):
    def __init__(self, cog, user_permissions: set, panel_message=None):
        super().__init__(timeout=300)
        self.cog = cog
        self.panel_message = panel_message
        self.add_item(SettingsCommandSelect(cog, user_permissions, panel_message))


class SettingsPanel(commands.GroupCog, name="settings"):
    """Settings Panel - unified bot configuration interface (Owner only)."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        super().__init__()

    @app_commands.command(name="panel", description="Open Settings control panel (Owner)")
    @app_commands.guild_only()
    async def settings_panel(self, interaction: discord.Interaction):
        """Show the Settings control panel (Owner only)."""
        # Check if user is owner
        if interaction.user.id != interaction.guild.owner_id and interaction.user.id not in []:  # Add bot owner IDs
            await interaction.response.send_message(
                "❌ Only the server owner can access the Settings panel.",
                ephemeral=True
            )
            return

        user_permissions = get_user_allowed_commands(interaction.guild_id, interaction.user)
        inpanel_permissions = {perm for perm in user_permissions if perm.startswith('inpanel_settings_')}

        if not inpanel_permissions:
            await interaction.response.send_message(
                "You don't have permission to use any settings panel features.",
                ephemeral=True
            )
            return

        embed = discord.Embed(
            title="⚙️ Settings Panel",
            description="Select an action from the dropdown below to configure the bot.\n\n"
                       "**⚠️ Owner Only** - These settings affect the entire server.",
            color=discord.Color.gold()
        )
        embed.set_footer(text="Select an action from the menu")

        # Send initial message without view
        await interaction.response.send_message(embed=embed, ephemeral=True)

        # Get the message object and create view with message reference for refresh capability
        panel_message = await interaction.original_response()
        view = SettingsCommandView(self, inpanel_permissions, panel_message)

        # Edit message to add the view
        await panel_message.edit(view=view)

    @app_commands.command(name="help", description="Show Settings panel help")
    @app_commands.guild_only()
    async def settings_help(self, interaction: discord.Interaction):
        """Show help for Settings panel."""
        # Check if user is owner
        is_owner = interaction.user.id == interaction.guild.owner_id or interaction.user.id in []  # Add bot owner IDs

        # Get user's allowed commands
        user_permissions = get_user_allowed_commands(interaction.guild_id, interaction.user)

        # Filter to only inpanel_settings_* permissions
        inpanel_permissions = {perm for perm in user_permissions if perm.startswith('inpanel_settings_')}

        # Build list of available actions
        available_actions = []
        for label, desc, permission, emoji in SETTINGS_ACTIONS:
            if permission in inpanel_permissions:
                available_actions.append((label, desc))

        # Create help embed
        embed = discord.Embed(
            title="⚙️ Settings Panel Help",
            description="Bot configuration and server settings (Owner Only).",
            color=discord.Color.gold()
        )

        # Access instructions
        if is_owner:
            embed.add_field(
                name="Access Panel",
                value="`/settings panel` - Open the Settings panel\n"
                      "`/panel` → Select Settings - Via main launcher",
                inline=False
            )
        else:
            embed.add_field(
                name="Access Panel",
                value="❌ **Owner Only** - Only the server owner can access this panel.\n"
                      "Contact the server owner to modify bot settings.",
                inline=False
            )

        # Available actions
        if available_actions and is_owner:
            actions_text = "\n".join([f"**{label}** - {desc}" for label, desc in available_actions])
            embed.add_field(name="Available Actions", value=actions_text, inline=False)
        else:
            if not is_owner:
                embed.add_field(
                    name="Available Actions",
                    value="You must be the server owner to use this panel.",
                    inline=False
                )
            else:
                embed.add_field(
                    name="Available Actions",
                    value="You don't have access to any actions.\n"
                          "Contact an administrator to configure your permissions.",
                    inline=False
                )

        # Panel access status
        if available_actions and is_owner:
            embed.set_footer(text="Panel access: ✅ Granted (Owner)")
        else:
            embed.set_footer(text="Panel access: ❌ Denied")

        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ==========================================
    # ACTION HANDLERS
    # ==========================================

    async def _action_view_config(self, interaction: discord.Interaction, panel_message=None, user_permissions=None):
        """View configuration - show current bot setup."""
        await guild_config_service.view_configuration(interaction)

        # Refresh the panel dropdown to allow reselection
        if panel_message and user_permissions:
            await self._refresh_panel(panel_message, user_permissions)

    async def _action_toggle_features(self, interaction: discord.Interaction, panel_message=None, user_permissions=None):
        """Toggle features - opens modal for feature selection."""
        modal = ToggleFeaturesModal(self, panel_message, user_permissions)
        await interaction.response.send_modal(modal)

    async def _action_set_channel(self, interaction: discord.Interaction, panel_message=None, user_permissions=None):
        """Set channel - opens modal for channel configuration."""
        modal = SetChannelModal(self, panel_message, user_permissions)
        await interaction.response.send_modal(modal)

    async def _action_set_admin_role(self, interaction: discord.Interaction, panel_message=None, user_permissions=None):
        """Set admin role - opens modal for role selection."""
        modal = SetAdminRoleModal(self, panel_message, user_permissions)
        await interaction.response.send_modal(modal)

    async def _action_remove_admin_role(self, interaction: discord.Interaction, panel_message=None, user_permissions=None):
        """Remove admin role - opens modal for role selection."""
        modal = RemoveAdminRoleModal(self, panel_message, user_permissions)
        await interaction.response.send_modal(modal)

    async def _action_admin_roles(self, interaction: discord.Interaction, panel_message=None, user_permissions=None):
        """List admin roles - immediate action."""
        await guild_config_service.list_admin_roles(interaction)

        # Refresh the panel dropdown to allow reselection
        if panel_message and user_permissions:
            await self._refresh_panel(panel_message, user_permissions)

    async def _action_role_permissions(self, interaction: discord.Interaction, panel_message=None, user_permissions=None):
        """Role permissions - show info message."""
        await interaction.response.send_message(
            "⚠️ **Role Permissions Configuration**\n\n"
            "Role permissions require advanced editing.\n"
            "Please use `/rolepermissions` command for INI-based permission configuration.",
            ephemeral=True
        )

        # Refresh the panel dropdown to allow reselection
        if panel_message and user_permissions:
            await self._refresh_panel(panel_message, user_permissions)

    async def _action_premium_status(self, interaction: discord.Interaction, panel_message=None, user_permissions=None):
        """Premium status - placeholder for future implementation."""
        await interaction.response.send_message(
            "💎 **Premium Status**\n\n"
            "This feature is coming soon! It will display:\n"
            "• Current subscription tier\n"
            "• Active premium features\n"
            "• Subscription expiry date\n"
            "• Usage statistics\n\n"
            "⚠️ **Status:** Not yet implemented",
            ephemeral=True
        )

        # Refresh the panel dropdown to allow reselection
        if panel_message and user_permissions:
            await self._refresh_panel(panel_message, user_permissions)

    async def _action_subscription(self, interaction: discord.Interaction, panel_message=None, user_permissions=None):
        """Subscription - placeholder for future implementation."""
        await interaction.response.send_message(
            "💳 **Subscription Management**\n\n"
            "This feature is coming soon! It will allow you to:\n"
            "• View available premium tiers\n"
            "• Upgrade/downgrade subscription\n"
            "• Manage billing information\n"
            "• Cancel subscription\n\n"
            "⚠️ **Status:** Not yet implemented",
            ephemeral=True
        )

        # Refresh the panel dropdown to allow reselection
        if panel_message and user_permissions:
            await self._refresh_panel(panel_message, user_permissions)

    async def _refresh_panel(self, panel_message, user_permissions: set):
        """Refresh the panel dropdown by recreating the view."""
        try:
            embed = discord.Embed(
                title="⚙️ Settings Panel",
                description="Select an action from the dropdown below to configure the bot.\n\n"
                           "**⚠️ Owner Only** - These settings affect the entire server.",
                color=discord.Color.gold()
            )
            embed.set_footer(text="Select an action from the menu")

            # Create fresh view with reset dropdown
            view = SettingsCommandView(self, user_permissions, panel_message)

            # Edit the panel message to refresh the dropdown
            await panel_message.edit(embed=embed, view=view)
        except Exception as e:
            logger.error(f"Error refreshing settings panel: {e}", exc_info=True)


# ==========================================
# MODAL CLASSES
# ==========================================

class ToggleFeaturesModal(discord.ui.Modal, title="Toggle Features"):
    """Modal for toggling features on/off."""

    feature_name = discord.ui.TextInput(
        label="Feature Name",
        placeholder="e.g., strikes, tickets, player_linking",
        required=True,
        max_length=50
    )

    action = discord.ui.TextInput(
        label="Action (enable/disable)",
        placeholder="enable or disable",
        required=True,
        max_length=10
    )

    def __init__(self, cog, panel_message=None, user_permissions=None):
        super().__init__()
        self.cog = cog
        self.panel_message = panel_message
        self.user_permissions = user_permissions

    async def on_submit(self, interaction: discord.Interaction):
        """Handle modal submission."""
        feature = self.feature_name.value.strip().lower()
        action = self.action.value.strip().lower()

        if action not in ["enable", "disable"]:
            await interaction.response.send_message(
                "❌ Invalid action. Use `enable` or `disable`.",
                ephemeral=True
            )
            return

        enabled = (action == "enable")

        # Use service to toggle feature
        await guild_config_service.toggle_feature(interaction, feature, enabled)

        # Refresh the panel dropdown to allow reselection
        if self.panel_message and self.user_permissions:
            await self.cog._refresh_panel(self.panel_message, self.user_permissions)


class SetChannelModal(discord.ui.Modal, title="Set Channel"):
    """Modal for setting a channel for a specific purpose."""

    purpose = discord.ui.TextInput(
        label="Purpose",
        placeholder="logs, announcements, rules, role_selection",
        required=True,
        max_length=30
    )

    channel_id = discord.ui.TextInput(
        label="Channel ID",
        placeholder="Enter the channel ID",
        required=True,
        max_length=20
    )

    def __init__(self, cog, panel_message=None, user_permissions=None):
        super().__init__()
        self.cog = cog
        self.panel_message = panel_message
        self.user_permissions = user_permissions

    async def on_submit(self, interaction: discord.Interaction):
        """Handle modal submission."""
        try:
            # Get the channel
            channel_id_str = self.channel_id.value.strip()
            if not channel_id_str.isdigit():
                await interaction.response.send_message(
                    "❌ Invalid channel ID. Must be a number.",
                    ephemeral=True
                )
                return

            channel = interaction.guild.get_channel(int(channel_id_str))
            if not channel or not isinstance(channel, discord.TextChannel):
                await interaction.response.send_message(
                    "❌ Channel not found or is not a text channel.",
                    ephemeral=True
                )
                return

            # Set the channel using service
            await guild_config_service.set_channel(
                interaction,
                self.purpose.value.strip().lower(),
                channel
            )

        except Exception as e:
            logger.error(f"Error in set channel modal: {e}", exc_info=True)
            await interaction.response.send_message(
                "An error occurred.",
                ephemeral=True
            )

        # Refresh the panel dropdown to allow reselection
        if self.panel_message and self.user_permissions:
            await self.cog._refresh_panel(self.panel_message, self.user_permissions)


class SetAdminRoleModal(discord.ui.Modal, title="Add Admin Role"):
    """Modal for adding an admin role."""

    role_input = discord.ui.TextInput(
        label="Role",
        placeholder="@role mention or Role ID",
        required=True,
        max_length=100
    )

    def __init__(self, cog, panel_message=None, user_permissions=None):
        super().__init__()
        self.cog = cog
        self.panel_message = panel_message
        self.user_permissions = user_permissions

    async def on_submit(self, interaction: discord.Interaction):
        """Handle modal submission."""
        try:
            role_str = self.role_input.value.strip()

            # Parse role mention or ID
            role_id = None
            if role_str.startswith('<@&') and role_str.endswith('>'):
                role_id = int(role_str[3:-1])
            elif role_str.isdigit():
                role_id = int(role_str)
            else:
                await interaction.response.send_message(
                    "❌ Invalid role format. Use @role mention or Role ID.",
                    ephemeral=True
                )
                return

            # Get the role
            role = interaction.guild.get_role(role_id)
            if not role:
                await interaction.response.send_message(
                    "❌ Role not found in this server.",
                    ephemeral=True
                )
                return

            # Add admin role using service
            await guild_config_service.set_admin_role(interaction, role)

        except Exception as e:
            logger.error(f"Error in set admin role modal: {e}", exc_info=True)
            await interaction.response.send_message(
                "An error occurred.",
                ephemeral=True
            )

        # Refresh the panel dropdown to allow reselection
        if self.panel_message and self.user_permissions:
            await self.cog._refresh_panel(self.panel_message, self.user_permissions)


class RemoveAdminRoleModal(discord.ui.Modal, title="Remove Admin Role"):
    """Modal for removing an admin role."""

    role_input = discord.ui.TextInput(
        label="Role",
        placeholder="@role mention or Role ID",
        required=True,
        max_length=100
    )

    def __init__(self, cog, panel_message=None, user_permissions=None):
        super().__init__()
        self.cog = cog
        self.panel_message = panel_message
        self.user_permissions = user_permissions

    async def on_submit(self, interaction: discord.Interaction):
        """Handle modal submission."""
        try:
            role_str = self.role_input.value.strip()

            # Parse role mention or ID
            role_id = None
            if role_str.startswith('<@&') and role_str.endswith('>'):
                role_id = int(role_str[3:-1])
            elif role_str.isdigit():
                role_id = int(role_str)
            else:
                await interaction.response.send_message(
                    "❌ Invalid role format. Use @role mention or Role ID.",
                    ephemeral=True
                )
                return

            # Get the role
            role = interaction.guild.get_role(role_id)
            if not role:
                await interaction.response.send_message(
                    "❌ Role not found in this server.",
                    ephemeral=True
                )
                return

            # Remove admin role using service
            await guild_config_service.remove_admin_role(interaction, role)

        except Exception as e:
            logger.error(f"Error in remove admin role modal: {e}", exc_info=True)
            await interaction.response.send_message(
                "An error occurred.",
                ephemeral=True
            )

        # Refresh the panel dropdown to allow reselection
        if self.panel_message and self.user_permissions:
            await self.cog._refresh_panel(self.panel_message, self.user_permissions)


async def setup(bot: commands.Bot):
    await bot.add_cog(SettingsPanel(bot))
