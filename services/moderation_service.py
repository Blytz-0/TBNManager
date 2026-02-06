# services/moderation_service.py
"""
Moderation Service - Discord moderation logic
Shared between slash commands and moderation panel.
"""

import discord
import logging
from database.queries import AuditQueries
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


async def send_announcement(interaction: discord.Interaction, title: str, message: str,
                           channel: discord.TextChannel, color_str: str = "blue",
                           role_to_ping: discord.Role = None):
    """Send a formatted announcement embed."""
    try:
        # Color mapping
        color_map = {
            "red": discord.Color.red(),
            "blue": discord.Color.blue(),
            "green": discord.Color.green(),
            "yellow": discord.Color.gold(),
            "purple": discord.Color.purple(),
            "orange": discord.Color.orange(),
        }
        color = color_map.get(color_str.lower(), discord.Color.blue())

        # Create embed
        embed = discord.Embed(
            title=title,
            description=message,
            color=color,
            timestamp=datetime.utcnow()
        )
        embed.set_footer(text=f"Announced by {interaction.user.name}", icon_url=interaction.user.display_avatar.url)

        # Send announcement with optional role ping
        if role_to_ping:
            await channel.send(content=role_to_ping.mention, embed=embed)
        else:
            await channel.send(embed=embed)

        # Log to audit
        AuditQueries.log(
            guild_id=interaction.guild_id,
            action_type=AuditQueries.ACTION_ANNOUNCEMENT,
            performed_by_id=interaction.user.id,
            performed_by_name=str(interaction.user),
            details={
                'channel_id': channel.id,
                'channel_name': channel.name,
                'title': title,
                'role_pinged': str(role_to_ping) if role_to_ping else None
            }
        )

        # Confirm to user
        await interaction.response.send_message(
            f"✅ Announcement sent to {channel.mention}",
            ephemeral=True
        )

    except discord.Forbidden:
        await interaction.response.send_message(
            f"❌ I don't have permission to send messages in {channel.mention}",
            ephemeral=True
        )
    except Exception as e:
        logger.error(f"Error sending announcement: {e}", exc_info=True)
        await interaction.response.send_message(
            "An error occurred while sending the announcement.",
            ephemeral=True
        )


async def send_bot_message(interaction: discord.Interaction, message: str, channel: discord.TextChannel):
    """Send a plain message as the bot."""
    try:
        # Replace \\n with actual newlines
        formatted_message = message.replace('\\n', '\n')

        await channel.send(formatted_message)

        # Log to audit
        AuditQueries.log(
            guild_id=interaction.guild_id,
            action_type=AuditQueries.ACTION_BOT_MESSAGE,
            performed_by_id=interaction.user.id,
            performed_by_name=str(interaction.user),
            details={'channel_id': channel.id, 'channel_name': channel.name}
        )

        await interaction.response.send_message(
            f"✅ Message sent to {channel.mention}",
            ephemeral=True
        )

    except discord.Forbidden:
        await interaction.response.send_message(
            f"❌ I don't have permission to send messages in {channel.mention}",
            ephemeral=True
        )
    except Exception as e:
        logger.error(f"Error sending message: {e}", exc_info=True)
        await interaction.response.send_message(
            "An error occurred while sending the message.",
            ephemeral=True
        )


async def clear_messages(interaction: discord.Interaction, amount: int, user: discord.Member = None):
    """Delete messages from the channel."""
    try:
        channel = interaction.channel

        # Validate amount
        if amount < 1 or amount > 100:
            await interaction.response.send_message(
                "❌ Amount must be between 1 and 100.",
                ephemeral=True
            )
            return

        # Defer the response since this might take a while
        await interaction.response.defer(ephemeral=True)

        # Delete messages
        if user:
            # Delete messages from specific user
            def check(m):
                return m.author == user

            deleted = await channel.purge(limit=amount * 2, check=check, before=datetime.utcnow())
        else:
            # Delete any messages
            deleted = await channel.purge(limit=amount, before=datetime.utcnow())

        deleted_count = len(deleted)

        # Log to audit
        AuditQueries.log(
            guild_id=interaction.guild_id,
            action_type=AuditQueries.ACTION_MESSAGE_DELETE,
            performed_by_id=interaction.user.id,
            performed_by_name=str(interaction.user),
            details={
                'channel_id': channel.id,
                'channel_name': channel.name,
                'count': deleted_count,
                'target_user': str(user) if user else None
            }
        )

        # Send confirmation
        if user:
            await interaction.followup.send(
                f"✅ Deleted {deleted_count} message(s) from {user.mention} in {channel.mention}",
                ephemeral=True
            )
        else:
            await interaction.followup.send(
                f"✅ Deleted {deleted_count} message(s) from {channel.mention}",
                ephemeral=True
            )

    except discord.Forbidden:
        await interaction.followup.send(
            "❌ I don't have permission to delete messages in this channel.",
            ephemeral=True
        )
    except Exception as e:
        logger.error(f"Error clearing messages: {e}", exc_info=True)
        await interaction.followup.send(
            "An error occurred while deleting messages.",
            ephemeral=True
        )


async def show_server_info(interaction: discord.Interaction):
    """Display server information."""
    try:
        guild = interaction.guild

        embed = discord.Embed(
            title=f"Server Information - {guild.name}",
            color=discord.Color.blue()
        )

        # Set guild icon as thumbnail
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)

        # Server info
        embed.add_field(name="Server ID", value=f"`{guild.id}`", inline=True)
        embed.add_field(name="Owner", value=guild.owner.mention if guild.owner else "Unknown", inline=True)
        embed.add_field(name="Created", value=guild.created_at.strftime("%Y-%m-%d"), inline=True)

        # Member counts
        total_members = guild.member_count
        bot_count = sum(1 for m in guild.members if m.bot)
        human_count = total_members - bot_count

        embed.add_field(name="Members", value=f"{human_count} humans\n{bot_count} bots\n**{total_members}** total", inline=True)

        # Channel counts
        text_channels = len(guild.text_channels)
        voice_channels = len(guild.voice_channels)
        categories = len(guild.categories)

        embed.add_field(name="Channels", value=f"{text_channels} text\n{voice_channels} voice\n{categories} categories", inline=True)

        # Roles
        role_count = len(guild.roles)
        embed.add_field(name="Roles", value=f"{role_count} roles", inline=True)

        await interaction.response.send_message(embed=embed, ephemeral=True)

    except Exception as e:
        logger.error(f"Error showing server info: {e}", exc_info=True)
        await interaction.response.send_message(
            "An error occurred while retrieving server information.",
            ephemeral=True
        )


async def show_user_info(interaction: discord.Interaction, user: discord.Member):
    """Display user information."""
    try:
        embed = discord.Embed(
            title=f"User Information - {user.name}",
            color=user.color
        )

        # Set user avatar as thumbnail
        embed.set_thumbnail(url=user.display_avatar.url)

        # User info
        embed.add_field(name="Username", value=user.name, inline=True)
        embed.add_field(name="User ID", value=f"`{user.id}`", inline=True)
        embed.add_field(name="Nickname", value=user.nick if user.nick else "None", inline=True)

        # Dates
        embed.add_field(name="Account Created", value=user.created_at.strftime("%Y-%m-%d"), inline=True)
        embed.add_field(name="Joined Server", value=user.joined_at.strftime("%Y-%m-%d") if user.joined_at else "Unknown", inline=True)

        # Roles
        roles = [role.mention for role in user.roles if role != interaction.guild.default_role]
        if roles:
            embed.add_field(name=f"Roles ({len(roles)})", value=" ".join(roles), inline=False)
        else:
            embed.add_field(name="Roles", value="No roles", inline=False)

        # Status
        status_emoji = {
            discord.Status.online: "🟢 Online",
            discord.Status.idle: "🟡 Idle",
            discord.Status.dnd: "🔴 Do Not Disturb",
            discord.Status.offline: "⚫ Offline"
        }
        embed.add_field(name="Status", value=status_emoji.get(user.status, "Unknown"), inline=True)

        await interaction.response.send_message(embed=embed, ephemeral=True)

    except Exception as e:
        logger.error(f"Error showing user info: {e}", exc_info=True)
        await interaction.response.send_message(
            "An error occurred while retrieving user information.",
            ephemeral=True
        )
