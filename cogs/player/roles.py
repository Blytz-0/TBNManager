# cogs/player/roles.py
"""
Reaction Role System

Allows users to self-assign roles by reacting to messages.
Admins can create role selection panels for different categories.
"""

import discord
from discord import app_commands
from discord.ext import commands
from database.queries import GuildQueries, AuditQueries
from database.connection import get_cursor
from services.permissions import require_admin
from config.constants import GENDER_ROLE_EMOJIS, PLATFORM_ROLE_EMOJIS, SERVER_ROLE_EMOJIS
import logging

logger = logging.getLogger(__name__)

# Default role configurations using custom emojis from constants
DEFAULT_ROLE_CONFIGS = {
    'gender': {
        'title': 'Gender Roles',
        'description': 'React to select your pronouns',
        'color': discord.Color.purple(),
        'roles': GENDER_ROLE_EMOJIS
    },
    'platform': {
        'title': 'Platform Roles',
        'description': 'React to show what platform you play on',
        'color': discord.Color.blue(),
        'roles': PLATFORM_ROLE_EMOJIS
    },
    'notifications': {
        'title': 'Notification Roles',
        'description': 'React to receive specific notifications',
        'color': discord.Color.gold(),
        'roles': SERVER_ROLE_EMOJIS
    }
}


class RoleSelection(commands.Cog):
    """Reaction-based role assignment system."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Cache of message_id -> {emoji: role_name}
        self._role_cache = {}

    async def cog_load(self):
        """Load role message cache from database on startup."""
        await self._refresh_cache()

    async def _refresh_cache(self):
        """Refresh the role message cache from database."""
        try:
            with get_cursor() as cursor:
                cursor.execute("""
                    SELECT rm.message_id, rem.emoji, rem.role_name
                    FROM role_messages rm
                    JOIN role_emoji_mappings rem ON rm.message_id = rem.message_id
                """)
                results = cursor.fetchall()

                self._role_cache = {}
                for row in results:
                    msg_id = row['message_id']
                    if msg_id not in self._role_cache:
                        self._role_cache[msg_id] = {}
                    self._role_cache[msg_id][row['emoji']] = row['role_name']

                logger.info(f"Loaded {len(self._role_cache)} role messages into cache")
        except Exception as e:
            logger.error(f"Failed to load role cache: {e}")

    @app_commands.command(
        name="rolepanel",
        description="Create a role selection panel"
    )
    @app_commands.guild_only()
    @app_commands.describe(
        panel_type="Type of role panel to create",
        channel="Channel to post the panel in (default: current channel)"
    )
    @app_commands.choices(panel_type=[
        app_commands.Choice(name="Gender/Pronouns", value="gender"),
        app_commands.Choice(name="Platform", value="platform"),
        app_commands.Choice(name="Notifications", value="notifications"),
    ])
    async def create_role_panel(self, interaction: discord.Interaction,
                                panel_type: str,
                                channel: discord.TextChannel = None):
        """Create a role selection panel with reactions."""

        if not await require_admin(interaction):
            return

        await interaction.response.defer()

        try:
            guild_id = interaction.guild_id
            GuildQueries.get_or_create(guild_id, interaction.guild.name)

            # Check if feature is enabled
            if not GuildQueries.is_feature_enabled(guild_id, 'role_selection'):
                await interaction.followup.send(
                    "Role selection is not enabled on this server.",
                    ephemeral=True
                )
                return

            target_channel = channel or interaction.channel
            config = DEFAULT_ROLE_CONFIGS.get(panel_type)

            if not config:
                await interaction.followup.send(
                    "Invalid panel type.",
                    ephemeral=True
                )
                return

            # Verify all roles exist
            missing_roles = []
            role_mappings = {}
            for emoji, role_name in config['roles'].items():
                role = discord.utils.get(interaction.guild.roles, name=role_name)
                if role:
                    role_mappings[emoji] = (role_name, role.id)
                else:
                    missing_roles.append(role_name)

            if missing_roles:
                await interaction.followup.send(
                    f"The following roles don't exist and need to be created:\n"
                    f"`{', '.join(missing_roles)}`\n\n"
                    f"Please create these roles first, then run the command again.",
                    ephemeral=True
                )
                return

            # Create the embed
            description_lines = [config['description'], ""]
            for emoji, role_name in config['roles'].items():
                description_lines.append(f"{emoji} — {role_name}")

            embed = discord.Embed(
                title=config['title'],
                description="\n".join(description_lines),
                color=config['color']
            )
            embed.set_footer(text="React to get/remove a role")

            # Send the message
            message = await target_channel.send(embed=embed)

            # Add reactions
            for emoji in config['roles'].keys():
                await message.add_reaction(emoji)

            # Save to database
            with get_cursor() as cursor:
                # Insert role message
                cursor.execute(
                    """INSERT INTO role_messages (guild_id, channel_id, message_id, role_type)
                       VALUES (%s, %s, %s, %s)""",
                    (guild_id, target_channel.id, message.id, panel_type)
                )

                # Insert emoji mappings
                for emoji, (role_name, role_id) in role_mappings.items():
                    cursor.execute(
                        """INSERT INTO role_emoji_mappings (message_id, emoji, role_id, role_name)
                           VALUES (%s, %s, %s, %s)""",
                        (message.id, emoji, role_id, role_name)
                    )

            # Update cache
            self._role_cache[message.id] = {e: r for e, (r, _) in role_mappings.items()}

            # Log to audit
            AuditQueries.log(
                guild_id=guild_id,
                action_type=AuditQueries.ACTION_ROLE_MESSAGE,
                performed_by_id=interaction.user.id,
                performed_by_name=str(interaction.user),
                details={
                    'panel_type': panel_type,
                    'channel_id': target_channel.id,
                    'message_id': message.id
                }
            )

            await interaction.followup.send(
                f"Role panel created in {target_channel.mention}!",
                ephemeral=True
            )

        except Exception as e:
            logger.error(f"Error creating role panel: {e}", exc_info=True)
            await interaction.followup.send(
                "An error occurred while creating the role panel.",
                ephemeral=True
            )

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        """Handle reaction adds for role assignment."""

        # Ignore bots
        if payload.member and payload.member.bot:
            return

        # Check if this is a tracked role message
        emoji_str = str(payload.emoji)
        if payload.message_id not in self._role_cache:
            return

        role_name = self._role_cache[payload.message_id].get(emoji_str)
        if not role_name:
            return

        try:
            guild = self.bot.get_guild(payload.guild_id)
            if not guild:
                return

            member = payload.member or await guild.fetch_member(payload.user_id)
            if not member or member.bot:
                return

            role = discord.utils.get(guild.roles, name=role_name)
            if role:
                await member.add_roles(role, reason="Reaction role")
                logger.debug(f"Added role {role_name} to {member} in {guild.name}")

        except discord.Forbidden:
            logger.warning(f"No permission to add role {role_name}")
        except Exception as e:
            logger.error(f"Error adding reaction role: {e}")

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        """Handle reaction removes for role removal."""

        # Check if this is a tracked role message
        emoji_str = str(payload.emoji)
        if payload.message_id not in self._role_cache:
            return

        role_name = self._role_cache[payload.message_id].get(emoji_str)
        if not role_name:
            return

        try:
            guild = self.bot.get_guild(payload.guild_id)
            if not guild:
                return

            member = await guild.fetch_member(payload.user_id)
            if not member or member.bot:
                return

            role = discord.utils.get(guild.roles, name=role_name)
            if role and role in member.roles:
                await member.remove_roles(role, reason="Reaction role removed")
                logger.debug(f"Removed role {role_name} from {member} in {guild.name}")

        except discord.Forbidden:
            logger.warning(f"No permission to remove role {role_name}")
        except discord.NotFound:
            pass  # Member left the server
        except Exception as e:
            logger.error(f"Error removing reaction role: {e}")

    @app_commands.command(
        name="refreshroles",
        description="Refresh the role panel cache (use if reactions stopped working)"
    )
    @app_commands.guild_only()
    async def refresh_roles(self, interaction: discord.Interaction):
        """Manually refresh the role cache."""

        if not await require_admin(interaction):
            return

        await self._refresh_cache()
        await interaction.response.send_message(
            f"Role cache refreshed. Tracking {len(self._role_cache)} role panels.",
            ephemeral=True
        )

    @app_commands.command(
        name="listroles",
        description="List all active role panels in this server"
    )
    @app_commands.guild_only()
    async def list_role_panels(self, interaction: discord.Interaction):
        """List all role selection panels."""

        if not await require_admin(interaction):
            return

        try:
            guild_id = interaction.guild_id

            with get_cursor() as cursor:
                cursor.execute(
                    """SELECT message_id, channel_id, role_type, created_at
                       FROM role_messages
                       WHERE guild_id = %s
                       ORDER BY created_at DESC""",
                    (guild_id,)
                )
                panels = cursor.fetchall()

            if not panels:
                await interaction.response.send_message(
                    "No role panels found in this server.",
                    ephemeral=True
                )
                return

            embed = discord.Embed(
                title="Role Panels",
                description=f"{len(panels)} panel(s) in this server",
                color=discord.Color.blue()
            )

            for panel in panels:
                channel = self.bot.get_channel(panel['channel_id'])
                channel_name = channel.mention if channel else f"Unknown ({panel['channel_id']})"

                embed.add_field(
                    name=f"{panel['role_type'].title()} Panel",
                    value=f"Channel: {channel_name}\n"
                          f"Message ID: `{panel['message_id']}`\n"
                          f"Created: {panel['created_at'].strftime('%Y-%m-%d')}",
                    inline=True
                )

            await interaction.response.send_message(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Error listing role panels: {e}", exc_info=True)
            await interaction.response.send_message(
                "An error occurred while listing role panels.",
                ephemeral=True
            )


async def setup(bot: commands.Bot):
    """Load the RoleSelection cog."""
    await bot.add_cog(RoleSelection(bot))
