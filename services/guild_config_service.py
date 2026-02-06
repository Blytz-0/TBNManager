# services/guild_config_service.py
"""
Guild Configuration Service - Bot configuration and settings logic
Shared between slash commands and settings panel.
"""

import discord
import logging
from database.queries import GuildQueries, PermissionQueries, AuditQueries
from config.settings import DEFAULT_FEATURES, PREMIUM_FEATURES, FEATURE_DESCRIPTIONS
from config.commands import get_command_count

logger = logging.getLogger(__name__)


async def view_configuration(interaction: discord.Interaction):
    """Display current bot configuration."""
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
                role_text = "Use `/rolepermissions` to edit\n" + "\n".join(role_lines)
            else:
                role_text = "No roles configured.\nUse `/rolepermissions` to set up permissions."
        else:
            role_text = "No roles configured.\nUse `/rolepermissions` to set up permissions."

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
            display_name = FEATURE_DESCRIPTIONS.get(feature, feature)
            feature_status.append(f"{status} {display_name}")

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
            display_name = FEATURE_DESCRIPTIONS.get(feature, feature)
            premium_status.append(f"{status} {display_name}")

        embed.add_field(
            name="Premium Features",
            value="\n".join(premium_status),
            inline=True
        )

        embed.set_footer(text="Use /rolepermissions, /setchannel, /feature to configure")

        await interaction.response.send_message(embed=embed, ephemeral=True)

    except Exception as e:
        logger.error(f"Error viewing configuration: {e}", exc_info=True)
        await interaction.response.send_message(
            "An error occurred while loading configuration.",
            ephemeral=True
        )


async def toggle_feature(interaction: discord.Interaction, feature: str, enabled: bool):
    """Toggle a feature on or off."""
    try:
        guild_id = interaction.guild_id

        # Check if feature exists
        all_features = DEFAULT_FEATURES + PREMIUM_FEATURES
        if feature not in all_features:
            await interaction.response.send_message(
                f"❌ Unknown feature: `{feature}`",
                ephemeral=True
            )
            return

        # Check if premium feature and guild has premium
        if feature in PREMIUM_FEATURES:
            guild_data = GuildQueries.get_or_create(guild_id, interaction.guild.name)
            if not guild_data.get('is_premium'):
                await interaction.response.send_message(
                    f"❌ `{feature}` is a premium feature. Upgrade to enable it.",
                    ephemeral=True
                )
                return

        # Toggle the feature
        GuildQueries.set_feature(guild_id, feature, enabled)

        # Log to audit
        AuditQueries.log(
            guild_id=guild_id,
            action_type=AuditQueries.ACTION_FEATURE_TOGGLE,
            performed_by_id=interaction.user.id,
            performed_by_name=str(interaction.user),
            details={'feature': feature, 'enabled': enabled}
        )

        status = "enabled" if enabled else "disabled"
        display_name = FEATURE_DESCRIPTIONS.get(feature, feature)

        embed = discord.Embed(
            title="Feature Updated",
            description=f"**{display_name}** has been {status}.",
            color=discord.Color.green() if enabled else discord.Color.orange()
        )
        embed.add_field(name="Feature", value=display_name, inline=True)
        embed.add_field(name="Status", value="✅ Enabled" if enabled else "❌ Disabled", inline=True)
        embed.add_field(name="Updated by", value=interaction.user.mention, inline=True)

        await interaction.response.send_message(embed=embed)

    except Exception as e:
        logger.error(f"Error toggling feature: {e}", exc_info=True)
        await interaction.response.send_message(
            "An error occurred while updating the feature.",
            ephemeral=True
        )


async def set_channel(interaction: discord.Interaction, purpose: str, channel: discord.TextChannel):
    """Set a channel for a specific purpose."""
    try:
        guild_id = interaction.guild_id

        # Valid purposes
        valid_purposes = ['logs', 'announcements', 'rules', 'role_selection']
        if purpose not in valid_purposes:
            await interaction.response.send_message(
                f"❌ Invalid purpose. Valid options: {', '.join(valid_purposes)}",
                ephemeral=True
            )
            return

        # Set the channel
        GuildQueries.set_channel(guild_id, purpose, channel.id)

        # Log to audit
        AuditQueries.log(
            guild_id=guild_id,
            action_type=AuditQueries.ACTION_CONFIG_CHANGE,
            performed_by_id=interaction.user.id,
            performed_by_name=str(interaction.user),
            details={'channel_purpose': purpose, 'channel_id': channel.id, 'channel_name': channel.name}
        )

        embed = discord.Embed(
            title="Channel Configuration Updated",
            description=f"**{purpose.replace('_', ' ').title()}** channel has been set.",
            color=discord.Color.green()
        )
        embed.add_field(name="Purpose", value=purpose.replace('_', ' ').title(), inline=True)
        embed.add_field(name="Channel", value=channel.mention, inline=True)
        embed.add_field(name="Updated by", value=interaction.user.mention, inline=True)

        await interaction.response.send_message(embed=embed)

    except Exception as e:
        logger.error(f"Error setting channel: {e}", exc_info=True)
        await interaction.response.send_message(
            "An error occurred while setting the channel.",
            ephemeral=True
        )


async def set_admin_role(interaction: discord.Interaction, role: discord.Role):
    """Add an admin role to the guild."""
    try:
        guild_id = interaction.guild_id

        # Add admin role
        GuildQueries.add_admin_role(guild_id, role.id)

        # Log to audit
        AuditQueries.log(
            guild_id=guild_id,
            action_type=AuditQueries.ACTION_CONFIG_CHANGE,
            performed_by_id=interaction.user.id,
            performed_by_name=str(interaction.user),
            details={'action': 'add_admin_role', 'role_id': role.id, 'role_name': role.name}
        )

        embed = discord.Embed(
            title="Admin Role Added",
            description=f"**{role.name}** has been added as an admin role.",
            color=discord.Color.green()
        )
        embed.add_field(name="Role", value=role.mention, inline=True)
        embed.add_field(name="Added by", value=interaction.user.mention, inline=True)

        await interaction.response.send_message(embed=embed)

    except Exception as e:
        logger.error(f"Error adding admin role: {e}", exc_info=True)
        await interaction.response.send_message(
            "An error occurred while adding the admin role.",
            ephemeral=True
        )


async def remove_admin_role(interaction: discord.Interaction, role: discord.Role):
    """Remove an admin role from the guild."""
    try:
        guild_id = interaction.guild_id

        # Remove admin role
        GuildQueries.remove_admin_role(guild_id, role.id)

        # Log to audit
        AuditQueries.log(
            guild_id=guild_id,
            action_type=AuditQueries.ACTION_CONFIG_CHANGE,
            performed_by_id=interaction.user.id,
            performed_by_name=str(interaction.user),
            details={'action': 'remove_admin_role', 'role_id': role.id, 'role_name': role.name}
        )

        embed = discord.Embed(
            title="Admin Role Removed",
            description=f"**{role.name}** has been removed from admin roles.",
            color=discord.Color.orange()
        )
        embed.add_field(name="Role", value=role.mention, inline=True)
        embed.add_field(name="Removed by", value=interaction.user.mention, inline=True)

        await interaction.response.send_message(embed=embed)

    except Exception as e:
        logger.error(f"Error removing admin role: {e}", exc_info=True)
        await interaction.response.send_message(
            "An error occurred while removing the admin role.",
            ephemeral=True
        )


async def list_admin_roles(interaction: discord.Interaction):
    """List all admin roles for the guild."""
    try:
        guild_id = interaction.guild_id

        # Get admin roles
        admin_roles = GuildQueries.get_admin_roles(guild_id)

        embed = discord.Embed(
            title="Admin Roles",
            description=f"Admin roles configured for this server",
            color=discord.Color.blue()
        )

        if not admin_roles:
            embed.add_field(
                name="No Admin Roles",
                value="No admin roles have been configured.\nUse Set Admin Role to add one.",
                inline=False
            )
        else:
            # Show roles
            role_mentions = []
            for role_data in admin_roles:
                role_id = role_data['role_id']
                role = interaction.guild.get_role(role_id)
                if role:
                    role_mentions.append(role.mention)
                else:
                    role_mentions.append(f"~~Deleted Role ({role_id})~~")

            embed.add_field(
                name=f"Admin Roles ({len(admin_roles)})",
                value="\n".join(role_mentions),
                inline=False
            )

        embed.set_footer(text="Admin roles have full access to bot commands")

        await interaction.response.send_message(embed=embed, ephemeral=True)

    except Exception as e:
        logger.error(f"Error listing admin roles: {e}", exc_info=True)
        await interaction.response.send_message(
            "An error occurred while retrieving admin roles.",
            ephemeral=True
        )
