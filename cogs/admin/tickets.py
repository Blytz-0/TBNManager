# cogs/admin/tickets.py
"""
Enhanced Ticket System Commands

Support ticket system with:
- Modal-based panel creation for better formatting
- Multiple buttons per panel with custom forms
- Pre-ticket forms for different ticket types (appeals, reports, etc.)
- Reference ID integration for strike/ban appeals
- Transcript generation
"""

import discord
from discord import app_commands
from discord.ext import commands
from database.queries import TicketQueries, GuildQueries, AuditQueries, StrikeQueries
from services.permissions import require_admin, has_admin_permission
from datetime import datetime
import logging
import json

logger = logging.getLogger(__name__)

# Button style mapping
BUTTON_STYLES = {
    1: discord.ButtonStyle.primary,    # Blue
    2: discord.ButtonStyle.secondary,  # Gray
    3: discord.ButtonStyle.success,    # Green
    4: discord.ButtonStyle.danger,     # Red
}

# Default panel description
DEFAULT_PANEL_DESCRIPTION = """**Need Help?**
Click the button below to open a support ticket.

Our team will assist you as soon as possible.
Please be patient and provide as much detail as you can."""


class TicketCommands(commands.Cog):
    """Commands for the enhanced ticket system."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ==========================================
    # TICKET PANEL CREATION (Modal-based)
    # ==========================================

    @app_commands.command(
        name="ticketpanel",
        description="Create a new ticket panel with customizable settings"
    )
    @app_commands.guild_only()
    @app_commands.describe(
        channel="Channel to post the panel in",
        category="Category where ticket channels are created",
        transcript_channel="Channel where transcripts are posted when tickets close",
        support_role="Role that can see and manage tickets"
    )
    async def create_ticket_panel(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        category: discord.CategoryChannel = None,
        transcript_channel: discord.TextChannel = None,
        support_role: discord.Role = None
    ):
        """Create a ticket panel - opens a modal for title and description."""

        if not await require_admin(interaction, min_level=2):
            return

        guild_id = interaction.guild_id
        GuildQueries.get_or_create(guild_id, interaction.guild.name)

        # Check if tickets feature is enabled
        if not GuildQueries.is_feature_enabled(guild_id, 'tickets'):
            await interaction.response.send_message(
                "Ticket system is not enabled on this server.\n"
                "Use `/feature tickets true` to enable it.",
                ephemeral=True
            )
            return

        # Show modal for panel details
        modal = CreatePanelModal(
            channel=channel,
            category=category,
            transcript_channel=transcript_channel,
            support_role=support_role
        )
        await interaction.response.send_modal(modal)

    @app_commands.command(
        name="addbutton",
        description="Add a button to an existing ticket panel"
    )
    @app_commands.guild_only()
    @app_commands.describe(
        panel_id="The ID of the panel to add the button to",
        button_type="Type of ticket this button creates",
        color="Button color (defaults based on type: support=green, appeal/report=red)"
    )
    @app_commands.choices(button_type=[
        app_commands.Choice(name="General Support", value="support"),
        app_commands.Choice(name="Strike/Ban Appeal", value="appeal"),
        app_commands.Choice(name="Rule Violation Report", value="report"),
        app_commands.Choice(name="Custom", value="custom"),
    ])
    @app_commands.choices(color=[
        app_commands.Choice(name="Blue", value=1),
        app_commands.Choice(name="Gray", value=2),
        app_commands.Choice(name="Green", value=3),
        app_commands.Choice(name="Red", value=4),
    ])
    async def add_button(
        self,
        interaction: discord.Interaction,
        panel_id: int,
        button_type: str,
        color: int = None
    ):
        """Add a button to a ticket panel."""

        if not await require_admin(interaction, min_level=2):
            return

        # Verify panel exists and belongs to this guild
        panel = TicketQueries.get_panel(panel_id)
        if not panel or panel['guild_id'] != interaction.guild_id:
            await interaction.response.send_message(
                f"Panel with ID `{panel_id}` not found in this server.",
                ephemeral=True
            )
            return

        # Check button limit (Discord allows max 5 buttons per row, 5 rows = 25 max)
        existing_buttons = TicketQueries.get_panel_buttons(panel_id)
        if len(existing_buttons) >= 5:
            await interaction.response.send_message(
                "This panel already has the maximum of 5 buttons.",
                ephemeral=True
            )
            return

        # Show the appropriate modal based on button type
        modal = AddButtonModal(panel_id=panel_id, button_type=button_type, color_override=color)
        await interaction.response.send_modal(modal)

    @app_commands.command(
        name="refreshpanel",
        description="Refresh a ticket panel to apply button changes"
    )
    @app_commands.guild_only()
    @app_commands.describe(
        panel_id="The ID of the panel to refresh"
    )
    async def refresh_panel(self, interaction: discord.Interaction, panel_id: int):
        """Refresh a ticket panel message with current buttons."""

        if not await require_admin(interaction, min_level=2):
            return

        panel = TicketQueries.get_panel(panel_id)
        if not panel or panel['guild_id'] != interaction.guild_id:
            await interaction.response.send_message(
                f"Panel with ID `{panel_id}` not found in this server.",
                ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)

        try:
            # Get the channel and message
            channel = interaction.guild.get_channel(panel['channel_id'])
            if not channel:
                await interaction.followup.send("Panel channel not found.", ephemeral=True)
                return

            # Create updated embed
            embed = discord.Embed(
                title=panel['title'],
                description=panel['description'] or "Click a button below to open a ticket.",
                color=discord.Color.blue()
            )
            embed.set_footer(text=f"{interaction.guild.name} • Support System")

            # Create view with all buttons
            view = TicketPanelView(panel_id=panel_id)

            # Try to edit existing message or send new one
            if panel['message_id']:
                try:
                    message = await channel.fetch_message(panel['message_id'])
                    await message.edit(embed=embed, view=view)
                    await interaction.followup.send(
                        f"Panel refreshed successfully!",
                        ephemeral=True
                    )
                    return
                except discord.NotFound:
                    pass

            # Send new message
            message = await channel.send(embed=embed, view=view)
            TicketQueries.update_panel_message(panel_id, message.id)

            await interaction.followup.send(
                f"Panel message recreated in {channel.mention}",
                ephemeral=True
            )

        except Exception as e:
            logger.error(f"Error refreshing panel: {e}", exc_info=True)
            await interaction.followup.send(
                "An error occurred while refreshing the panel.",
                ephemeral=True
            )

    @app_commands.command(
        name="listpanels",
        description="List all ticket panels in this server"
    )
    @app_commands.guild_only()
    async def list_panels(self, interaction: discord.Interaction):
        """List all ticket panels."""

        if not await require_admin(interaction):
            return

        panels = TicketQueries.get_guild_panels(interaction.guild_id)

        if not panels:
            await interaction.response.send_message(
                "No ticket panels found. Create one with `/ticketpanel`.",
                ephemeral=True
            )
            return

        embed = discord.Embed(
            title="Ticket Panels",
            description=f"Found **{len(panels)}** panel(s)",
            color=discord.Color.blue()
        )

        for panel in panels:
            buttons = TicketQueries.get_panel_buttons(panel['id'])
            channel = interaction.guild.get_channel(panel['channel_id'])
            channel_text = channel.mention if channel else "Unknown"

            embed.add_field(
                name=f"Panel #{panel['id']}: {panel['title']}",
                value=f"**Channel:** {channel_text}\n"
                      f"**Buttons:** {len(buttons)}\n"
                      f"**Created:** {panel['created_at'].strftime('%Y-%m-%d')}",
                inline=True
            )

        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ==========================================
    # TICKET MANAGEMENT COMMANDS
    # ==========================================

    @app_commands.command(
        name="tickets",
        description="View open tickets in this server"
    )
    @app_commands.guild_only()
    async def list_tickets(self, interaction: discord.Interaction):
        """List all open tickets."""

        if not await require_admin(interaction):
            return

        try:
            guild_id = interaction.guild_id
            open_tickets = TicketQueries.get_open_tickets(guild_id)
            stats = TicketQueries.get_ticket_stats(guild_id)

            if not open_tickets:
                await interaction.response.send_message(
                    "No open tickets at the moment.",
                    ephemeral=True
                )
                return

            embed = discord.Embed(
                title="Open Tickets",
                description=f"Open: **{stats['open_count']}** | "
                           f"Claimed: **{stats['claimed_count']}** | "
                           f"Total: **{stats['total']}**",
                color=discord.Color.blue()
            )

            for ticket in open_tickets[:15]:
                status_icon = "🔵" if ticket['status'] == 'open' else "🟡"
                claimed_text = f" (Claimed by {ticket['claimed_by_name']})" if ticket['claimed_by_name'] else ""

                embed.add_field(
                    name=f"{status_icon} Ticket #{ticket['ticket_number']}",
                    value=f"**User:** {ticket['username']}\n"
                          f"**Opened:** {ticket['opened_at'].strftime('%Y-%m-%d %H:%M')}{claimed_text}\n"
                          f"**Channel:** <#{ticket['channel_id']}>",
                    inline=True
                )

            await interaction.response.send_message(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Error listing tickets: {e}", exc_info=True)
            await interaction.response.send_message(
                "An error occurred while retrieving tickets.",
                ephemeral=True
            )

    @app_commands.command(
        name="close",
        description="Close the current ticket"
    )
    @app_commands.guild_only()
    async def close_ticket(self, interaction: discord.Interaction):
        """Close a ticket - opens modal for reason."""

        ticket = TicketQueries.get_ticket_by_channel(interaction.channel_id)

        if not ticket:
            await interaction.response.send_message(
                "This command can only be used in a ticket channel.",
                ephemeral=True
            )
            return

        if ticket['status'] == 'closed':
            await interaction.response.send_message(
                "This ticket is already closed.",
                ephemeral=True
            )
            return

        modal = CloseTicketModal(ticket['id'])
        await interaction.response.send_modal(modal)

    @app_commands.command(
        name="claim",
        description="Claim the current ticket"
    )
    @app_commands.guild_only()
    async def claim_ticket(self, interaction: discord.Interaction):
        """Claim a ticket."""

        if not await require_admin(interaction):
            return

        try:
            ticket = TicketQueries.get_ticket_by_channel(interaction.channel_id)

            if not ticket:
                await interaction.response.send_message(
                    "This command can only be used in a ticket channel.",
                    ephemeral=True
                )
                return

            if ticket['status'] == 'claimed':
                await interaction.response.send_message(
                    f"This ticket is already claimed by {ticket['claimed_by_name']}.",
                    ephemeral=True
                )
                return

            if ticket['status'] == 'closed':
                await interaction.response.send_message(
                    "This ticket is closed.",
                    ephemeral=True
                )
                return

            TicketQueries.claim_ticket(
                ticket_id=ticket['id'],
                claimed_by_id=interaction.user.id,
                claimed_by_name=str(interaction.user)
            )

            embed = discord.Embed(
                title="Ticket Claimed",
                description=f"{interaction.user.mention} has claimed this ticket and will be assisting you.",
                color=discord.Color.green()
            )

            await interaction.response.send_message(embed=embed)

        except Exception as e:
            logger.error(f"Error claiming ticket: {e}", exc_info=True)
            await interaction.response.send_message(
                "An error occurred while claiming the ticket.",
                ephemeral=True
            )

    @app_commands.command(
        name="adduser",
        description="Add a user to the current ticket"
    )
    @app_commands.guild_only()
    @app_commands.describe(
        user="The user to add to the ticket"
    )
    async def add_user_to_ticket(self, interaction: discord.Interaction, user: discord.Member):
        """Add a user to a ticket."""

        if not await require_admin(interaction):
            return

        try:
            ticket = TicketQueries.get_ticket_by_channel(interaction.channel_id)

            if not ticket:
                await interaction.response.send_message(
                    "This command can only be used in a ticket channel.",
                    ephemeral=True
                )
                return

            TicketQueries.add_participant(
                ticket_id=ticket['id'],
                user_id=user.id,
                username=str(user),
                added_by_id=interaction.user.id
            )

            await interaction.channel.set_permissions(
                user,
                read_messages=True,
                send_messages=True,
                reason=f"Added to ticket by {interaction.user}"
            )

            await interaction.response.send_message(
                f"{user.mention} has been added to this ticket."
            )

        except Exception as e:
            logger.error(f"Error adding user to ticket: {e}", exc_info=True)
            await interaction.response.send_message(
                "An error occurred while adding the user.",
                ephemeral=True
            )

    @app_commands.command(
        name="removeuser",
        description="Remove a user from the current ticket"
    )
    @app_commands.guild_only()
    @app_commands.describe(
        user="The user to remove from the ticket"
    )
    async def remove_user_from_ticket(self, interaction: discord.Interaction, user: discord.Member):
        """Remove a user from a ticket."""

        if not await require_admin(interaction):
            return

        try:
            ticket = TicketQueries.get_ticket_by_channel(interaction.channel_id)

            if not ticket:
                await interaction.response.send_message(
                    "This command can only be used in a ticket channel.",
                    ephemeral=True
                )
                return

            if user.id == ticket['user_id']:
                await interaction.response.send_message(
                    "You cannot remove the ticket creator.",
                    ephemeral=True
                )
                return

            TicketQueries.remove_participant(ticket['id'], user.id)

            await interaction.channel.set_permissions(
                user,
                overwrite=None,
                reason=f"Removed from ticket by {interaction.user}"
            )

            await interaction.response.send_message(
                f"{user.mention} has been removed from this ticket."
            )

        except Exception as e:
            logger.error(f"Error removing user from ticket: {e}", exc_info=True)
            await interaction.response.send_message(
                "An error occurred while removing the user.",
                ephemeral=True
            )

    # ==========================================
    # TRANSCRIPT GENERATION
    # ==========================================

    async def _generate_transcript(self, ticket: dict, guild: discord.Guild,
                                    closed_by: discord.User, reason: str = None) -> tuple:
        """
        Generate transcript embed and downloadable file for a closed ticket.
        Returns tuple of (embed, file) where file is a discord.File or None.
        """

        # Generate summary embed
        embed = discord.Embed(
            title="Ticket Closed",
            color=discord.Color.blue(),
            timestamp=datetime.now()
        )

        embed.add_field(name="Ticket ID", value=str(ticket['ticket_number']), inline=True)

        opener = guild.get_member(ticket['user_id'])
        opener_text = opener.mention if opener else ticket['username']
        embed.add_field(name="Opened By", value=opener_text, inline=True)

        embed.add_field(name="Closed By", value=closed_by.mention, inline=True)

        embed.add_field(
            name="Open Time",
            value=ticket['opened_at'].strftime("%d %B %Y %H:%M"),
            inline=True
        )

        if ticket['claimed_by_name']:
            embed.add_field(name="Claimed By", value=ticket['claimed_by_name'], inline=True)
        else:
            embed.add_field(name="Claimed By", value="Not claimed", inline=True)

        embed.add_field(
            name="Reason",
            value=reason or "No reason specified",
            inline=False
        )

        # Show form responses if any
        if ticket.get('form_responses'):
            responses = ticket['form_responses']
            if isinstance(responses, str):
                responses = json.loads(responses)
            for field_name, value in responses.items():
                if value:
                    embed.add_field(
                        name=f"📝 {field_name}",
                        value=value[:200] + "..." if len(str(value)) > 200 else value,
                        inline=False
                    )

        # Show appeal reference if any
        if ticket.get('appeal_reference_id'):
            embed.add_field(
                name="Appeal Reference",
                value=f"`{ticket['appeal_reference_id']}`",
                inline=True
            )

        messages = TicketQueries.get_ticket_messages(ticket['id'])
        if messages:
            embed.add_field(name="Messages", value=str(len(messages)), inline=True)

        embed.set_footer(text=f"{guild.name} • Ticket System")

        # Generate downloadable transcript file
        transcript_file = await self._generate_transcript_file(ticket, guild, closed_by, reason, messages)

        return embed, transcript_file

    async def _generate_transcript_file(self, ticket: dict, guild: discord.Guild,
                                         closed_by: discord.User, reason: str,
                                         messages: list) -> discord.File:
        """Generate a downloadable text transcript file."""
        import io

        lines = []
        lines.append("=" * 60)
        lines.append(f"TICKET TRANSCRIPT - #{ticket['ticket_number']}")
        lines.append("=" * 60)
        lines.append("")
        lines.append(f"Server: {guild.name}")
        lines.append(f"Ticket ID: #{ticket['ticket_number']}")
        lines.append(f"Opened By: {ticket['username']} (ID: {ticket['user_id']})")
        lines.append(f"Opened At: {ticket['opened_at'].strftime('%Y-%m-%d %H:%M:%S UTC')}")

        if ticket.get('claimed_by_name'):
            lines.append(f"Claimed By: {ticket['claimed_by_name']}")

        lines.append(f"Closed By: {closed_by} (ID: {closed_by.id})")
        lines.append(f"Closed At: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}")

        if reason:
            lines.append(f"Close Reason: {reason}")

        # Form responses
        if ticket.get('form_responses'):
            responses = ticket['form_responses']
            if isinstance(responses, str):
                responses = json.loads(responses)
            lines.append("")
            lines.append("-" * 40)
            lines.append("FORM RESPONSES")
            lines.append("-" * 40)
            for field_name, value in responses.items():
                if value:
                    lines.append(f"{field_name}: {value}")

        # Appeal reference
        if ticket.get('appeal_reference_id'):
            lines.append(f"Appeal Reference: {ticket['appeal_reference_id']}")

        # Messages
        lines.append("")
        lines.append("-" * 40)
        lines.append(f"MESSAGES ({len(messages)} total)")
        lines.append("-" * 40)
        lines.append("")

        for msg in messages:
            timestamp = msg['created_at'].strftime('%Y-%m-%d %H:%M:%S')
            username = msg['username']
            content = msg['content'] or "[No text content]"

            lines.append(f"[{timestamp}] {username}:")
            lines.append(f"  {content}")

            # Attachments
            if msg.get('attachments'):
                attachments = msg['attachments']
                if isinstance(attachments, str):
                    attachments = json.loads(attachments)
                for att in attachments:
                    lines.append(f"  📎 Attachment: {att.get('filename', 'unknown')} - {att.get('url', 'N/A')}")

            if msg.get('deleted'):
                lines.append("  [MESSAGE DELETED]")

            lines.append("")

        lines.append("=" * 60)
        lines.append("END OF TRANSCRIPT")
        lines.append("=" * 60)

        # Create file
        transcript_content = "\n".join(lines)
        file_bytes = io.BytesIO(transcript_content.encode('utf-8'))
        filename = f"transcript-{ticket['ticket_number']}-{guild.id}.txt"

        return discord.File(file_bytes, filename=filename)

    # ==========================================
    # MESSAGE LOGGING FOR TRANSCRIPTS
    # ==========================================

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Log messages in ticket channels."""

        if message.author.bot:
            return

        if not message.guild:
            return

        ticket = TicketQueries.get_ticket_by_channel(message.channel.id)
        if not ticket or ticket['status'] == 'closed':
            return

        attachments = [
            {'url': a.url, 'filename': a.filename}
            for a in message.attachments
        ]

        TicketQueries.add_message(
            ticket_id=ticket['id'],
            message_id=message.id,
            user_id=message.author.id,
            username=str(message.author),
            content=message.content,
            attachments=attachments if attachments else None
        )

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        """Mark deleted messages in tickets."""
        TicketQueries.mark_message_deleted(message.id)

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        """Update edited messages in tickets."""
        if before.content != after.content:
            TicketQueries.update_message(after.id, after.content)


# ==========================================
# MODALS
# ==========================================

class CreatePanelModal(discord.ui.Modal, title="Create Ticket Panel"):
    """Modal for creating a ticket panel with formatted description."""

    panel_title = discord.ui.TextInput(
        label="Panel Title",
        placeholder="Support Tickets",
        default="Support Tickets",
        max_length=255,
        required=True
    )

    description = discord.ui.TextInput(
        label="Description (leave empty for default)",
        placeholder="Custom description or leave empty to use default...\n**Bold** *italic* supported",
        style=discord.TextStyle.paragraph,
        max_length=2000,
        required=False
    )

    welcome_message = discord.ui.TextInput(
        label="Welcome Message (sent in new tickets)",
        placeholder="Thank you for opening a ticket! A staff member will assist you shortly.",
        style=discord.TextStyle.paragraph,
        max_length=1000,
        required=False
    )

    def __init__(self, channel: discord.TextChannel, category: discord.CategoryChannel = None,
                 transcript_channel: discord.TextChannel = None, support_role: discord.Role = None):
        super().__init__()
        self.channel = channel
        self.category = category
        self.transcript_channel = transcript_channel
        self.support_role = support_role

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        try:
            # Use default description if none provided
            panel_description = self.description.value.strip() if self.description.value else DEFAULT_PANEL_DESCRIPTION

            panel = TicketQueries.create_panel(
                guild_id=interaction.guild_id,
                channel_id=self.channel.id,
                title=self.panel_title.value,
                description=panel_description,
                ticket_category_id=self.category.id if self.category else None,
                transcript_channel_id=self.transcript_channel.id if self.transcript_channel else None,
                support_role_id=self.support_role.id if self.support_role else None,
                welcome_message=self.welcome_message.value or None
            )

            # Create default "General Support" button (green)
            TicketQueries.create_button_type(
                panel_id=panel['id'],
                button_label="General Support",
                button_emoji="💬",
                button_style=3,  # Green
                form_title="Open Support Ticket",
                form_fields=[
                    {
                        "name": "topic",
                        "label": "What do you need help with?",
                        "placeholder": "Brief summary of your issue",
                        "required": True,
                        "style": "short"
                    },
                    {
                        "name": "details",
                        "label": "Please provide more details",
                        "placeholder": "Describe your issue or question in detail...",
                        "required": True,
                        "style": "long"
                    }
                ],
                welcome_template=self.welcome_message.value or "**General Support**\n\nHow can we help you today?\nA staff member will assist you shortly."
            )

            # Create the embed
            embed = discord.Embed(
                title=self.panel_title.value,
                description=panel_description,
                color=discord.Color.blue()
            )
            embed.set_footer(text=f"{interaction.guild.name} • Support System")

            # Create the view
            view = TicketPanelView(panel_id=panel['id'])

            # Send the panel
            message = await self.channel.send(embed=embed, view=view)
            TicketQueries.update_panel_message(panel['id'], message.id)

            # Log
            AuditQueries.log(
                guild_id=interaction.guild_id,
                action_type='ticket_panel_created',
                performed_by_id=interaction.user.id,
                performed_by_name=str(interaction.user),
                details={
                    'panel_id': panel['id'],
                    'channel_id': self.channel.id,
                    'title': self.panel_title.value
                }
            )

            await interaction.followup.send(
                f"Ticket panel created in {self.channel.mention}!\n"
                f"**Panel ID:** `{panel['id']}`\n\n"
                f"Use `/addbutton {panel['id']} <type>` to add more buttons (appeal, report, etc.)\n"
                f"Use `/refreshpanel {panel['id']}` after adding buttons to update the panel.",
                ephemeral=True
            )

        except Exception as e:
            logger.error(f"Error creating panel: {e}", exc_info=True)
            await interaction.followup.send(
                "An error occurred while creating the panel.",
                ephemeral=True
            )


class AddButtonModal(discord.ui.Modal, title="Add Button to Panel"):
    """Modal for adding a button to a panel."""

    button_label = discord.ui.TextInput(
        label="Button Label",
        placeholder="Open Ticket",
        max_length=80,
        required=True
    )

    button_emoji = discord.ui.TextInput(
        label="Button Emoji (optional)",
        placeholder="🎫",
        max_length=50,
        required=False
    )

    welcome_template = discord.ui.TextInput(
        label="Welcome Message for this ticket type",
        placeholder="Thank you for opening a ticket...",
        style=discord.TextStyle.paragraph,
        max_length=1000,
        required=False
    )

    def __init__(self, panel_id: int, button_type: str, color_override: int = None):
        super().__init__()
        self.panel_id = panel_id
        self.button_type = button_type
        self.color_override = color_override  # User-specified color, or None for type default

        # Pre-fill based on type
        if button_type == "appeal":
            self.button_label.default = "Strike/Ban Appeal"
            self.button_emoji.default = "⚖️"
            self.welcome_template.default = (
                "**Strike or Ban Appeal**\n\n"
                "Please provide the information requested below.\n"
                "A staff member will review your case shortly."
            )
        elif button_type == "report":
            self.button_label.default = "Report Rule Violation"
            self.button_emoji.default = "🚨"
            self.welcome_template.default = (
                "**Rule Violation Report**\n\n"
                "Thank you for helping keep our community safe.\n"
                "Please provide details about the incident."
            )
        elif button_type == "support":
            self.button_label.default = "General Support"
            self.button_emoji.default = "💬"
            self.welcome_template.default = (
                "**General Support**\n\n"
                "How can we help you today?\n"
                "Please describe your issue or question."
            )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        try:
            # Define form fields and default style based on button type
            form_fields = None
            default_style = 1  # Primary (blue) as fallback

            if self.button_type == "appeal":
                default_style = 4  # Danger (red)
                form_fields = [
                    {
                        "name": "reference_id",
                        "label": "Reference ID (from DM notification)",
                        "placeholder": "e.g., ABC12345",
                        "required": False,
                        "style": "short"
                    },
                    {
                        "name": "player_id",
                        "label": "Your Alderon Player ID",
                        "placeholder": "XXX-XXX-XXX",
                        "required": True,
                        "style": "short"
                    },
                    {
                        "name": "appeal_reason",
                        "label": "Why should this be reconsidered?",
                        "placeholder": "Explain why you believe this action was unfair or provide any evidence...",
                        "required": True,
                        "style": "long"
                    }
                ]
            elif self.button_type == "report":
                default_style = 4  # Danger (red)
                form_fields = [
                    {
                        "name": "reported_player",
                        "label": "Player Name/ID being reported",
                        "placeholder": "Name or Alderon ID of the rule breaker",
                        "required": True,
                        "style": "short"
                    },
                    {
                        "name": "rule_broken",
                        "label": "What rule was broken?",
                        "placeholder": "e.g., KOS, Combat logging, Harassment",
                        "required": True,
                        "style": "short"
                    },
                    {
                        "name": "description",
                        "label": "Describe what happened",
                        "placeholder": "Provide details about the incident including time, location, etc.",
                        "required": True,
                        "style": "long"
                    },
                    {
                        "name": "evidence",
                        "label": "Evidence (screenshots/video links)",
                        "placeholder": "Links to evidence (you can also attach files after ticket opens)",
                        "required": False,
                        "style": "long"
                    }
                ]
            elif self.button_type == "support":
                default_style = 3  # Success (green)
                form_fields = [
                    {
                        "name": "topic",
                        "label": "What do you need help with?",
                        "placeholder": "Brief summary of your issue",
                        "required": True,
                        "style": "short"
                    },
                    {
                        "name": "details",
                        "label": "Please provide more details",
                        "placeholder": "Describe your issue or question in detail...",
                        "required": True,
                        "style": "long"
                    }
                ]

            # Use color override if provided, otherwise use type default
            button_style = self.color_override if self.color_override is not None else default_style

            # Create the button
            button = TicketQueries.create_button_type(
                panel_id=self.panel_id,
                button_label=self.button_label.value,
                button_emoji=self.button_emoji.value or None,
                button_style=button_style,
                form_title=f"Open {self.button_label.value}",
                form_fields=form_fields,
                welcome_template=self.welcome_template.value or None
            )

            await interaction.followup.send(
                f"Button **{self.button_label.value}** added to panel #{self.panel_id}!\n\n"
                f"Use `/refreshpanel {self.panel_id}` to update the panel message with the new button.",
                ephemeral=True
            )

        except Exception as e:
            logger.error(f"Error adding button: {e}", exc_info=True)
            await interaction.followup.send(
                "An error occurred while adding the button.",
                ephemeral=True
            )


class CloseTicketModal(discord.ui.Modal, title="Close Ticket"):
    """Modal for entering close reason."""

    reason = discord.ui.TextInput(
        label="Reason for closing",
        placeholder="Enter the reason for closing this ticket...",
        style=discord.TextStyle.paragraph,
        required=False,
        max_length=500
    )

    def __init__(self, ticket_id: int):
        super().__init__()
        self.ticket_id = ticket_id

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()

        try:
            ticket = TicketQueries.get_ticket_with_details(self.ticket_id)

            if not ticket or ticket['status'] == 'closed':
                await interaction.followup.send(
                    "This ticket is already closed.",
                    ephemeral=True
                )
                return

            panel = TicketQueries.get_panel(ticket['panel_id']) if ticket['panel_id'] else None

            # Get the cog to generate transcript (returns embed and file)
            cog = interaction.client.get_cog('TicketCommands')
            transcript_embed, transcript_file = await cog._generate_transcript(
                ticket, interaction.guild, interaction.user, self.reason.value
            )

            # Send transcript to transcript channel (with file)
            transcript_message = None
            if panel and panel['transcript_channel_id']:
                transcript_channel = interaction.guild.get_channel(panel['transcript_channel_id'])
                if transcript_channel:
                    transcript_message = await transcript_channel.send(
                        embed=transcript_embed,
                        file=transcript_file
                    )
                    TicketQueries.set_transcript(ticket['id'], transcript_message.id)

            TicketQueries.close_ticket(
                ticket_id=ticket['id'],
                closed_by_id=interaction.user.id,
                closed_by_name=str(interaction.user),
                reason=self.reason.value or None
            )

            AuditQueries.log(
                guild_id=interaction.guild_id,
                action_type='ticket_closed',
                performed_by_id=interaction.user.id,
                performed_by_name=str(interaction.user),
                target_user_id=ticket['user_id'],
                details={
                    'ticket_id': ticket['id'],
                    'ticket_number': ticket['ticket_number'],
                    'reason': self.reason.value
                }
            )

            close_embed = discord.Embed(
                title="Ticket Closed",
                description=f"This ticket has been closed by {interaction.user.mention}",
                color=discord.Color.red(),
                timestamp=datetime.now()
            )
            if self.reason.value:
                close_embed.add_field(name="Reason", value=self.reason.value, inline=False)

            await interaction.followup.send(embed=close_embed)

            # DM the creator with transcript file
            try:
                creator = interaction.guild.get_member(ticket['user_id'])
                if creator:
                    dm_embed = discord.Embed(
                        title="Ticket Closed",
                        description=f"Your ticket in **{interaction.guild.name}** has been closed.\n\n"
                                    f"A transcript of your conversation is attached below.",
                        color=discord.Color.blue(),
                        timestamp=datetime.now()
                    )
                    dm_embed.add_field(name="Ticket ID", value=str(ticket['ticket_number']), inline=True)
                    dm_embed.add_field(name="Closed By", value=str(interaction.user), inline=True)
                    if self.reason.value:
                        dm_embed.add_field(name="Reason", value=self.reason.value, inline=False)

                    dm_embed.set_footer(text=f"{interaction.guild.name} • Support System")

                    # Generate a fresh transcript file for the DM (file can only be sent once)
                    messages = TicketQueries.get_ticket_messages(ticket['id'])
                    dm_transcript_file = await cog._generate_transcript_file(
                        ticket, interaction.guild, interaction.user, self.reason.value, messages
                    )
                    await creator.send(embed=dm_embed, file=dm_transcript_file)
            except discord.Forbidden:
                pass  # User has DMs disabled

            # Delete channel
            await interaction.channel.send("This channel will be deleted in 5 seconds...")
            import asyncio
            await asyncio.sleep(5)
            await interaction.channel.delete(reason=f"Ticket closed by {interaction.user}")

        except Exception as e:
            logger.error(f"Error in close modal: {e}", exc_info=True)


class TicketFormModal(discord.ui.Modal):
    """Dynamic modal for pre-ticket forms."""

    def __init__(self, button_type: dict, panel: dict):
        super().__init__(title=button_type.get('form_title', 'Open Ticket')[:45])
        self.button_type = button_type
        self.panel = panel
        self.form_fields = button_type.get('form_fields') or []

        # Add fields dynamically (max 5 for Discord modals)
        for i, field in enumerate(self.form_fields[:5]):
            text_input = discord.ui.TextInput(
                label=field.get('label', f'Field {i+1}')[:45],
                placeholder=field.get('placeholder', '')[:100],
                required=field.get('required', False),
                style=discord.TextStyle.paragraph if field.get('style') == 'long' else discord.TextStyle.short,
                max_length=1000 if field.get('style') == 'long' else 100
            )
            self.add_item(text_input)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        try:
            guild_id = interaction.guild_id

            # Check ticket limits
            # 1. Max 3 tickets per user total
            open_ticket_count = TicketQueries.get_user_open_ticket_count(guild_id, interaction.user.id)
            if open_ticket_count >= 3:
                existing = TicketQueries.get_user_open_tickets(guild_id, interaction.user.id)
                ticket_links = ", ".join([f"<#{t['channel_id']}>" for t in existing[:3]])
                await interaction.followup.send(
                    f"You have reached the maximum of **3** open tickets.\n"
                    f"Your open tickets: {ticket_links}\n\n"
                    "Please close one of your existing tickets before opening a new one.",
                    ephemeral=True
                )
                return

            # 2. Max 1 ticket per button type
            existing_same_type = TicketQueries.get_user_open_ticket_by_button_type(
                guild_id, interaction.user.id, self.button_type['id']
            )
            if existing_same_type:
                await interaction.followup.send(
                    f"You already have an open **{self.button_type['button_label']}** ticket: "
                    f"<#{existing_same_type['channel_id']}>\n\n"
                    "You can only have one ticket of each type open at a time.",
                    ephemeral=True
                )
                return

            # Collect form responses
            form_responses = {}
            for i, child in enumerate(self.children):
                if isinstance(child, discord.ui.TextInput):
                    field_name = self.form_fields[i].get('name', f'field_{i}') if i < len(self.form_fields) else f'field_{i}'
                    form_responses[field_name] = child.value

            # Check for appeal reference ID
            appeal_ref = form_responses.get('reference_id', '').strip().upper()
            player_history = None
            if appeal_ref:
                player_history = StrikeQueries.get_player_history_by_reference(appeal_ref)

            # Create ticket
            ticket = TicketQueries.create_ticket_with_form(
                guild_id=guild_id,
                user_id=interaction.user.id,
                username=str(interaction.user),
                panel_id=self.panel['id'],
                button_type_id=self.button_type['id'],
                form_responses=form_responses,
                appeal_reference_id=appeal_ref if appeal_ref else None
            )

            # Create channel
            category = None
            if self.panel['ticket_category_id']:
                category = interaction.guild.get_channel(self.panel['ticket_category_id'])

            overwrites = {
                interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
                interaction.user: discord.PermissionOverwrite(
                    read_messages=True,
                    send_messages=True,
                    attach_files=True,
                    embed_links=True
                ),
                interaction.guild.me: discord.PermissionOverwrite(
                    read_messages=True,
                    send_messages=True,
                    manage_channels=True,
                    manage_messages=True
                )
            }

            if self.panel['support_role_id']:
                support_role = interaction.guild.get_role(self.panel['support_role_id'])
                if support_role:
                    overwrites[support_role] = discord.PermissionOverwrite(
                        read_messages=True,
                        send_messages=True,
                        manage_messages=True
                    )

            # Generate channel name
            channel_pattern = self.button_type.get('channel_name_pattern', 'ticket-{number}')
            channel_name = channel_pattern.format(
                number=f"{ticket['ticket_number']:04d}",
                user=interaction.user.name[:10]
            )

            channel = await interaction.guild.create_text_channel(
                name=channel_name,
                category=category,
                overwrites=overwrites,
                topic=f"Ticket #{ticket['ticket_number']} | {self.button_type['button_label']} | User: {interaction.user}"
            )

            TicketQueries.update_ticket_channel(ticket['id'], channel.id)

            # Build welcome embed
            welcome_embed = discord.Embed(
                title=f"Ticket #{ticket['ticket_number']} - {self.button_type['button_label']}",
                description=self.button_type.get('welcome_template') or "A staff member will assist you shortly.",
                color=discord.Color.green(),
                timestamp=datetime.now()
            )
            welcome_embed.add_field(name="Created By", value=interaction.user.mention, inline=True)

            # Add form responses to embed
            for field in self.form_fields[:5]:
                field_name = field.get('name', '')
                field_label = field.get('label', field_name)
                value = form_responses.get(field_name, '')
                if value:
                    welcome_embed.add_field(
                        name=f"📝 {field_label}",
                        value=value[:1024],
                        inline=False
                    )

            # If appeal with valid reference, show player history
            if player_history:
                history_text = (
                    f"**Player:** {player_history['player_name']}\n"
                    f"**Alderon ID:** `{player_history['in_game_id']}`\n"
                    f"**Active Strikes:** {player_history['active_strike_count']}\n"
                    f"**Total Strikes:** {player_history['total_strike_count']}\n"
                    f"**Banned:** {'Yes' if player_history['is_banned'] else 'No'}"
                )

                if player_history['referenced_strike']:
                    strike = player_history['referenced_strike']
                    history_text += f"\n\n**Referenced Strike #{strike['strike_number']}:**\n"
                    history_text += f"Reason: {strike['reason'][:200]}\n"
                    history_text += f"Date: {strike['created_at'].strftime('%Y-%m-%d')}"

                if player_history['referenced_ban']:
                    ban = player_history['referenced_ban']
                    history_text += f"\n\n**Referenced Ban:**\n"
                    history_text += f"Reason: {ban['reason'][:200]}\n"
                    history_text += f"Date: {ban['banned_at'].strftime('%Y-%m-%d')}"

                welcome_embed.add_field(
                    name="📋 Moderation History (from reference)",
                    value=history_text,
                    inline=False
                )

            welcome_embed.set_footer(text=f"{interaction.guild.name} • Support System")

            # Control buttons
            control_view = TicketControlView(ticket['id'])

            await channel.send(
                content=interaction.user.mention,
                embed=welcome_embed,
                view=control_view
            )

            # Ping support role
            if self.panel['support_role_id']:
                support_role = interaction.guild.get_role(self.panel['support_role_id'])
                if support_role:
                    await channel.send(f"{support_role.mention} - New ticket opened!", delete_after=5)

            AuditQueries.log(
                guild_id=guild_id,
                action_type='ticket_opened',
                performed_by_id=interaction.user.id,
                performed_by_name=str(interaction.user),
                details={
                    'ticket_id': ticket['id'],
                    'ticket_number': ticket['ticket_number'],
                    'button_type': self.button_type['button_label'],
                    'has_reference': bool(appeal_ref)
                }
            )

            await interaction.followup.send(
                f"Your ticket has been created: {channel.mention}",
                ephemeral=True
            )

        except Exception as e:
            logger.error(f"Error creating ticket from form: {e}", exc_info=True)
            await interaction.followup.send(
                "An error occurred while creating your ticket. Please try again.",
                ephemeral=True
            )


# ==========================================
# VIEWS
# ==========================================

class TicketPanelView(discord.ui.View):
    """Persistent view for ticket panel with multiple buttons."""

    def __init__(self, panel_id: int):
        super().__init__(timeout=None)
        self.panel_id = panel_id

        # Load buttons from database
        buttons = TicketQueries.get_panel_buttons(panel_id)

        for button_data in buttons:
            style = BUTTON_STYLES.get(button_data.get('button_style', 1), discord.ButtonStyle.primary)

            button = discord.ui.Button(
                label=button_data['button_label'],
                emoji=button_data.get('button_emoji'),
                style=style,
                custom_id=f"ticket_btn:{panel_id}:{button_data['id']}"
            )
            button.callback = self._make_callback(button_data['id'])
            self.add_item(button)

    def _make_callback(self, button_type_id: int):
        async def callback(interaction: discord.Interaction):
            button_type = TicketQueries.get_button_type(button_type_id)
            panel = TicketQueries.get_panel(self.panel_id)

            if not button_type or not panel:
                await interaction.response.send_message(
                    "This button is no longer valid.",
                    ephemeral=True
                )
                return

            guild_id = panel['guild_id']

            # Check ticket limits
            # 1. Max 3 tickets per user total
            open_ticket_count = TicketQueries.get_user_open_ticket_count(guild_id, interaction.user.id)
            if open_ticket_count >= 3:
                existing = TicketQueries.get_user_open_tickets(guild_id, interaction.user.id)
                ticket_links = ", ".join([f"<#{t['channel_id']}>" for t in existing[:3]])
                await interaction.response.send_message(
                    f"You have reached the maximum of **3** open tickets.\n"
                    f"Your open tickets: {ticket_links}\n\n"
                    "Please close one of your existing tickets before opening a new one.",
                    ephemeral=True
                )
                return

            # 2. Max 1 ticket per button type
            existing_same_type = TicketQueries.get_user_open_ticket_by_button_type(
                guild_id, interaction.user.id, button_type_id
            )
            if existing_same_type:
                await interaction.response.send_message(
                    f"You already have an open **{button_type['button_label']}** ticket: "
                    f"<#{existing_same_type['channel_id']}>\n\n"
                    "You can only have one ticket of each type open at a time.",
                    ephemeral=True
                )
                return

            # If button has form fields, show modal
            if button_type.get('form_fields'):
                modal = TicketFormModal(button_type, panel)
                await interaction.response.send_modal(modal)
            else:
                # Create ticket directly
                await self._create_simple_ticket(interaction, button_type, panel)

        return callback

    async def _create_simple_ticket(self, interaction: discord.Interaction,
                                     button_type: dict, panel: dict):
        """Create a ticket without a form."""
        await interaction.response.defer(ephemeral=True)

        try:
            guild_id = interaction.guild_id

            ticket = TicketQueries.create_ticket_with_form(
                guild_id=guild_id,
                user_id=interaction.user.id,
                username=str(interaction.user),
                panel_id=panel['id'],
                button_type_id=button_type['id']
            )

            category = None
            if panel['ticket_category_id']:
                category = interaction.guild.get_channel(panel['ticket_category_id'])

            overwrites = {
                interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
                interaction.user: discord.PermissionOverwrite(
                    read_messages=True,
                    send_messages=True,
                    attach_files=True,
                    embed_links=True
                ),
                interaction.guild.me: discord.PermissionOverwrite(
                    read_messages=True,
                    send_messages=True,
                    manage_channels=True,
                    manage_messages=True
                )
            }

            if panel['support_role_id']:
                support_role = interaction.guild.get_role(panel['support_role_id'])
                if support_role:
                    overwrites[support_role] = discord.PermissionOverwrite(
                        read_messages=True,
                        send_messages=True,
                        manage_messages=True
                    )

            channel = await interaction.guild.create_text_channel(
                name=f"ticket-{ticket['ticket_number']:04d}",
                category=category,
                overwrites=overwrites,
                topic=f"Ticket #{ticket['ticket_number']} | User: {interaction.user}"
            )

            TicketQueries.update_ticket_channel(ticket['id'], channel.id)

            welcome_embed = discord.Embed(
                title=f"Ticket #{ticket['ticket_number']}",
                description=button_type.get('welcome_template') or panel.get('welcome_message') or "A staff member will assist you shortly.",
                color=discord.Color.green(),
                timestamp=datetime.now()
            )
            welcome_embed.add_field(name="Created By", value=interaction.user.mention, inline=True)
            welcome_embed.set_footer(text=f"{interaction.guild.name} • Support System")

            control_view = TicketControlView(ticket['id'])

            await channel.send(
                content=interaction.user.mention,
                embed=welcome_embed,
                view=control_view
            )

            await interaction.followup.send(
                f"Your ticket has been created: {channel.mention}",
                ephemeral=True
            )

        except Exception as e:
            logger.error(f"Error creating simple ticket: {e}", exc_info=True)
            await interaction.followup.send(
                "An error occurred while creating your ticket.",
                ephemeral=True
            )


class TicketControlView(discord.ui.View):
    """Control buttons shown in ticket channels."""

    def __init__(self, ticket_id: int):
        super().__init__(timeout=None)
        self.ticket_id = ticket_id

    @discord.ui.button(label="Close Ticket", emoji="🔒", style=discord.ButtonStyle.danger,
                       custom_id="ticket_close")
    async def close_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Close ticket button."""
        modal = CloseTicketModal(self.ticket_id)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Claim", emoji="🙋", style=discord.ButtonStyle.secondary,
                       custom_id="ticket_claim")
    async def claim_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Claim ticket button."""

        if not has_admin_permission(interaction.user, interaction.guild_id):
            await interaction.response.send_message(
                "You don't have permission to claim tickets.",
                ephemeral=True
            )
            return

        ticket = TicketQueries.get_ticket(self.ticket_id)

        if ticket['status'] == 'claimed':
            await interaction.response.send_message(
                f"This ticket is already claimed by {ticket['claimed_by_name']}.",
                ephemeral=True
            )
            return

        TicketQueries.claim_ticket(
            ticket_id=self.ticket_id,
            claimed_by_id=interaction.user.id,
            claimed_by_name=str(interaction.user)
        )

        embed = discord.Embed(
            title="Ticket Claimed",
            description=f"{interaction.user.mention} has claimed this ticket.",
            color=discord.Color.green()
        )
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
    """Load the TicketCommands cog."""
    cog = TicketCommands(bot)
    await bot.add_cog(cog)

    # Register persistent views for existing panels
    try:
        from database.connection import get_cursor
        with get_cursor() as cursor:
            cursor.execute("SELECT id FROM ticket_panels")
            panels = cursor.fetchall()

        for panel in panels:
            bot.add_view(TicketPanelView(panel['id']))

        logger.info(f"Registered {len(panels)} ticket panel views")
    except Exception as e:
        logger.warning(f"Could not load ticket panels: {e}")
