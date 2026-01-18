# cogs/admin/tickets.py
"""
Ticket System Commands

Support ticket system with transcripts for moderation appeals and general support.
"""

import discord
from discord import app_commands
from discord.ext import commands
from database.queries import TicketQueries, GuildQueries, AuditQueries
from services.permissions import require_admin
from datetime import datetime
import logging
import io

logger = logging.getLogger(__name__)


class TicketCommands(commands.Cog):
    """Commands for the ticket system."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ==========================================
    # TICKET PANEL COMMANDS
    # ==========================================

    @app_commands.command(
        name="ticketpanel",
        description="Create a ticket panel for users to open support tickets"
    )
    @app_commands.guild_only()
    @app_commands.describe(
        channel="Channel to post the panel in",
        title="Title of the ticket panel",
        description="Description shown on the panel",
        button_label="Text on the button",
        category="Category where ticket channels are created",
        transcript_channel="Channel where transcripts are posted when tickets close",
        support_role="Role that can see and manage tickets"
    )
    async def create_ticket_panel(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        title: str = "Support Tickets",
        description: str = "Click the button below to open a support ticket.",
        button_label: str = "Open Ticket",
        category: discord.CategoryChannel = None,
        transcript_channel: discord.TextChannel = None,
        support_role: discord.Role = None
    ):
        """Create a ticket panel."""

        if not await require_admin(interaction, min_level=2):
            return

        await interaction.response.defer(ephemeral=True)

        try:
            guild_id = interaction.guild_id
            GuildQueries.get_or_create(guild_id, interaction.guild.name)

            # Check if tickets feature is enabled
            if not GuildQueries.is_feature_enabled(guild_id, 'tickets'):
                await interaction.followup.send(
                    "Ticket system is not enabled on this server.\n"
                    "Use `/feature tickets true` to enable it.",
                    ephemeral=True
                )
                return

            # Create panel in database
            panel = TicketQueries.create_panel(
                guild_id=guild_id,
                channel_id=channel.id,
                title=title,
                description=description,
                button_label=button_label,
                ticket_category_id=category.id if category else None,
                transcript_channel_id=transcript_channel.id if transcript_channel else None,
                support_role_id=support_role.id if support_role else None,
                welcome_message=f"Thank you for opening a ticket! A member of our support team will be with you shortly."
            )

            # Create the embed
            embed = discord.Embed(
                title=title,
                description=description,
                color=discord.Color.blue()
            )
            embed.set_footer(text=f"{interaction.guild.name} • Support System")

            # Create the button view
            view = TicketPanelView(panel_id=panel['id'])

            # Send the panel message
            message = await channel.send(embed=embed, view=view)

            # Update panel with message ID
            TicketQueries.update_panel_message(panel['id'], message.id)

            # Log to audit
            AuditQueries.log(
                guild_id=guild_id,
                action_type='ticket_panel_created',
                performed_by_id=interaction.user.id,
                performed_by_name=str(interaction.user),
                details={
                    'panel_id': panel['id'],
                    'channel_id': channel.id,
                    'title': title
                }
            )

            await interaction.followup.send(
                f"Ticket panel created in {channel.mention}!\n"
                f"Panel ID: `{panel['id']}`",
                ephemeral=True
            )

        except Exception as e:
            logger.error(f"Error creating ticket panel: {e}", exc_info=True)
            await interaction.followup.send(
                "An error occurred while creating the ticket panel.",
                ephemeral=True
            )

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

    # ==========================================
    # TICKET MANAGEMENT COMMANDS
    # ==========================================

    @app_commands.command(
        name="close",
        description="Close the current ticket"
    )
    @app_commands.guild_only()
    @app_commands.describe(
        reason="Reason for closing the ticket"
    )
    async def close_ticket(self, interaction: discord.Interaction, reason: str = None):
        """Close a ticket."""

        try:
            # Check if this is a ticket channel
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

            await interaction.response.defer()

            # Get panel for transcript channel
            panel = TicketQueries.get_panel(ticket['panel_id']) if ticket['panel_id'] else None

            # Generate transcript before closing
            transcript_embed = await self._generate_transcript(
                ticket, interaction.guild, interaction.user, reason
            )

            # Post transcript if channel is configured
            transcript_message = None
            if panel and panel['transcript_channel_id']:
                transcript_channel = interaction.guild.get_channel(panel['transcript_channel_id'])
                if transcript_channel:
                    transcript_message = await transcript_channel.send(embed=transcript_embed)
                    TicketQueries.set_transcript(ticket['id'], transcript_message.id)

            # Close the ticket
            TicketQueries.close_ticket(
                ticket_id=ticket['id'],
                closed_by_id=interaction.user.id,
                closed_by_name=str(interaction.user),
                reason=reason
            )

            # Log to audit
            AuditQueries.log(
                guild_id=interaction.guild_id,
                action_type='ticket_closed',
                performed_by_id=interaction.user.id,
                performed_by_name=str(interaction.user),
                target_user_id=ticket['user_id'],
                details={
                    'ticket_id': ticket['id'],
                    'ticket_number': ticket['ticket_number'],
                    'reason': reason
                }
            )

            # Send closing message
            close_embed = discord.Embed(
                title="Ticket Closed",
                description=f"This ticket has been closed by {interaction.user.mention}",
                color=discord.Color.red(),
                timestamp=datetime.now()
            )
            if reason:
                close_embed.add_field(name="Reason", value=reason, inline=False)

            if transcript_message:
                close_embed.add_field(
                    name="Transcript",
                    value=f"[View Transcript](https://discord.com/channels/{interaction.guild_id}/{panel['transcript_channel_id']}/{transcript_message.id})",
                    inline=False
                )

            await interaction.followup.send(embed=close_embed)

            # Try to DM the ticket creator
            try:
                creator = interaction.guild.get_member(ticket['user_id'])
                if creator:
                    dm_embed = discord.Embed(
                        title="Ticket Closed",
                        description=f"Your ticket in **{interaction.guild.name}** has been closed.",
                        color=discord.Color.blue(),
                        timestamp=datetime.now()
                    )
                    dm_embed.add_field(name="Ticket ID", value=str(ticket['ticket_number']), inline=True)
                    dm_embed.add_field(name="Closed By", value=str(interaction.user), inline=True)
                    if reason:
                        dm_embed.add_field(name="Reason", value=reason, inline=False)

                    if transcript_message:
                        dm_embed.add_field(
                            name="Transcript",
                            value=f"[View Online Transcript](https://discord.com/channels/{interaction.guild_id}/{panel['transcript_channel_id']}/{transcript_message.id})",
                            inline=False
                        )

                    dm_embed.set_footer(text=f"{interaction.guild.name} • Support System")
                    await creator.send(embed=dm_embed)
            except discord.Forbidden:
                pass

            # Delete the channel after a short delay
            await interaction.channel.send("This channel will be deleted in 5 seconds...")
            import asyncio
            await asyncio.sleep(5)
            await interaction.channel.delete(reason=f"Ticket closed by {interaction.user}")

        except Exception as e:
            logger.error(f"Error closing ticket: {e}", exc_info=True)
            await interaction.followup.send(
                "An error occurred while closing the ticket.",
                ephemeral=True
            )

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

            # Claim the ticket
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

            # Add to database
            TicketQueries.add_participant(
                ticket_id=ticket['id'],
                user_id=user.id,
                username=str(user),
                added_by_id=interaction.user.id
            )

            # Add channel permissions
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

            # Remove from database
            TicketQueries.remove_participant(ticket['id'], user.id)

            # Remove channel permissions
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
                                    closed_by: discord.User, reason: str = None) -> discord.Embed:
        """Generate a transcript embed for a closed ticket."""

        embed = discord.Embed(
            title="Ticket Closed",
            color=discord.Color.blue(),
            timestamp=datetime.now()
        )

        # Ticket info
        embed.add_field(name="Ticket ID", value=str(ticket['ticket_number']), inline=True)

        # Opened by
        opener = guild.get_member(ticket['user_id'])
        opener_text = opener.mention if opener else ticket['username']
        embed.add_field(name="Opened By", value=opener_text, inline=True)

        # Closed by
        embed.add_field(name="Closed By", value=closed_by.mention, inline=True)

        # Open time
        embed.add_field(
            name="Open Time",
            value=ticket['opened_at'].strftime("%d %B %Y %H:%M"),
            inline=True
        )

        # Claimed by
        if ticket['claimed_by_name']:
            embed.add_field(name="Claimed By", value=ticket['claimed_by_name'], inline=True)
        else:
            embed.add_field(name="Claimed By", value="Not claimed", inline=True)

        # Close reason
        embed.add_field(
            name="Reason",
            value=reason or "No reason specified",
            inline=False
        )

        # Get message count from database
        messages = TicketQueries.get_ticket_messages(ticket['id'])
        if messages:
            embed.add_field(name="Messages", value=str(len(messages)), inline=True)

        embed.set_footer(text=f"{guild.name} • Ticket System")

        return embed

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

        # Check if this is a ticket channel
        ticket = TicketQueries.get_ticket_by_channel(message.channel.id)
        if not ticket or ticket['status'] == 'closed':
            return

        # Log the message
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


class TicketPanelView(discord.ui.View):
    """Persistent view for ticket panel buttons."""

    def __init__(self, panel_id: int):
        super().__init__(timeout=None)
        self.panel_id = panel_id

        # Add the button with a custom_id for persistence
        button = discord.ui.Button(
            label="Open Ticket",
            emoji="🎫",
            style=discord.ButtonStyle.primary,
            custom_id=f"ticket_panel:{panel_id}"
        )
        button.callback = self.open_ticket
        self.add_item(button)

    async def open_ticket(self, interaction: discord.Interaction):
        """Handle ticket creation."""

        await interaction.response.defer(ephemeral=True)

        try:
            panel = TicketQueries.get_panel(self.panel_id)
            if not panel:
                await interaction.followup.send(
                    "This ticket panel no longer exists.",
                    ephemeral=True
                )
                return

            guild_id = interaction.guild_id

            # Check if user already has an open ticket
            existing = TicketQueries.get_user_open_tickets(guild_id, interaction.user.id)
            if existing:
                await interaction.followup.send(
                    f"You already have an open ticket: <#{existing[0]['channel_id']}>\n"
                    "Please close that ticket before opening a new one.",
                    ephemeral=True
                )
                return

            # Create ticket in database first
            ticket = TicketQueries.create_ticket(
                guild_id=guild_id,
                user_id=interaction.user.id,
                username=str(interaction.user),
                panel_id=self.panel_id
            )

            # Create ticket channel
            category = None
            if panel['ticket_category_id']:
                category = interaction.guild.get_channel(panel['ticket_category_id'])

            # Set up permissions
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

            # Add support role if configured
            if panel['support_role_id']:
                support_role = interaction.guild.get_role(panel['support_role_id'])
                if support_role:
                    overwrites[support_role] = discord.PermissionOverwrite(
                        read_messages=True,
                        send_messages=True,
                        manage_messages=True
                    )

            # Create the channel
            channel = await interaction.guild.create_text_channel(
                name=f"ticket-{ticket['ticket_number']:04d}",
                category=category,
                overwrites=overwrites,
                topic=f"Ticket #{ticket['ticket_number']} | User: {interaction.user} | Opened: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
            )

            # Update ticket with channel ID
            TicketQueries.update_ticket_channel(ticket['id'], channel.id)

            # Send welcome message
            welcome_embed = discord.Embed(
                title=f"Ticket #{ticket['ticket_number']}",
                description=panel['welcome_message'] or "Thank you for opening a ticket! A staff member will assist you shortly.",
                color=discord.Color.green(),
                timestamp=datetime.now()
            )
            welcome_embed.add_field(name="Created By", value=interaction.user.mention, inline=True)
            welcome_embed.set_footer(text=f"{interaction.guild.name} • Support System")

            # Create control buttons
            control_view = TicketControlView(ticket['id'])

            await channel.send(
                content=interaction.user.mention,
                embed=welcome_embed,
                view=control_view
            )

            # Log to audit
            AuditQueries.log(
                guild_id=guild_id,
                action_type='ticket_opened',
                performed_by_id=interaction.user.id,
                performed_by_name=str(interaction.user),
                details={
                    'ticket_id': ticket['id'],
                    'ticket_number': ticket['ticket_number'],
                    'channel_id': channel.id
                }
            )

            await interaction.followup.send(
                f"Your ticket has been created: {channel.mention}",
                ephemeral=True
            )

        except Exception as e:
            logger.error(f"Error opening ticket: {e}", exc_info=True)
            await interaction.followup.send(
                "An error occurred while creating your ticket. Please try again.",
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

        # Show modal for close reason
        modal = CloseTicketModal(self.ticket_id)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Claim", emoji="🙋", style=discord.ButtonStyle.secondary,
                       custom_id="ticket_claim")
    async def claim_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Claim ticket button."""

        from services.permissions import has_admin_permission

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
        """Handle modal submission."""

        await interaction.response.defer()

        try:
            ticket = TicketQueries.get_ticket(self.ticket_id)

            if not ticket or ticket['status'] == 'closed':
                await interaction.followup.send(
                    "This ticket is already closed.",
                    ephemeral=True
                )
                return

            # Get panel for transcript channel
            panel = TicketQueries.get_panel(ticket['panel_id']) if ticket['panel_id'] else None

            # Generate transcript
            cog = interaction.client.get_cog('TicketCommands')
            transcript_embed = await cog._generate_transcript(
                ticket, interaction.guild, interaction.user, self.reason.value
            )

            # Post transcript
            transcript_message = None
            if panel and panel['transcript_channel_id']:
                transcript_channel = interaction.guild.get_channel(panel['transcript_channel_id'])
                if transcript_channel:
                    transcript_message = await transcript_channel.send(embed=transcript_embed)
                    TicketQueries.set_transcript(ticket['id'], transcript_message.id)

            # Close the ticket
            TicketQueries.close_ticket(
                ticket_id=ticket['id'],
                closed_by_id=interaction.user.id,
                closed_by_name=str(interaction.user),
                reason=self.reason.value or None
            )

            # Send closing message
            close_embed = discord.Embed(
                title="Ticket Closed",
                description=f"This ticket has been closed by {interaction.user.mention}",
                color=discord.Color.red(),
                timestamp=datetime.now()
            )
            if self.reason.value:
                close_embed.add_field(name="Reason", value=self.reason.value, inline=False)

            await interaction.followup.send(embed=close_embed)

            # DM the creator
            try:
                creator = interaction.guild.get_member(ticket['user_id'])
                if creator:
                    dm_embed = discord.Embed(
                        title="Ticket Closed",
                        description=f"Your ticket in **{interaction.guild.name}** has been closed.",
                        color=discord.Color.blue(),
                        timestamp=datetime.now()
                    )
                    dm_embed.add_field(name="Ticket ID", value=str(ticket['ticket_number']), inline=True)
                    dm_embed.add_field(name="Closed By", value=str(interaction.user), inline=True)
                    if self.reason.value:
                        dm_embed.add_field(name="Reason", value=self.reason.value, inline=False)

                    if transcript_message:
                        dm_embed.add_field(
                            name="Transcript",
                            value=f"[View Online Transcript](https://discord.com/channels/{interaction.guild_id}/{panel['transcript_channel_id']}/{transcript_message.id})",
                            inline=False
                        )

                    await creator.send(embed=dm_embed)
            except discord.Forbidden:
                pass

            # Delete channel
            await interaction.channel.send("This channel will be deleted in 5 seconds...")
            import asyncio
            await asyncio.sleep(5)
            await interaction.channel.delete(reason=f"Ticket closed by {interaction.user}")

        except Exception as e:
            logger.error(f"Error in close modal: {e}", exc_info=True)


async def setup(bot: commands.Bot):
    """Load the TicketCommands cog."""
    cog = TicketCommands(bot)
    await bot.add_cog(cog)

    # Register persistent views
    panels = []
    try:
        from database.connection import get_cursor
        with get_cursor() as cursor:
            cursor.execute("SELECT id FROM ticket_panels")
            panels = cursor.fetchall()
    except Exception as e:
        logger.warning(f"Could not load ticket panels: {e}")

    for panel in panels:
        bot.add_view(TicketPanelView(panel['id']))

    logger.info(f"Registered {len(panels)} ticket panel views")
