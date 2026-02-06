# cogs/moderation/moderation_panel.py
"""
Moderation Panel - Unified moderation tools interface

Provides a dropdown-based interface for moderation tools.
"""

import discord
from discord import app_commands
from discord.ext import commands
from services.permissions import get_user_allowed_commands
from services import moderation_service
import logging

logger = logging.getLogger(__name__)


MODERATION_ACTIONS = [
    ("Announcement", "Send formatted announcement", "inpanel_moderation_announce", "📢"),
    ("Say", "Send message as bot", "inpanel_moderation_say", "💬"),
    ("Clear Messages", "Delete messages from channel", "inpanel_moderation_clear", "🗑️"),
    ("Server Info", "View server information", "inpanel_moderation_serverinfo", "ℹ️"),
    ("User Info", "View user information", "inpanel_moderation_userinfo", "👤"),
    ("Role Panel", "Create role selection panel", "inpanel_moderation_rolepanel", "🎭"),
    ("AI Detection", "Run AI detection (Coming Soon)", "inpanel_moderation_aidetect", "🤖"),
    ("AI Settings", "Configure AI detection (Coming Soon)", "inpanel_moderation_aisettings", "⚙️"),
]


class ModerationCommandSelect(discord.ui.Select):
    def __init__(self, cog, user_permissions: set, panel_message=None):
        self.cog = cog
        self.user_permissions = user_permissions
        self.panel_message = panel_message
        options = []
        for label, desc, permission, emoji in MODERATION_ACTIONS:
            if permission in user_permissions:
                options.append(discord.SelectOption(label=label, description=desc, value=permission, emoji=emoji))

        super().__init__(placeholder="Choose a moderation action...", options=options, row=0)

    async def callback(self, interaction: discord.Interaction):
        selected = self.values[0]

        # Route to appropriate action handler
        if selected == "inpanel_moderation_announce":
            await self.cog._action_announce(interaction, self.panel_message, self.user_permissions)
        elif selected == "inpanel_moderation_say":
            await self.cog._action_say(interaction, self.panel_message, self.user_permissions)
        elif selected == "inpanel_moderation_clear":
            await self.cog._action_clear(interaction, self.panel_message, self.user_permissions)
        elif selected == "inpanel_moderation_serverinfo":
            await self.cog._action_server_info(interaction, self.panel_message, self.user_permissions)
        elif selected == "inpanel_moderation_userinfo":
            await self.cog._action_user_info(interaction, self.panel_message, self.user_permissions)
        elif selected == "inpanel_moderation_rolepanel":
            await self.cog._action_role_panel(interaction, self.panel_message, self.user_permissions)
        elif selected == "inpanel_moderation_aidetect":
            await self.cog._action_ai_detect(interaction, self.panel_message, self.user_permissions)
        elif selected == "inpanel_moderation_aisettings":
            await self.cog._action_ai_settings(interaction, self.panel_message, self.user_permissions)


class ModerationCommandView(discord.ui.View):
    def __init__(self, cog, user_permissions: set, panel_message=None):
        super().__init__(timeout=300)
        self.cog = cog
        self.panel_message = panel_message
        self.add_item(ModerationCommandSelect(cog, user_permissions, panel_message))


class ModerationPanel(commands.GroupCog, name="moderation"):
    """Moderation Panel - unified moderation tools interface."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        super().__init__()

    @app_commands.command(name="panel", description="Open Moderation control panel")
    @app_commands.guild_only()
    async def moderation_panel(self, interaction: discord.Interaction):
        """Show the Moderation control panel."""
        user_permissions = get_user_allowed_commands(interaction.guild_id, interaction.user)
        inpanel_permissions = {perm for perm in user_permissions if perm.startswith('inpanel_moderation_')}

        if not inpanel_permissions:
            await interaction.response.send_message(
                "You don't have permission to use any moderation panel features.",
                ephemeral=True
            )
            return

        embed = discord.Embed(
            title="🛡️ Moderation Panel",
            description="Select an action from the dropdown below for moderation tools.",
            color=discord.Color.green()
        )
        embed.set_footer(text="Select an action from the menu")

        # Send initial message without view
        await interaction.response.send_message(embed=embed, ephemeral=True)

        # Get the message object and create view with message reference for refresh capability
        panel_message = await interaction.original_response()
        view = ModerationCommandView(self, inpanel_permissions, panel_message)

        # Edit message to add the view
        await panel_message.edit(view=view)

    @app_commands.command(name="help", description="Show Moderation panel help")
    @app_commands.guild_only()
    async def moderation_help(self, interaction: discord.Interaction):
        """Show help for Moderation panel."""
        # Get user's allowed commands
        user_permissions = get_user_allowed_commands(interaction.guild_id, interaction.user)

        # Filter to only inpanel_moderation_* permissions
        inpanel_permissions = {perm for perm in user_permissions if perm.startswith('inpanel_moderation_')}

        # Build list of available actions
        available_actions = []
        for label, desc, permission, emoji in MODERATION_ACTIONS:
            if permission in inpanel_permissions:
                available_actions.append((label, desc))

        # Create help embed
        embed = discord.Embed(
            title="🛡️ Moderation Panel Help",
            description="Server moderation tools and commands.",
            color=discord.Color.green()
        )

        # Access instructions
        embed.add_field(
            name="Access Panel",
            value="`/moderation panel` - Open the Moderation panel\n"
                  "`/panel` → Select Moderation - Via main launcher",
            inline=False
        )

        # Available actions
        if available_actions:
            actions_text = "\n".join([f"**{label}** - {desc}" for label, desc in available_actions])
            embed.add_field(name="Available Actions", value=actions_text, inline=False)
        else:
            embed.add_field(
                name="Available Actions",
                value="You don't have access to any actions.\n"
                      "Contact an administrator to configure your permissions.",
                inline=False
            )

        # Panel access status
        if available_actions:
            embed.set_footer(text="Panel access: ✅ Granted")
        else:
            embed.set_footer(text="Panel access: ❌ Denied")

        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ==========================================
    # ACTION HANDLERS
    # ==========================================

    async def _action_announce(self, interaction: discord.Interaction, panel_message=None, user_permissions=None):
        """Announcement - opens modal for announcement creation."""
        modal = AnnouncementModal(self, panel_message, user_permissions)
        await interaction.response.send_modal(modal)

    async def _action_server_info(self, interaction: discord.Interaction, panel_message=None, user_permissions=None):
        """Server info - immediate action."""
        await moderation_service.show_server_info(interaction)

        # Refresh the panel dropdown to allow reselection
        if panel_message and user_permissions:
            await self._refresh_panel(panel_message, user_permissions)

    async def _action_user_info(self, interaction: discord.Interaction, panel_message=None, user_permissions=None):
        """User info - opens modal for user selection."""
        modal = UserInfoModal(self, panel_message, user_permissions)
        await interaction.response.send_modal(modal)

    async def _action_say(self, interaction: discord.Interaction, panel_message=None, user_permissions=None):
        """Say - opens modal to send message as bot."""
        modal = SayModal(self, panel_message, user_permissions)
        await interaction.response.send_modal(modal)

    async def _action_clear(self, interaction: discord.Interaction, panel_message=None, user_permissions=None):
        """Clear messages - opens modal for deletion parameters."""
        modal = ClearMessagesModal(self, panel_message, user_permissions)
        await interaction.response.send_modal(modal)

    async def _action_role_panel(self, interaction: discord.Interaction, panel_message=None, user_permissions=None):
        """Role panel - placeholder for now, will implement after checking roles.py."""
        await interaction.response.send_message(
            "🎭 **Role Panel Creation**\n\n"
            "This feature allows creating interactive role selection panels.\n\n"
            "⚠️ **Status:** Coming soon - needs integration with roles system",
            ephemeral=True
        )

        # Refresh the panel dropdown to allow reselection
        if panel_message and user_permissions:
            await self._refresh_panel(panel_message, user_permissions)

    async def _action_ai_detect(self, interaction: discord.Interaction, panel_message=None, user_permissions=None):
        """AI detection - placeholder for future implementation."""
        await interaction.response.send_message(
            "🤖 **AI Detection**\n\n"
            "This feature is coming soon! It will allow you to:\n"
            "• Scan messages for AI-generated content\n"
            "• Set detection sensitivity levels\n"
            "• Review flagged messages\n\n"
            "⚠️ **Status:** Not yet implemented",
            ephemeral=True
        )

        # Refresh the panel dropdown to allow reselection
        if panel_message and user_permissions:
            await self._refresh_panel(panel_message, user_permissions)

    async def _action_ai_settings(self, interaction: discord.Interaction, panel_message=None, user_permissions=None):
        """AI settings - placeholder for future implementation."""
        await interaction.response.send_message(
            "⚙️ **AI Detection Settings**\n\n"
            "This feature is coming soon! It will allow you to:\n"
            "• Configure detection thresholds\n"
            "• Enable/disable AI detection\n"
            "• Manage detection models\n\n"
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
                title="🛡️ Moderation Panel",
                description="Select an action from the dropdown below for moderation tools.",
                color=discord.Color.green()
            )
            embed.set_footer(text="Select an action from the menu")

            # Create fresh view with reset dropdown
            view = ModerationCommandView(self, user_permissions, panel_message)

            # Edit the panel message to refresh the dropdown
            await panel_message.edit(embed=embed, view=view)
        except Exception as e:
            logger.error(f"Error refreshing moderation panel: {e}", exc_info=True)


# ==========================================
# MODAL CLASSES
# ==========================================

class AnnouncementModal(discord.ui.Modal, title="Send Announcement"):
    """Modal for creating an announcement."""

    title_input = discord.ui.TextInput(
        label="Announcement Title",
        placeholder="Enter the announcement title",
        required=True,
        max_length=100
    )

    message_input = discord.ui.TextInput(
        label="Message",
        placeholder="Enter your message...",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=2000
    )

    channel_id = discord.ui.TextInput(
        label="Channel ID",
        placeholder="Enter the channel ID to send to",
        required=True,
        max_length=20
    )

    color = discord.ui.TextInput(
        label="Color (optional)",
        placeholder="red, blue, green, yellow, purple, orange",
        required=False,
        default="blue",
        max_length=10
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

            # Send announcement
            await moderation_service.send_announcement(
                interaction,
                self.title_input.value,
                self.message_input.value,
                channel,
                self.color.value if self.color.value else "blue"
            )

        except Exception as e:
            logger.error(f"Error in announcement modal: {e}", exc_info=True)
            await interaction.response.send_message(
                "An error occurred.",
                ephemeral=True
            )

        # Refresh the panel dropdown to allow reselection
        if self.panel_message and self.user_permissions:
            await self.cog._refresh_panel(self.panel_message, self.user_permissions)


class UserInfoModal(discord.ui.Modal, title="View User Info"):
    """Modal for looking up user information."""

    user_input = discord.ui.TextInput(
        label="User",
        placeholder="@user mention or User ID",
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
            user_str = self.user_input.value.strip()

            # Parse user mention or ID
            user_id = None
            if user_str.startswith('<@') and user_str.endswith('>'):
                user_id = int(user_str[2:-1].replace('!', ''))
            elif user_str.isdigit():
                user_id = int(user_str)
            else:
                await interaction.response.send_message(
                    "❌ Invalid user format. Use @user mention or User ID.",
                    ephemeral=True
                )
                return

            # Get the user
            user = interaction.guild.get_member(user_id)
            if not user:
                await interaction.response.send_message(
                    "❌ User not found in this server.",
                    ephemeral=True
                )
                return

            # Show user info
            await moderation_service.show_user_info(interaction, user)

        except Exception as e:
            logger.error(f"Error in user info modal: {e}", exc_info=True)
            await interaction.response.send_message(
                "An error occurred.",
                ephemeral=True
            )

        # Refresh the panel dropdown to allow reselection
        if self.panel_message and self.user_permissions:
            await self.cog._refresh_panel(self.panel_message, self.user_permissions)


class SayModal(discord.ui.Modal, title="Send Message as Bot"):
    """Modal for sending a plain message as the bot."""

    message_input = discord.ui.TextInput(
        label="Message",
        placeholder="Enter the message to send...",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=2000
    )

    channel_id = discord.ui.TextInput(
        label="Channel ID",
        placeholder="Enter the channel ID to send to",
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

            # Send the message using service
            await moderation_service.send_bot_message(
                interaction,
                self.message_input.value,
                channel
            )

        except Exception as e:
            logger.error(f"Error in say modal: {e}", exc_info=True)
            await interaction.response.send_message(
                "An error occurred.",
                ephemeral=True
            )

        # Refresh the panel dropdown to allow reselection
        if self.panel_message and self.user_permissions:
            await self.cog._refresh_panel(self.panel_message, self.user_permissions)


class ClearMessagesModal(discord.ui.Modal, title="Clear Messages"):
    """Modal for clearing messages from a channel."""

    amount = discord.ui.TextInput(
        label="Amount (1-100)",
        placeholder="Number of messages to delete",
        required=True,
        max_length=3
    )

    user_input = discord.ui.TextInput(
        label="User (optional)",
        placeholder="@user mention or User ID (leave empty for all messages)",
        required=False,
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
            # Parse amount
            try:
                amount = int(self.amount.value.strip())
                if amount < 1 or amount > 100:
                    await interaction.response.send_message(
                        "❌ Amount must be between 1 and 100.",
                        ephemeral=True
                    )
                    return
            except ValueError:
                await interaction.response.send_message(
                    "❌ Invalid amount. Must be a number.",
                    ephemeral=True
                )
                return

            # Parse user (optional)
            user = None
            if self.user_input.value.strip():
                user_str = self.user_input.value.strip()
                user_id = None

                # Parse user mention or ID
                if user_str.startswith('<@') and user_str.endswith('>'):
                    user_id = int(user_str[2:-1].replace('!', ''))
                elif user_str.isdigit():
                    user_id = int(user_str)
                else:
                    await interaction.response.send_message(
                        "❌ Invalid user format. Use @user mention or User ID.",
                        ephemeral=True
                    )
                    return

                user = interaction.guild.get_member(user_id)
                if not user:
                    await interaction.response.send_message(
                        "❌ User not found in this server.",
                        ephemeral=True
                    )
                    return

            # Clear messages using service
            await moderation_service.clear_messages(interaction, amount, user)

        except Exception as e:
            logger.error(f"Error in clear messages modal: {e}", exc_info=True)
            await interaction.response.send_message(
                "An error occurred.",
                ephemeral=True
            )

        # Refresh the panel dropdown to allow reselection
        if self.panel_message and self.user_permissions:
            await self.cog._refresh_panel(self.panel_message, self.user_permissions)


async def setup(bot: commands.Bot):
    await bot.add_cog(ModerationPanel(bot))
