# services/panel_router.py
"""
Panel Router - Centralized routing for panel access

Provides safe, centralized routing logic for opening panels from various entry points
(main launcher, buttons, modals, etc.). Handles interaction safety and provides a
single place for logging/tracing panel access.
"""

import discord
import logging

logger = logging.getLogger(__name__)


class PanelRouter:
    """Central router for opening panels safely."""

    # Map panel identifiers to (registered_cog_name, method_name)
    # Note: Use the 'name' parameter from GroupCog definition, not the class name
    PANEL_MAP = {
        # Core panels
        "players": ("player", "player_panel"),
        "enforcement": ("enforcement", "enforcement_panel"),
        "tickets": ("tickets", "tickets_panel"),
        "moderation": ("moderation", "moderation_panel"),
        "settings": ("settings", "settings_panel"),

        # Premium panels (Infrastructure)
        "rcon": ("rcon", "rcon_panel"),
        "pterodactyl": ("pterodactyl", "pterodactyl_panel"),
        "logs": ("sftplogs", "logs_panel"),
    }

    @staticmethod
    async def open_panel(interaction: discord.Interaction, panel_name: str):
        """
        Open a panel by name. Handles routing and safety checks.

        Args:
            interaction: Discord interaction object
            panel_name: Panel identifier (e.g., "players", "enforcement")

        Raises:
            ValueError: If panel_name is not recognized
            RuntimeError: If the required cog is not loaded
        """
        bot = interaction.client

        # Validate panel name
        if panel_name not in PanelRouter.PANEL_MAP:
            logger.error(f"Unknown panel requested: {panel_name}")
            raise ValueError(f"Unknown panel: {panel_name}")

        cog_name, method_name = PanelRouter.PANEL_MAP[panel_name]
        cog = bot.get_cog(cog_name)

        # Check if cog is loaded
        if not cog:
            logger.error(f"Cog not loaded for panel {panel_name}: {cog_name}")
            await interaction.response.send_message(
                f"❌ Panel system error: {panel_name} panel is not available.\n"
                "Please contact an administrator.",
                ephemeral=True
            )
            return

        # Optional: Add logging/tracing here
        logger.info(
            f"Panel access: {panel_name} by user {interaction.user.id} "
            f"in guild {interaction.guild_id}"
        )

        # Defensive response handling (belt-and-suspenders)
        # Protects against edge cases where panel defers or double-responds
        try:
            panel_method = getattr(cog, method_name)

            # If it's a Command object (app_commands), get the callback
            if hasattr(panel_method, 'callback'):
                await panel_method.callback(cog, interaction)
            else:
                # Direct callable method
                await panel_method(interaction)
        except discord.errors.InteractionResponded:
            # Interaction already responded to - this is fine
            # Panel method handled the response
            logger.debug(f"Panel {panel_name} already responded to interaction")
            pass
        except AttributeError:
            logger.error(f"Method {method_name} not found on cog {cog_name}")
            # Try to respond if we haven't already
            try:
                await interaction.response.send_message(
                    f"❌ Panel system error: Method not found.\n"
                    "Please contact an administrator.",
                    ephemeral=True
                )
            except discord.errors.InteractionResponded:
                pass
        except Exception as e:
            logger.error(f"Error opening panel {panel_name}: {e}", exc_info=True)
            # Try to respond if we haven't already
            try:
                await interaction.response.send_message(
                    f"❌ Error opening panel: {str(e)}\n"
                    "Please contact an administrator.",
                    ephemeral=True
                )
            except discord.errors.InteractionResponded:
                pass

    @staticmethod
    def get_available_panels() -> list[str]:
        """
        Get list of all registered panel identifiers.

        Returns:
            List of panel identifier strings
        """
        return list(PanelRouter.PANEL_MAP.keys())

    @staticmethod
    def is_valid_panel(panel_name: str) -> bool:
        """
        Check if a panel identifier is valid.

        Args:
            panel_name: Panel identifier to check

        Returns:
            True if panel exists, False otherwise
        """
        return panel_name in PanelRouter.PANEL_MAP
