# cogs/panel_launcher.py
"""
Panel Launcher - Main panel discovery hub

Provides the main `/panel` command that shows all accessible panels based on
user permissions and premium status. Acts as the primary discovery tool for
bot features.
"""

import discord
from discord import app_commands
from discord.ext import commands
from services.permissions import get_user_allowed_commands
from services.panel_router import PanelRouter
import logging

logger = logging.getLogger(__name__)


class PanelLauncher(commands.Cog):
    """Main panel launcher - discovery hub for all bot features."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="panel", description="Open TBNManager control panel")
    @app_commands.guild_only()
    async def panel(self, interaction: discord.Interaction):
        """Main panel launcher showing all accessible panels."""

        guild_id = interaction.guild_id
        user_id = interaction.user.id

        # Get user permissions
        user_permissions = get_user_allowed_commands(guild_id, interaction.user)

        # Build panel list based on access using meta-permissions
        available_panels = []

        # Core panels - check meta-permissions
        if 'panel.players' in user_permissions:
            available_panels.append(("Players", "👥", "players", "Player management and linking"))

        if 'panel.enforcement' in user_permissions:
            available_panels.append(("Enforcement", "⚖️", "enforcement", "Strikes, bans, and moderation"))

        if 'panel.tickets' in user_permissions:
            available_panels.append(("Tickets", "🎫", "tickets", "Support ticket system"))

        if 'panel.moderation' in user_permissions:
            available_panels.append(("Moderation", "🛡️", "moderation", "Server moderation tools"))

        if 'panel.settings' in user_permissions:
            available_panels.append(("Settings", "⚙️", "settings", "Bot configuration (Owner)"))

        # Premium panels (Infrastructure) - check meta-permissions
        # Note: Premium tier checking should also be done here when subscription system is available
        if 'panel.rcon' in user_permissions:
            available_panels.append(("RCON Panel", "🎮", "rcon", "Direct server commands"))

        if 'panel.pterodactyl' in user_permissions:
            available_panels.append(("Pterodactyl Panel", "🖥️", "pterodactyl", "Server control"))

        if 'panel.logs' in user_permissions:
            available_panels.append(("Logs Panel", "📊", "logs", "SFTP log monitoring"))

        # Check if user has access to any panels
        if not available_panels:
            await interaction.response.send_message(
                "❌ You don't have access to any panels.\n"
                "Contact an administrator to configure your permissions.",
                ephemeral=True
            )
            return

        # Split panels into core and premium categories
        core_panels = [p for p in available_panels if p[2] not in ['rcon', 'pterodactyl', 'logs']]
        premium_panels = [p for p in available_panels if p[2] in ['rcon', 'pterodactyl', 'logs']]

        # Create panel launcher embed
        embed = discord.Embed(
            title="🎛️ TBNManager Control Panel",
            description="Select a panel to get started:",
            color=discord.Color.blue()
        )

        # Add core features section
        if core_panels:
            core_text = "\n".join([f"{icon} **{name}** - {desc}" for name, icon, _, desc in core_panels])
            embed.add_field(name="Core Features", value=core_text, inline=False)

        # Add premium infrastructure section
        if premium_panels:
            premium_text = "\n".join([f"{icon} **{name}** - {desc}" for name, icon, _, desc in premium_panels])
            embed.add_field(name="🏗️ Infrastructure (Premium)", value=premium_text, inline=False)

        embed.set_footer(text="Use the dropdown menu to select a panel")

        # Send initial message without view
        await interaction.response.send_message(embed=embed, ephemeral=True)

        # Get the message object and create view with message reference for refresh capability
        launcher_message = await interaction.original_response()
        view = PanelLauncherView(self, available_panels, launcher_message, core_panels, premium_panels)

        # Edit message to add the view
        await launcher_message.edit(view=view)

    async def _refresh_launcher(self, launcher_message, available_panels, core_panels, premium_panels):
        """Refresh the launcher dropdown by recreating the view."""
        try:
            # Recreate the embed
            embed = discord.Embed(
                title="🎛️ TBNManager Control Panel",
                description="Select a panel to get started:",
                color=discord.Color.blue()
            )

            # Add core features section
            if core_panels:
                core_text = "\n".join([f"{icon} **{name}** - {desc}" for name, icon, _, desc in core_panels])
                embed.add_field(name="Core Features", value=core_text, inline=False)

            # Add premium infrastructure section
            if premium_panels:
                premium_text = "\n".join([f"{icon} **{name}** - {desc}" for name, icon, _, desc in premium_panels])
                embed.add_field(name="🏗️ Infrastructure (Premium)", value=premium_text, inline=False)

            embed.set_footer(text="Use the dropdown menu to select a panel")

            # Create fresh view with reset dropdown
            view = PanelLauncherView(self, available_panels, launcher_message, core_panels, premium_panels)

            # Edit the launcher message to refresh the dropdown
            await launcher_message.edit(embed=embed, view=view)
        except Exception as e:
            logger.error(f"Error refreshing panel launcher: {e}", exc_info=True)


class PanelLauncherView(discord.ui.View):
    """View with dropdown to select panel."""

    def __init__(self, cog, panels, launcher_message=None, core_panels=None, premium_panels=None):
        super().__init__(timeout=300)
        self.cog = cog
        self.launcher_message = launcher_message
        self.add_item(PanelLauncherSelect(cog, panels, launcher_message, core_panels, premium_panels))


class PanelLauncherSelect(discord.ui.Select):
    """Dropdown menu for panel selection."""

    def __init__(self, cog, panels, launcher_message=None, core_panels=None, premium_panels=None):
        self.cog = cog
        self.launcher_message = launcher_message
        self.available_panels = panels
        self.core_panels = core_panels
        self.premium_panels = premium_panels

        # Create select options from available panels
        options = []
        for name, icon, panel_id, desc in panels:
            options.append(
                discord.SelectOption(
                    label=name,
                    description=desc[:100],  # Discord limit
                    emoji=icon,
                    value=panel_id
                )
            )

        super().__init__(
            placeholder="Choose a panel...",
            options=options,
            row=0
        )

        self.panels = {panel_id: name for name, icon, panel_id, desc in panels}

    async def callback(self, interaction: discord.Interaction):
        """Open the selected panel using the router."""
        selected_panel = self.values[0]

        logger.info(
            f"User {interaction.user.id} selected panel '{selected_panel}' "
            f"from launcher in guild {interaction.guild_id}"
        )

        # Use panel router for safe, centralized routing
        await PanelRouter.open_panel(interaction, selected_panel)

        # Refresh the launcher dropdown to allow reselection
        if self.launcher_message and self.available_panels:
            await self.cog._refresh_launcher(
                self.launcher_message,
                self.available_panels,
                self.core_panels,
                self.premium_panels
            )


async def setup(bot: commands.Bot):
    """Load the PanelLauncher cog."""
    await bot.add_cog(PanelLauncher(bot))
