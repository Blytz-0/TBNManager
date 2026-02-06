# cogs/tickets/tickets_panel.py
"""
Tickets Panel - Unified ticket management interface

Provides a dropdown-based interface for ticket system management.
"""

import discord
from discord import app_commands
from discord.ext import commands
from database.queries import GuildQueries
from services.permissions import get_user_allowed_commands
from services import tickets_service
import logging

logger = logging.getLogger(__name__)


TICKETS_ACTIONS = [
    ("Create Panel", "Create new ticket panel", "inpanel_tickets_createpanel", "➕"),
    ("List Panels", "View all ticket panels", "inpanel_tickets_listpanels", "📑"),
    ("List Tickets", "View all open tickets", "inpanel_tickets_list", "📋"),
    ("Close Ticket", "Close current ticket", "inpanel_tickets_close", "🔒"),
    ("Claim Ticket", "Claim ticket to handle", "inpanel_tickets_claim", "🙋"),
    ("Add User", "Add user to ticket", "inpanel_tickets_adduser", "➕"),
    ("Remove User", "Remove user from ticket", "inpanel_tickets_removeuser", "➖"),
    ("Add Button", "Add button to panel (Coming Soon)", "inpanel_tickets_addbutton", "🔘"),
    ("Refresh Panel", "Refresh panel (Coming Soon)", "inpanel_tickets_refresh", "🔄"),
]


class TicketsCommandSelect(discord.ui.Select):
    def __init__(self, cog, user_permissions: set, panel_message=None):
        self.cog = cog
        self.user_permissions = user_permissions
        self.panel_message = panel_message
        options = []
        for label, desc, permission, emoji in TICKETS_ACTIONS:
            if permission in user_permissions:
                options.append(discord.SelectOption(label=label, description=desc, value=permission, emoji=emoji))

        super().__init__(placeholder="Choose a ticket action...", options=options, row=0)

    async def callback(self, interaction: discord.Interaction):
        selected = self.values[0]

        # Route to appropriate action handler
        if selected == "inpanel_tickets_createpanel":
            await self.cog._action_create_panel(interaction, self.panel_message, self.user_permissions)
        elif selected == "inpanel_tickets_listpanels":
            await self.cog._action_list_panels(interaction, self.panel_message, self.user_permissions)
        elif selected == "inpanel_tickets_list":
            await self.cog._action_list_tickets(interaction, self.panel_message, self.user_permissions)
        elif selected == "inpanel_tickets_close":
            await self.cog._action_close_ticket(interaction, self.panel_message, self.user_permissions)
        elif selected == "inpanel_tickets_claim":
            await self.cog._action_claim_ticket(interaction, self.panel_message, self.user_permissions)
        elif selected == "inpanel_tickets_adduser":
            await self.cog._action_add_user(interaction, self.panel_message, self.user_permissions)
        elif selected == "inpanel_tickets_removeuser":
            await self.cog._action_remove_user(interaction, self.panel_message, self.user_permissions)
        elif selected == "inpanel_tickets_addbutton":
            await self.cog._action_add_button(interaction, self.panel_message, self.user_permissions)
        elif selected == "inpanel_tickets_refresh":
            await self.cog._action_refresh_panel(interaction, self.panel_message, self.user_permissions)


class TicketsCommandView(discord.ui.View):
    def __init__(self, cog, user_permissions: set, panel_message=None):
        super().__init__(timeout=300)
        self.cog = cog
        self.panel_message = panel_message
        self.add_item(TicketsCommandSelect(cog, user_permissions, panel_message))


class TicketsPanel(commands.GroupCog, name="tickets"):
    """Tickets Panel - unified ticket management interface."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        super().__init__()

    @app_commands.command(name="panel", description="Open Tickets control panel")
    @app_commands.guild_only()
    async def tickets_panel(self, interaction: discord.Interaction):
        """Show the Tickets control panel."""
        user_permissions = get_user_allowed_commands(interaction.guild_id, interaction.user)
        inpanel_permissions = {perm for perm in user_permissions if perm.startswith('inpanel_tickets_')}

        if not inpanel_permissions:
            await interaction.response.send_message(
                "You don't have permission to use any ticket panel features.",
                ephemeral=True
            )
            return

        embed = discord.Embed(
            title="🎫 Tickets Panel",
            description="Select an action from the dropdown below to manage tickets.",
            color=discord.Color.blue()
        )
        embed.set_footer(text="Select an action from the menu")

        # Send initial message without view
        await interaction.response.send_message(embed=embed, ephemeral=True)

        # Get the message object and create view with message reference for refresh capability
        panel_message = await interaction.original_response()
        view = TicketsCommandView(self, inpanel_permissions, panel_message)

        # Edit message to add the view
        await panel_message.edit(view=view)

    @app_commands.command(name="help", description="Show Tickets panel help")
    @app_commands.guild_only()
    async def tickets_help(self, interaction: discord.Interaction):
        """Show help for Tickets panel."""
        # Get user's allowed commands
        user_permissions = get_user_allowed_commands(interaction.guild_id, interaction.user)

        # Filter to only inpanel_tickets_* permissions
        inpanel_permissions = {perm for perm in user_permissions if perm.startswith('inpanel_tickets_')}

        # Build list of available actions
        available_actions = []
        for label, desc, permission, emoji in TICKETS_ACTIONS:
            if permission in inpanel_permissions:
                available_actions.append((label, desc))

        # Create help embed
        embed = discord.Embed(
            title="🎫 Tickets Panel Help",
            description="Support ticket system management commands.",
            color=discord.Color.blue()
        )

        # Access instructions
        embed.add_field(
            name="Access Panel",
            value="`/tickets panel` - Open the Tickets panel\n"
                  "`/panel` → Select Tickets - Via main launcher",
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

    async def _action_create_panel(self, interaction: discord.Interaction, panel_message=None, user_permissions=None):
        """Create panel - opens modal for panel creation."""
        modal = CreatePanelModal(self, panel_message, user_permissions)
        await interaction.response.send_modal(modal)

    async def _action_list_tickets(self, interaction: discord.Interaction, panel_message=None, user_permissions=None):
        """List tickets - immediate action."""
        await tickets_service.list_open_tickets(interaction)

        # Refresh the panel dropdown to allow reselection
        if panel_message and user_permissions:
            await self._refresh_panel(panel_message, user_permissions)

    async def _action_close_ticket(self, interaction: discord.Interaction, panel_message=None, user_permissions=None):
        """Close ticket - opens modal for close reason."""
        modal = CloseTicketModal(self, panel_message, user_permissions)
        await interaction.response.send_modal(modal)

    async def _action_list_panels(self, interaction: discord.Interaction, panel_message=None, user_permissions=None):
        """List panels - immediate action."""
        await tickets_service.list_panels(interaction)

        # Refresh the panel dropdown to allow reselection
        if panel_message and user_permissions:
            await self._refresh_panel(panel_message, user_permissions)

    async def _action_claim_ticket(self, interaction: discord.Interaction, panel_message=None, user_permissions=None):
        """Claim ticket - immediate action."""
        await tickets_service.claim_ticket(interaction)

        # Refresh the panel dropdown to allow reselection
        if panel_message and user_permissions:
            await self._refresh_panel(panel_message, user_permissions)

    async def _action_add_user(self, interaction: discord.Interaction, panel_message=None, user_permissions=None):
        """Add user - opens modal for user selection."""
        modal = AddUserModal(self, panel_message, user_permissions)
        await interaction.response.send_modal(modal)

    async def _action_remove_user(self, interaction: discord.Interaction, panel_message=None, user_permissions=None):
        """Remove user - opens modal for user selection."""
        modal = RemoveUserModal(self, panel_message, user_permissions)
        await interaction.response.send_modal(modal)

    async def _action_add_button(self, interaction: discord.Interaction, panel_message=None, user_permissions=None):
        """Add button - placeholder for future implementation."""
        await interaction.response.send_message(
            "🔘 **Add Button to Panel**\n\n"
            "This feature allows adding custom buttons to ticket panels.\n\n"
            "⚠️ **Status:** Coming soon - requires panel view integration",
            ephemeral=True
        )

        # Refresh the panel dropdown to allow reselection
        if panel_message and user_permissions:
            await self._refresh_panel(panel_message, user_permissions)

    async def _action_refresh_panel(self, interaction: discord.Interaction, panel_message=None, user_permissions=None):
        """Refresh panel - placeholder for future implementation."""
        await interaction.response.send_message(
            "🔄 **Refresh Ticket Panel**\n\n"
            "This feature refreshes panel messages to apply button changes.\n\n"
            "⚠️ **Status:** Coming soon - requires panel view integration",
            ephemeral=True
        )

        # Refresh the panel dropdown to allow reselection
        if panel_message and user_permissions:
            await self._refresh_panel(panel_message, user_permissions)

    async def _refresh_panel(self, panel_message, user_permissions: set):
        """Refresh the panel dropdown by recreating the view."""
        try:
            embed = discord.Embed(
                title="🎫 Tickets Panel",
                description="Select an action from the dropdown below to manage tickets.",
                color=discord.Color.blue()
            )
            embed.set_footer(text="Select an action from the menu")

            # Create fresh view with reset dropdown
            view = TicketsCommandView(self, user_permissions, panel_message)

            # Edit the panel message to refresh the dropdown
            await panel_message.edit(embed=embed, view=view)
        except Exception as e:
            logger.error(f"Error refreshing tickets panel: {e}", exc_info=True)


# ==========================================
# MODAL CLASSES
# ==========================================

class CreatePanelModal(discord.ui.Modal, title="Create Ticket Panel"):
    """Modal for creating a new ticket panel."""

    channel_id = discord.ui.TextInput(
        label="Channel ID",
        placeholder="Enter the channel ID where the panel will be posted",
        required=True,
        max_length=20
    )

    title_input = discord.ui.TextInput(
        label="Panel Title",
        placeholder="e.g., Support Tickets",
        required=True,
        max_length=100
    )

    description_input = discord.ui.TextInput(
        label="Panel Description",
        placeholder="Describe what this ticket panel is for...",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=500
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

            # Create the panel
            await tickets_service.create_ticket_panel(
                interaction,
                channel,
                self.title_input.value,
                self.description_input.value
            )

        except Exception as e:
            logger.error(f"Error in create panel modal: {e}", exc_info=True)
            await interaction.response.send_message(
                "An error occurred.",
                ephemeral=True
            )

        # Refresh the panel dropdown to allow reselection
        if self.panel_message and self.user_permissions:
            await self.cog._refresh_panel(self.panel_message, self.user_permissions)


class CloseTicketModal(discord.ui.Modal, title="Close Ticket"):
    """Modal for closing a ticket."""

    reason = discord.ui.TextInput(
        label="Close Reason",
        placeholder="Why is this ticket being closed?",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=500
    )

    def __init__(self, cog, panel_message=None, user_permissions=None):
        super().__init__()
        self.cog = cog
        self.panel_message = panel_message
        self.user_permissions = user_permissions

    async def on_submit(self, interaction: discord.Interaction):
        """Handle modal submission."""
        # Close the ticket
        await tickets_service.close_ticket_from_channel(
            interaction,
            self.reason.value
        )

        # Note: Panel refresh happens automatically after ticket closes (channel gets deleted)


class AddUserModal(discord.ui.Modal, title="Add User to Ticket"):
    """Modal for adding a user to the current ticket."""

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

            # Add user using service
            await tickets_service.add_user_to_ticket(interaction, user)

        except Exception as e:
            logger.error(f"Error in add user modal: {e}", exc_info=True)
            await interaction.response.send_message(
                "An error occurred.",
                ephemeral=True
            )

        # Refresh the panel dropdown to allow reselection
        if self.panel_message and self.user_permissions:
            await self.cog._refresh_panel(self.panel_message, self.user_permissions)


class RemoveUserModal(discord.ui.Modal, title="Remove User from Ticket"):
    """Modal for removing a user from the current ticket."""

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

            # Remove user using service
            await tickets_service.remove_user_from_ticket(interaction, user)

        except Exception as e:
            logger.error(f"Error in remove user modal: {e}", exc_info=True)
            await interaction.response.send_message(
                "An error occurred.",
                ephemeral=True
            )

        # Refresh the panel dropdown to allow reselection
        if self.panel_message and self.user_permissions:
            await self.cog._refresh_panel(self.panel_message, self.user_permissions)


async def setup(bot: commands.Bot):
    await bot.add_cog(TicketsPanel(bot))
