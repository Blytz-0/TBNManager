# services/tickets_service.py
"""
Tickets Service - Basic ticket operations
Shared between slash commands and tickets panel.
"""

import discord
import logging
from database.queries import TicketQueries, AuditQueries
from datetime import datetime

logger = logging.getLogger(__name__)


async def list_open_tickets(interaction: discord.Interaction):
    """List all open tickets in the server."""
    try:
        guild_id = interaction.guild_id

        # Get all open tickets
        tickets = TicketQueries.get_all_tickets(guild_id, status='open')

        if not tickets:
            await interaction.response.send_message(
                "No open tickets found.",
                ephemeral=True
            )
            return

        embed = discord.Embed(
            title="📋 Open Tickets",
            description=f"Total: **{len(tickets)}** open ticket(s)",
            color=discord.Color.blue()
        )

        # Show up to 15 tickets
        for ticket in tickets[:15]:
            channel = interaction.guild.get_channel(ticket['channel_id'])
            channel_mention = channel.mention if channel else "❌ Deleted"

            creator = interaction.guild.get_member(ticket['user_id'])
            creator_mention = creator.mention if creator else f"User {ticket['user_id']}"

            opened_date = datetime.fromisoformat(ticket['created_at'])

            claimed_text = ""
            if ticket.get('claimed_by_id'):
                claimed_by = interaction.guild.get_member(ticket['claimed_by_id'])
                if claimed_by:
                    claimed_text = f"\n🔧 Claimed by {claimed_by.mention}"

            embed.add_field(
                name=f"Ticket #{ticket['id']} - {ticket['button_type']}",
                value=f"**Creator:** {creator_mention}\n"
                      f"**Channel:** {channel_mention}\n"
                      f"**Opened:** {opened_date.strftime('%Y-%m-%d %H:%M')}"
                      f"{claimed_text}",
                inline=False
            )

        if len(tickets) > 15:
            embed.set_footer(text=f"Showing 15 of {len(tickets)} tickets")

        await interaction.response.send_message(embed=embed, ephemeral=True)

    except Exception as e:
        logger.error(f"Error listing tickets: {e}", exc_info=True)
        await interaction.response.send_message(
            "An error occurred while retrieving tickets.",
            ephemeral=True
        )


async def close_ticket_from_channel(interaction: discord.Interaction, reason: str):
    """Close a ticket from its channel."""
    try:
        guild_id = interaction.guild_id
        channel_id = interaction.channel_id

        # Check if current channel is a ticket
        ticket = TicketQueries.get_ticket_by_channel(guild_id, channel_id)

        if not ticket:
            await interaction.response.send_message(
                "❌ This is not a ticket channel.",
                ephemeral=True
            )
            return

        if ticket['status'] != 'open':
            await interaction.response.send_message(
                "❌ This ticket is already closed.",
                ephemeral=True
            )
            return

        # Defer response as this might take a while
        await interaction.response.defer()

        # Close the ticket
        TicketQueries.close_ticket(guild_id, ticket['id'], interaction.user.id, reason)

        # Log to audit
        AuditQueries.log(
            guild_id=guild_id,
            action_type=AuditQueries.ACTION_TICKET_CLOSE,
            performed_by_id=interaction.user.id,
            performed_by_name=str(interaction.user),
            details={
                'ticket_id': ticket['id'],
                'reason': reason,
                'channel_id': channel_id
            }
        )

        # Send confirmation
        embed = discord.Embed(
            title="🔒 Ticket Closed",
            description=f"This ticket has been closed.",
            color=discord.Color.green()
        )
        embed.add_field(name="Closed by", value=interaction.user.mention, inline=True)
        embed.add_field(name="Reason", value=reason, inline=False)
        embed.set_footer(text=f"Ticket #{ticket['id']} | This channel will be deleted shortly")

        await interaction.followup.send(embed=embed)

        # Try to DM the ticket creator
        try:
            creator = interaction.guild.get_member(ticket['user_id'])
            if creator:
                dm_embed = discord.Embed(
                    title="Ticket Closed",
                    description=f"Your ticket in **{interaction.guild.name}** has been closed.",
                    color=discord.Color.blue()
                )
                dm_embed.add_field(name="Ticket Type", value=ticket['button_type'], inline=True)
                dm_embed.add_field(name="Closed by", value=str(interaction.user), inline=True)
                dm_embed.add_field(name="Reason", value=reason, inline=False)

                await creator.send(embed=dm_embed)
        except:
            pass  # Ignore DM failures

        # Delete the channel after a short delay
        import asyncio
        await asyncio.sleep(5)
        channel = interaction.guild.get_channel(channel_id)
        if channel:
            await channel.delete(reason=f"Ticket closed by {interaction.user}")

    except Exception as e:
        logger.error(f"Error closing ticket: {e}", exc_info=True)
        await interaction.followup.send(
            "An error occurred while closing the ticket.",
            ephemeral=True
        )


async def create_ticket_panel(interaction: discord.Interaction, channel: discord.TextChannel,
                             title: str, description: str):
    """Create a new ticket panel."""
    try:
        guild_id = interaction.guild_id

        # Create panel in database
        panel = TicketQueries.create_panel(
            guild_id=guild_id,
            channel_id=channel.id,
            title=title,
            description=description,
            created_by_id=interaction.user.id
        )

        # Create embed for the panel
        embed = discord.Embed(
            title=title,
            description=description,
            color=discord.Color.blue()
        )
        embed.set_footer(text="Click a button below to create a ticket")

        # Create view with default button (we'll start with General Support)
        view = discord.ui.View(timeout=None)

        # Add a basic "Create Ticket" button
        button = discord.ui.Button(
            label="🎫 Create Ticket",
            style=discord.ButtonStyle.primary,
            custom_id=f"ticket_create_{panel['id']}_general"
        )
        view.add_item(button)

        # Send the panel message
        panel_message = await channel.send(embed=embed, view=view)

        # Update panel with message ID
        TicketQueries.set_panel_message_id(panel['id'], panel_message.id)

        # Log to audit
        AuditQueries.log(
            guild_id=guild_id,
            action_type=AuditQueries.ACTION_TICKET_PANEL_CREATE,
            performed_by_id=interaction.user.id,
            performed_by_name=str(interaction.user),
            details={
                'panel_id': panel['id'],
                'channel_id': channel.id,
                'title': title
            }
        )

        # Confirm to user
        await interaction.response.send_message(
            f"✅ Ticket panel created in {channel.mention}\n"
            f"**Note:** Use `/addbutton` to add more ticket types to this panel.",
            ephemeral=True
        )

    except Exception as e:
        logger.error(f"Error creating ticket panel: {e}", exc_info=True)
        await interaction.response.send_message(
            "An error occurred while creating the ticket panel.",
            ephemeral=True
        )


async def list_panels(interaction: discord.Interaction):
    """List all ticket panels in the server."""
    try:
        panels = TicketQueries.get_guild_panels(interaction.guild_id)

        if not panels:
            await interaction.response.send_message(
                "No ticket panels found. Create one with the Create Panel action.",
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

            created_date = datetime.fromisoformat(panel['created_at'])

            embed.add_field(
                name=f"Panel #{panel['id']}: {panel['title']}",
                value=f"**Channel:** {channel_text}\n"
                      f"**Buttons:** {len(buttons)}\n"
                      f"**Created:** {created_date.strftime('%Y-%m-%d')}",
                inline=True
            )

        await interaction.response.send_message(embed=embed, ephemeral=True)

    except Exception as e:
        logger.error(f"Error listing panels: {e}", exc_info=True)
        await interaction.response.send_message(
            "An error occurred while listing panels.",
            ephemeral=True
        )


async def claim_ticket(interaction: discord.Interaction):
    """Claim the current ticket."""
    try:
        ticket = TicketQueries.get_ticket_by_channel(interaction.guild_id, interaction.channel_id)

        if not ticket:
            await interaction.response.send_message(
                "This command can only be used in a ticket channel.",
                ephemeral=True
            )
            return

        if ticket.get('claimed_by_id'):
            await interaction.response.send_message(
                f"This ticket is already claimed.",
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
            ticket['id'],
            interaction.user.id,
            str(interaction.user)
        )

        # Log to audit
        AuditQueries.log(
            guild_id=interaction.guild_id,
            action_type=AuditQueries.ACTION_TICKET_CLAIM,
            performed_by_id=interaction.user.id,
            performed_by_name=str(interaction.user),
            details={'ticket_id': ticket['id'], 'channel_id': interaction.channel_id}
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


async def add_user_to_ticket(interaction: discord.Interaction, user: discord.Member):
    """Add a user to the current ticket."""
    try:
        ticket = TicketQueries.get_ticket_by_channel(interaction.guild_id, interaction.channel_id)

        if not ticket:
            await interaction.response.send_message(
                "This command can only be used in a ticket channel.",
                ephemeral=True
            )
            return

        # Add participant to database
        TicketQueries.add_participant(
            ticket['id'],
            user.id,
            str(user),
            interaction.user.id
        )

        # Set channel permissions
        await interaction.channel.set_permissions(
            user,
            read_messages=True,
            send_messages=True,
            reason=f"Added to ticket by {interaction.user}"
        )

        # Log to audit
        AuditQueries.log(
            guild_id=interaction.guild_id,
            action_type=AuditQueries.ACTION_TICKET_ADD_USER,
            performed_by_id=interaction.user.id,
            performed_by_name=str(interaction.user),
            details={'ticket_id': ticket['id'], 'added_user_id': user.id, 'added_user_name': str(user)}
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


async def remove_user_from_ticket(interaction: discord.Interaction, user: discord.Member):
    """Remove a user from the current ticket."""
    try:
        ticket = TicketQueries.get_ticket_by_channel(interaction.guild_id, interaction.channel_id)

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

        # Remove participant from database
        TicketQueries.remove_participant(ticket['id'], user.id)

        # Remove channel permissions
        await interaction.channel.set_permissions(
            user,
            overwrite=None,
            reason=f"Removed from ticket by {interaction.user}"
        )

        # Log to audit
        AuditQueries.log(
            guild_id=interaction.guild_id,
            action_type=AuditQueries.ACTION_TICKET_REMOVE_USER,
            performed_by_id=interaction.user.id,
            performed_by_name=str(interaction.user),
            details={'ticket_id': ticket['id'], 'removed_user_id': user.id, 'removed_user_name': str(user)}
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
