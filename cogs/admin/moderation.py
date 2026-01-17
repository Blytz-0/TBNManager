# cogs/admin/moderation.py
"""
Moderation and Utility Commands

Admin commands for announcements, message management, and server utilities.
"""

import discord
from discord import app_commands
from discord.ext import commands
from database.queries import GuildQueries, AuditQueries
from services.permissions import require_admin
import logging

logger = logging.getLogger(__name__)


class ModerationCommands(commands.Cog):
    """Server moderation and utility commands."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ==========================================
    # ANNOUNCEMENT COMMANDS
    # ==========================================

    @app_commands.command(
        name="announce",
        description="Send an announcement to a channel"
    )
    @app_commands.guild_only()
    @app_commands.describe(
        channel="The channel to send the announcement to",
        title="Title of the announcement",
        message="The announcement message (use \\n for new lines)",
        color="Embed color",
        ping_role="Optional role to ping"
    )
    @app_commands.choices(color=[
        app_commands.Choice(name="Blue", value="blue"),
        app_commands.Choice(name="Green", value="green"),
        app_commands.Choice(name="Red", value="red"),
        app_commands.Choice(name="Gold", value="gold"),
        app_commands.Choice(name="Purple", value="purple"),
    ])
    async def announce(self, interaction: discord.Interaction,
                       channel: discord.TextChannel,
                       title: str,
                       message: str,
                       color: str = "blue",
                       ping_role: discord.Role = None):
        """Send a formatted announcement."""

        if not await require_admin(interaction):
            return

        try:
            guild_id = interaction.guild_id
            GuildQueries.get_or_create(guild_id, interaction.guild.name)

            # Check if feature is enabled
            if not GuildQueries.is_feature_enabled(guild_id, 'announcements'):
                await interaction.response.send_message(
                    "Announcements are not enabled on this server.",
                    ephemeral=True
                )
                return

            # Parse color
            color_map = {
                'blue': discord.Color.blue(),
                'green': discord.Color.green(),
                'red': discord.Color.red(),
                'gold': discord.Color.gold(),
                'purple': discord.Color.purple(),
            }
            embed_color = color_map.get(color, discord.Color.blue())

            # Format message (replace \n with actual newlines)
            formatted_message = message.replace("\\n", "\n")

            # Create embed
            embed = discord.Embed(
                title=title,
                description=formatted_message,
                color=embed_color
            )
            embed.set_footer(text=f"Announced by {interaction.user.display_name}")
            embed.timestamp = discord.utils.utcnow()

            # Send with optional ping
            content = ping_role.mention if ping_role else None
            await channel.send(content=content, embed=embed)

            # Log to audit
            AuditQueries.log(
                guild_id=guild_id,
                action_type='announcement',
                performed_by_id=interaction.user.id,
                performed_by_name=str(interaction.user),
                details={
                    'channel_id': channel.id,
                    'title': title
                }
            )

            await interaction.response.send_message(
                f"Announcement sent to {channel.mention}!",
                ephemeral=True
            )

        except discord.Forbidden:
            await interaction.response.send_message(
                f"I don't have permission to send messages in {channel.mention}.",
                ephemeral=True
            )
        except Exception as e:
            logger.error(f"Error in /announce: {e}", exc_info=True)
            await interaction.response.send_message(
                "An error occurred while sending the announcement.",
                ephemeral=True
            )

    @app_commands.command(
        name="say",
        description="Send a message as the bot to a channel"
    )
    @app_commands.guild_only()
    @app_commands.describe(
        channel="The channel to send the message to",
        message="The message to send (use \\n for new lines)"
    )
    async def say(self, interaction: discord.Interaction,
                  channel: discord.TextChannel,
                  message: str):
        """Send a plain message as the bot."""

        if not await require_admin(interaction):
            return

        try:
            formatted_message = message.replace("\\n", "\n")
            await channel.send(formatted_message)

            await interaction.response.send_message(
                f"Message sent to {channel.mention}!",
                ephemeral=True
            )

        except discord.Forbidden:
            await interaction.response.send_message(
                f"I don't have permission to send messages in {channel.mention}.",
                ephemeral=True
            )
        except Exception as e:
            logger.error(f"Error in /say: {e}", exc_info=True)
            await interaction.response.send_message(
                "An error occurred while sending the message.",
                ephemeral=True
            )

    # ==========================================
    # MESSAGE MANAGEMENT
    # ==========================================

    @app_commands.command(
        name="clear",
        description="Delete messages from the current channel"
    )
    @app_commands.guild_only()
    @app_commands.describe(
        amount="Number of messages to delete (1-100)",
        user="Only delete messages from this user"
    )
    async def clear_messages(self, interaction: discord.Interaction,
                             amount: app_commands.Range[int, 1, 100],
                             user: discord.Member = None):
        """Delete messages from a channel."""

        if not await require_admin(interaction):
            return

        await interaction.response.defer(ephemeral=True)

        try:
            channel = interaction.channel

            if user:
                # Delete messages from specific user
                deleted = []
                async for message in channel.history(limit=200):
                    if message.author == user and len(deleted) < amount:
                        deleted.append(message)

                if deleted:
                    await channel.delete_messages(deleted)
                count = len(deleted)
            else:
                # Delete any messages
                deleted = await channel.purge(limit=amount)
                count = len(deleted)

            # Log to audit
            AuditQueries.log(
                guild_id=interaction.guild_id,
                action_type='messages_cleared',
                performed_by_id=interaction.user.id,
                performed_by_name=str(interaction.user),
                target_user_id=user.id if user else None,
                details={
                    'channel_id': channel.id,
                    'count': count
                }
            )

            user_text = f" from {user.mention}" if user else ""
            await interaction.followup.send(
                f"Deleted {count} message(s){user_text}.",
                ephemeral=True
            )

        except discord.Forbidden:
            await interaction.followup.send(
                "I don't have permission to delete messages in this channel.",
                ephemeral=True
            )
        except discord.HTTPException as e:
            if "older than 14 days" in str(e):
                await interaction.followup.send(
                    "Cannot delete messages older than 14 days. "
                    "Discord limitation.",
                    ephemeral=True
                )
            else:
                await interaction.followup.send(
                    "An error occurred while deleting messages.",
                    ephemeral=True
                )
        except Exception as e:
            logger.error(f"Error in /clear: {e}", exc_info=True)
            await interaction.followup.send(
                "An error occurred while clearing messages.",
                ephemeral=True
            )

    # ==========================================
    # SERVER INFO
    # ==========================================

    @app_commands.command(
        name="serverinfo",
        description="Display information about this server"
    )
    @app_commands.guild_only()
    async def server_info(self, interaction: discord.Interaction):
        """Display server information."""

        guild = interaction.guild

        embed = discord.Embed(
            title=guild.name,
            color=discord.Color.blue()
        )

        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)

        embed.add_field(name="Owner", value=guild.owner.mention if guild.owner else "Unknown", inline=True)
        embed.add_field(name="Members", value=str(guild.member_count), inline=True)
        embed.add_field(name="Channels", value=str(len(guild.channels)), inline=True)
        embed.add_field(name="Roles", value=str(len(guild.roles)), inline=True)
        embed.add_field(name="Created", value=guild.created_at.strftime("%Y-%m-%d"), inline=True)
        embed.add_field(name="Server ID", value=str(guild.id), inline=True)

        if guild.description:
            embed.add_field(name="Description", value=guild.description, inline=False)

        await interaction.response.send_message(embed=embed)

    @app_commands.command(
        name="userinfo",
        description="Display information about a user"
    )
    @app_commands.guild_only()
    @app_commands.describe(
        user="The user to get info about (default: yourself)"
    )
    async def user_info(self, interaction: discord.Interaction,
                        user: discord.Member = None):
        """Display user information."""

        target = user or interaction.user

        embed = discord.Embed(
            title=f"User Info: {target.display_name}",
            color=target.color if target.color != discord.Color.default() else discord.Color.blue()
        )

        embed.set_thumbnail(url=target.display_avatar.url)

        embed.add_field(name="Username", value=str(target), inline=True)
        embed.add_field(name="ID", value=str(target.id), inline=True)
        embed.add_field(name="Bot", value="Yes" if target.bot else "No", inline=True)

        embed.add_field(
            name="Account Created",
            value=target.created_at.strftime("%Y-%m-%d"),
            inline=True
        )
        embed.add_field(
            name="Joined Server",
            value=target.joined_at.strftime("%Y-%m-%d") if target.joined_at else "Unknown",
            inline=True
        )

        # Top role (excluding @everyone)
        top_role = target.top_role if target.top_role.name != "@everyone" else None
        if top_role:
            embed.add_field(name="Top Role", value=top_role.mention, inline=True)

        # Role count
        role_count = len([r for r in target.roles if r.name != "@everyone"])
        embed.add_field(name="Roles", value=str(role_count), inline=True)

        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
    """Load the ModerationCommands cog."""
    await bot.add_cog(ModerationCommands(bot))
