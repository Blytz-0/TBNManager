# cogs/player/player_panel.py
"""
Players Panel - Unified player management interface

Provides a dropdown-based interface for:
- Account linking (Alderon ID, Steam ID)
- Player verification
- Player lookup and information
- Player management (admin)
"""

import discord
from discord import app_commands
from discord.ext import commands
from database.queries import GuildQueries, PlayerQueries
from services.permissions import require_permission, get_user_allowed_commands
from services import player_service
import logging

logger = logging.getLogger(__name__)


# ==========================================
# PLAYER ACTIONS DEFINITION
# ==========================================

PLAYER_ACTIONS = [
    ("View My IDs", "See your linked accounts", "inpanel_player_myid", "👤"),
    ("Link IDs", "Link Steam or Alderon ID", "inpanel_player_linkids", "🔗"),
    ("Verify In-Game", "Verify by typing code in chat", "inpanel_player_verify", "✅"),
    ("Look Up Player", "Search by Discord/Steam/Alderon", "inpanel_player_lookup", "🔍"),
    ("Unlink ID", "Unlink a user's ID (Admin)", "inpanel_player_unlink", "🔓"),
]


# ==========================================
# DROPDOWN-BASED PLAYER PANEL INTERFACE
# ==========================================

class PlayerCommandSelect(discord.ui.Select):
    """Dropdown menu for selecting player actions."""

    def __init__(self, cog, user_permissions: set, panel_message=None):
        self.cog = cog
        self.user_permissions = user_permissions
        self.panel_message = panel_message

        # Filter actions based on user permissions
        options = []
        for label, desc, permission, emoji in PLAYER_ACTIONS:
            if permission in user_permissions:
                options.append(
                    discord.SelectOption(
                        label=label,
                        description=desc,
                        value=permission,
                        emoji=emoji
                    )
                )

        super().__init__(
            placeholder="Choose a player action...",
            options=options,
            row=0
        )

    async def callback(self, interaction: discord.Interaction):
        """Handle action selection."""
        selected = self.values[0]

        # Route to appropriate action handler, passing panel message for refresh
        if selected == "inpanel_player_linkids":
            await self.cog._action_link_ids(interaction, self.panel_message, self.user_permissions)
        elif selected == "inpanel_player_verify":
            await self.cog._action_verify(interaction, self.panel_message, self.user_permissions)
        elif selected == "inpanel_player_lookup":
            await self.cog._action_lookup(interaction, self.panel_message, self.user_permissions)
        elif selected == "inpanel_player_myid":
            await self.cog._action_myid(interaction, self.panel_message, self.user_permissions)
        elif selected == "inpanel_player_unlink":
            await self.cog._action_unlink(interaction, self.panel_message, self.user_permissions)


class PlayerCommandView(discord.ui.View):
    """Main view with player action dropdown."""

    def __init__(self, cog, user_permissions: set, panel_message=None):
        super().__init__(timeout=300)
        self.cog = cog
        self.panel_message = panel_message
        self.add_item(PlayerCommandSelect(cog, user_permissions, panel_message))


# ==========================================
# MAIN PANEL COG
# ==========================================

class PlayerPanel(commands.GroupCog, name="player"):
    """Players Panel - unified player management interface."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        super().__init__()

    @app_commands.command(name="panel", description="Open Players control panel")
    @app_commands.guild_only()
    async def player_panel(self, interaction: discord.Interaction):
        """Show the Players control panel with dropdown selections."""
        # Check if player management feature enabled
        if not GuildQueries.is_feature_enabled(interaction.guild_id, 'player_linking'):
            await interaction.response.send_message(
                "Player management is not enabled on this server.",
                ephemeral=True
            )
            return

        # Get user's allowed commands
        user_permissions = get_user_allowed_commands(interaction.guild_id, interaction.user)

        # Filter to only inpanel_player_* permissions
        inpanel_permissions = {perm for perm in user_permissions if perm.startswith('inpanel_player_')}

        # If user has no panel permissions, show error
        if not inpanel_permissions:
            await interaction.response.send_message(
                "You don't have permission to use any player panel features.\n"
                "Contact an administrator to configure your permissions.",
                ephemeral=True
            )
            return

        embed = discord.Embed(
            title="👥 Players Panel",
            description="Select an action from the dropdown below to manage players and account linking.",
            color=discord.Color.blue()
        )
        embed.set_footer(text="Select an action from the menu")

        # Send initial message without view
        await interaction.response.send_message(embed=embed, ephemeral=True)

        # Get the message object and create view with message reference for refresh capability
        panel_message = await interaction.original_response()
        view = PlayerCommandView(self, inpanel_permissions, panel_message)

        # Edit message to add the view
        await panel_message.edit(view=view)

    @app_commands.command(name="help", description="Show Players panel help")
    @app_commands.guild_only()
    async def player_help(self, interaction: discord.Interaction):
        """Show help for Players panel."""
        # Get user's allowed commands
        user_permissions = get_user_allowed_commands(interaction.guild_id, interaction.user)

        # Filter to only inpanel_player_* permissions
        inpanel_permissions = {perm for perm in user_permissions if perm.startswith('inpanel_player_')}

        # Build list of available actions
        available_actions = []
        for label, desc, permission, emoji in PLAYER_ACTIONS:
            if permission in inpanel_permissions:
                available_actions.append((label, desc))

        # Create help embed
        embed = discord.Embed(
            title="👥 Players Panel Help",
            description="Player management and account linking commands.",
            color=discord.Color.blue()
        )

        # Access instructions
        embed.add_field(
            name="Access Panel",
            value="`/player panel` - Open the Players panel\n"
                  "`/panel` → Select Players - Via main launcher",
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

    async def _action_link_ids(self, interaction: discord.Interaction, panel_message=None, user_permissions=None):
        """Link IDs - show select menu to choose Steam or Alderon."""
        embed = discord.Embed(
            title="🔗 Link Your IDs",
            description="Select which ID type you want to link:",
            color=discord.Color.blue()
        )

        # Send the submenu first
        await interaction.response.send_message(embed=embed, ephemeral=True)

        # Get the submenu message and create view with it
        submenu_message = await interaction.original_response()
        view = LinkIDTypeView(self, submenu_message, panel_message, user_permissions)

        # Edit to add the view
        await submenu_message.edit(view=view)

    async def _action_link_alderon(self, interaction: discord.Interaction, panel_message=None, user_permissions=None):
        """Link Alderon ID - opens modal for input."""
        modal = LinkAlderonModal(self, panel_message, user_permissions)
        await interaction.response.send_modal(modal)

    async def _action_link_steam(self, interaction: discord.Interaction, panel_message=None, user_permissions=None):
        """Link Steam ID - opens modal for input."""
        modal = LinkSteamModal(self, panel_message, user_permissions)
        await interaction.response.send_modal(modal)

    async def _action_verify(self, interaction: discord.Interaction, panel_message=None, user_permissions=None):
        """Verify in-game - show info message (requires RCON premium)."""
        await interaction.response.send_message(
            "⚠️ **In-Game Verification (Premium Feature)**\n\n"
            "This feature requires RCON integration to be configured.\n"
            "Please use `/verifymyid` command or contact an administrator.",
            ephemeral=True
        )

        # Refresh the panel dropdown to allow reselection
        if panel_message and user_permissions:
            await self._refresh_panel(panel_message, user_permissions)

    async def _action_lookup(self, interaction: discord.Interaction, panel_message=None, user_permissions=None):
        """Look up player - opens modal for search."""
        modal = PlayerLookupModal(self, panel_message, user_permissions)
        await interaction.response.send_modal(modal)

    async def _action_myid(self, interaction: discord.Interaction, panel_message=None, user_permissions=None):
        """View my IDs - show user's linked accounts with rich format."""
        try:
            player = PlayerQueries.get_by_user(interaction.guild_id, interaction.user.id)

            embed = discord.Embed(
                title="Your Linked Accounts",
                color=discord.Color.blue()
            )

            # Set Discord avatar as main thumbnail
            embed.set_thumbnail(url=interaction.user.display_avatar.url)

            # Discord - always show with verification status
            display_name = interaction.user.display_name
            username = interaction.user.name
            discord_verified = "✅" if player and player.get('discord_verified') else ""
            embed.add_field(
                name=f"Discord {discord_verified}",
                value=f"@{display_name} ({username})\n**Discord ID:** `{interaction.user.id}`",
                inline=False
            )

            has_ids = False
            steam_avatar_url = None

            # Steam info with verification status
            if player and player.get('steam_id'):
                has_ids = True
                # Try to fetch Steam avatar if API is configured
                try:
                    from services.steam_api import SteamAPI
                    if SteamAPI.is_configured():
                        steam_data = await SteamAPI.get_player_summary(player['steam_id'])
                        if steam_data and steam_data.get('avatarmedium'):
                            steam_avatar_url = steam_data['avatarmedium']
                except Exception:
                    pass  # Don't fail if we can't get avatar

                steam_verified = "✅" if player.get('steam_verified') else ""
                steam_value = f"**Steam Name:** {player.get('steam_name', 'Unknown')}\n**Steam ID:** `{player['steam_id']}`"
                if steam_avatar_url:
                    steam_value += f"\n[View Profile](https://steamcommunity.com/profiles/{player['steam_id']})"
                embed.add_field(
                    name=f"Steam {steam_verified}",
                    value=steam_value,
                    inline=False
                )
            else:
                embed.add_field(
                    name="Steam",
                    value="Not linked\nUse **Link Steam ID** to link",
                    inline=False
                )

            # Alderon info with verification status
            if player and player.get('player_id'):
                has_ids = True
                alderon_verified = "✅" if player.get('alderon_verified') else ""
                embed.add_field(
                    name=f"Alderon {alderon_verified}",
                    value=f"**Player Name:** {player['player_name']}\n"
                          f"**Alderon ID:** `{player['player_id']}`",
                    inline=False
                )
            else:
                embed.add_field(
                    name="Alderon",
                    value="Not linked\nUse **Link Alderon ID** to link",
                    inline=False
                )

            # Set Steam avatar as image if available (shows at bottom)
            if steam_avatar_url:
                embed.set_image(url=steam_avatar_url)

            # Footer based on link status
            if has_ids:
                embed.set_footer(text="IDs are locked. Contact an admin to change them.")
            else:
                embed.set_footer(text="Link your game accounts to get started!")

            await interaction.response.send_message(embed=embed, ephemeral=True)

            # Refresh the panel dropdown to allow reselection
            if panel_message and user_permissions:
                await self._refresh_panel(panel_message, user_permissions)

        except Exception as e:
            logger.error(f"Error in View My IDs: {e}", exc_info=True)
            await interaction.response.send_message(
                "An error occurred. Please try again later.",
                ephemeral=True
            )

    async def _action_unlink(self, interaction: discord.Interaction, panel_message=None, user_permissions=None):
        """Unlink player ID - opens modal for player search."""
        modal = UnlinkPlayerLookupModal(self, panel_message, user_permissions)
        await interaction.response.send_modal(modal)

    async def _refresh_panel(self, panel_message, user_permissions: set):
        """Refresh the panel dropdown by recreating the view."""
        try:
            embed = discord.Embed(
                title="👥 Players Panel",
                description="Select an action from the dropdown below to manage players and account linking.",
                color=discord.Color.blue()
            )
            embed.set_footer(text="Select an action from the menu")

            # Create fresh view with reset dropdown
            view = PlayerCommandView(self, user_permissions, panel_message)

            # Edit the panel message to refresh the dropdown
            await panel_message.edit(embed=embed, view=view)
        except Exception as e:
            logger.error(f"Error refreshing panel: {e}", exc_info=True)


# ==========================================
# LINK ID TYPE SELECTION
# ==========================================

class LinkIDTypeView(discord.ui.View):
    """View for selecting which ID type to link."""

    def __init__(self, cog, submenu_message=None, panel_message=None, user_permissions=None):
        super().__init__(timeout=300)
        self.cog = cog
        self.submenu_message = submenu_message
        self.panel_message = panel_message
        self.user_permissions = user_permissions
        self.add_item(LinkIDTypeSelect(cog, submenu_message, panel_message, user_permissions))

    @discord.ui.button(label="Back to Main Panel", style=discord.ButtonStyle.secondary, row=1)
    async def back_button(self, interaction: discord.Interaction, _button: discord.ui.Button):
        """Return to main panel."""
        try:
            # Delete the submenu message
            if self.submenu_message:
                await self.submenu_message.delete()

            # Refresh the main panel
            if self.panel_message and self.user_permissions:
                await self.cog._refresh_panel(self.panel_message, self.user_permissions)

            # Acknowledge the interaction (message already deleted, so just send ephemeral confirmation)
            try:
                await interaction.response.send_message("Returned to main panel.", ephemeral=True, delete_after=2)
            except:
                # Interaction may already be responded to
                pass
        except Exception as e:
            logger.error(f"Error in back button: {e}", exc_info=True)


class LinkIDTypeSelect(discord.ui.Select):
    """Select menu for choosing Steam or Alderon ID to link."""

    def __init__(self, cog, submenu_message=None, panel_message=None, user_permissions=None):
        self.cog = cog
        self.submenu_message = submenu_message
        self.panel_message = panel_message
        self.user_permissions = user_permissions

        options = [
            discord.SelectOption(
                label="Steam ID",
                description="Link your Steam account",
                value="steam",
                emoji="🎮"
            ),
            discord.SelectOption(
                label="Alderon ID",
                description="Link your Alderon account (Path of Titans)",
                value="alderon",
                emoji="🦖"
            )
        ]

        super().__init__(
            placeholder="Select ID type to link...",
            options=options,
            row=0
        )

    async def callback(self, interaction: discord.Interaction):
        """Handle ID type selection."""
        selected = self.values[0]

        if selected == "steam":
            modal = LinkSteamModal(self.cog, self.submenu_message, self.panel_message, self.user_permissions)
            await interaction.response.send_modal(modal)
        elif selected == "alderon":
            modal = LinkAlderonModal(self.cog, self.submenu_message, self.panel_message, self.user_permissions)
            await interaction.response.send_modal(modal)


# ==========================================
# MODAL CLASSES
# ==========================================

class LinkAlderonModal(discord.ui.Modal, title="Link Alderon ID"):
    """Modal for linking Alderon ID."""

    player_id = discord.ui.TextInput(
        label="Alderon ID",
        placeholder="XXX-XXX-XXX (e.g., 123-456-789)",
        required=True,
        max_length=11
    )

    player_name = discord.ui.TextInput(
        label="In-Game Player Name",
        placeholder="Your player name in Path of Titans",
        required=True,
        max_length=50
    )

    def __init__(self, cog, submenu_message=None, panel_message=None, user_permissions=None):
        super().__init__()
        self.cog = cog
        self.submenu_message = submenu_message
        self.panel_message = panel_message
        self.user_permissions = user_permissions

    async def on_submit(self, interaction: discord.Interaction):
        """Handle modal submission."""
        # Call player service to link Alderon ID
        await player_service.link_alderon_id(interaction, self.player_id.value, self.player_name.value)

        # Delete submenu message and refresh main panel
        try:
            if self.submenu_message:
                await self.submenu_message.delete()
        except:
            pass

        if self.panel_message and self.user_permissions:
            await self.cog._refresh_panel(self.panel_message, self.user_permissions)

    async def on_error(self, interaction: discord.Interaction, error: Exception):
        """Handle modal errors (not called on user cancellation)."""
        logger.error(f"Link Alderon modal error: {error}", exc_info=True)


class LinkSteamModal(discord.ui.Modal, title="Link Steam ID"):
    """Modal for linking Steam ID."""

    steam_id = discord.ui.TextInput(
        label="Steam ID",
        placeholder="76561198XXXXXXXXX (17 digits) or profile URL",
        required=True,
        max_length=100
    )

    def __init__(self, cog, submenu_message=None, panel_message=None, user_permissions=None):
        super().__init__()
        self.cog = cog
        self.submenu_message = submenu_message
        self.panel_message = panel_message
        self.user_permissions = user_permissions

    async def on_submit(self, interaction: discord.Interaction):
        """Handle modal submission."""
        # Call player service to link Steam ID
        await player_service.link_steam_id(interaction, self.steam_id.value)

        # Delete submenu message and refresh main panel
        try:
            if self.submenu_message:
                await self.submenu_message.delete()
        except:
            pass

        if self.panel_message and self.user_permissions:
            await self.cog._refresh_panel(self.panel_message, self.user_permissions)

    async def on_error(self, interaction: discord.Interaction, error: Exception):
        """Handle modal errors (not called on user cancellation)."""
        logger.error(f"Link Steam modal error: {error}", exc_info=True)


class PlayerLookupModal(discord.ui.Modal, title="Look Up Player"):
    """Modal for looking up a player."""

    search_query = discord.ui.TextInput(
        label="Search Query",
        placeholder="Discord username, @mention, Steam ID, or Alderon ID",
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
        # Call player service to look up player
        await player_service.lookup_player(interaction, self.search_query.value)

        # Refresh the panel dropdown to allow reselection
        if self.panel_message and self.user_permissions:
            await self.cog._refresh_panel(self.panel_message, self.user_permissions)

    async def on_error(self, interaction: discord.Interaction, error: Exception):
        """Handle modal cancellation or error."""
        logger.error(f"Player lookup modal error: {error}", exc_info=True)
        # Refresh the panel dropdown to allow reselection
        if self.panel_message and self.user_permissions:
            try:
                await self.cog._refresh_panel(self.panel_message, self.user_permissions)
            except:
                pass


class UnlinkPlayerLookupModal(discord.ui.Modal, title="Unlink Player ID - Search"):
    """Step 1: Modal for searching a player to unlink."""

    search_query = discord.ui.TextInput(
        label="Player Search",
        placeholder="Discord username, @mention, Steam ID, or Alderon ID",
        required=True,
        max_length=100
    )

    def __init__(self, cog, panel_message=None, user_permissions=None):
        super().__init__()
        self.cog = cog
        self.panel_message = panel_message
        self.user_permissions = user_permissions

    async def on_submit(self, interaction: discord.Interaction):
        """Handle player search submission."""
        try:
            guild_id = interaction.guild_id
            query = self.search_query.value.strip()

            # Use same lookup logic as player lookup
            # Try to parse as Discord user
            user = None
            if query.startswith('<@') and query.endswith('>'):
                # Discord mention
                user_id = int(query[2:-1].replace('!', ''))
                try:
                    user = await interaction.client.fetch_user(user_id)
                except:
                    pass
            elif query.isdigit():
                # Discord ID
                try:
                    user = await interaction.client.fetch_user(int(query))
                except:
                    pass
            else:
                # Search guild members by username/display name
                guild = interaction.guild
                if guild:
                    query_lower = query.lower()
                    for member in guild.members:
                        # Check username, display name, and global name
                        if (member.name.lower() == query_lower or
                            member.display_name.lower() == query_lower or
                            (member.global_name and member.global_name.lower() == query_lower)):
                            user = member
                            break
                        # Also check for partial matches
                        if (query_lower in member.name.lower() or
                            query_lower in member.display_name.lower() or
                            (member.global_name and query_lower in member.global_name.lower())):
                            user = member
                            break

            # Search database
            player = None
            if user:
                player = PlayerQueries.get_by_user(guild_id, user.id)
            else:
                # Try as Steam ID or Alderon ID
                player = PlayerQueries.get_by_player_id(guild_id, query)

            if not player:
                await interaction.response.send_message(
                    f"❌ No player found matching: `{query}`",
                    ephemeral=True
                )
                # Refresh the panel dropdown to allow reselection
                if self.panel_message and self.user_permissions:
                    await self.cog._refresh_panel(self.panel_message, self.user_permissions)
                return

            # Get Discord user for display
            if player.get('user_id'):
                try:
                    discord_user = await interaction.client.fetch_user(player['user_id'])
                except:
                    discord_user = None
            else:
                discord_user = None

            # Build player info embed (similar to MyID)
            embed = discord.Embed(
                title="Unlink Player IDs",
                description="Review player information and select which IDs to unlink:",
                color=discord.Color.orange()
            )

            # Discord info
            if discord_user:
                embed.set_thumbnail(url=discord_user.display_avatar.url)
                embed.add_field(
                    name="Discord",
                    value=f"{discord_user.mention}\n**Username:** @{discord_user.name}\n**ID:** `{discord_user.id}`",
                    inline=False
                )

            # Steam info
            if player.get('steam_id'):
                steam_value = f"**Steam ID:** `{player['steam_id']}`"
                if player.get('steam_name'):
                    steam_value = f"**Steam Name:** {player['steam_name']}\n" + steam_value
                embed.add_field(
                    name="Steam (Linked)",
                    value=steam_value,
                    inline=False
                )
            else:
                embed.add_field(
                    name="Steam",
                    value="*Not linked*",
                    inline=False
                )

            # Alderon info
            if player.get('player_id'):
                embed.add_field(
                    name="Alderon (Linked)",
                    value=f"**Player Name:** {player.get('player_name', 'Unknown')}\n**Alderon ID:** `{player['player_id']}`",
                    inline=False
                )
            else:
                embed.add_field(
                    name="Alderon",
                    value="*Not linked*",
                    inline=False
                )

            embed.set_footer(text="Click a button below to unlink an ID")

            # Create view with unlink buttons
            view = UnlinkConfirmView(
                self.cog,
                player,
                discord_user,
                self.panel_message,
                self.user_permissions
            )

            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

        except Exception as e:
            logger.error(f"Error in unlink player lookup: {e}", exc_info=True)
            await interaction.response.send_message(
                "An error occurred while searching for the player.",
                ephemeral=True
            )

    async def on_error(self, interaction: discord.Interaction, error: Exception):
        """Handle modal cancellation or error."""
        logger.error(f"Unlink lookup modal error: {error}", exc_info=True)
        # Refresh the panel dropdown to allow reselection
        if self.panel_message and self.user_permissions:
            try:
                await self.cog._refresh_panel(self.panel_message, self.user_permissions)
            except:
                pass


class UnlinkConfirmView(discord.ui.View):
    """Step 2: View with buttons to confirm unlinking specific IDs."""

    def __init__(self, cog, player_data: dict, discord_user: discord.User, panel_message=None, user_permissions=None):
        super().__init__(timeout=300)
        self.cog = cog
        self.player_data = player_data
        self.discord_user = discord_user
        self.panel_message = panel_message
        self.user_permissions = user_permissions

        # Add buttons only for linked IDs
        if player_data.get('steam_id'):
            self.add_item(UnlinkSteamButton(cog, player_data, discord_user, panel_message, user_permissions))

        if player_data.get('player_id'):
            self.add_item(UnlinkAlderonButton(cog, player_data, discord_user, panel_message, user_permissions))

        # Add cancel button
        cancel_button = discord.ui.Button(
            label="Cancel",
            style=discord.ButtonStyle.gray,
            emoji="❌"
        )
        cancel_button.callback = self._cancel_callback
        self.add_item(cancel_button)

    async def _cancel_callback(self, interaction: discord.Interaction):
        """Handle cancel button click."""
        await interaction.response.send_message("Unlink operation cancelled.", ephemeral=True)
        # Refresh the panel dropdown
        if self.panel_message and self.user_permissions:
            await self.cog._refresh_panel(self.panel_message, self.user_permissions)


class UnlinkSteamButton(discord.ui.Button):
    """Button to unlink Steam ID."""

    def __init__(self, cog, player_data: dict, discord_user: discord.User, panel_message=None, user_permissions=None):
        super().__init__(
            label="Unlink Steam",
            style=discord.ButtonStyle.danger,
            emoji="🔓"
        )
        self.cog = cog
        self.player_data = player_data
        self.discord_user = discord_user
        self.panel_message = panel_message
        self.user_permissions = user_permissions

    async def callback(self, interaction: discord.Interaction):
        """Show confirmation modal before unlinking Steam ID."""
        modal = UnlinkSteamConfirmModal(
            self.cog,
            self.player_data,
            self.discord_user,
            self.panel_message,
            self.user_permissions
        )
        await interaction.response.send_modal(modal)


class UnlinkAlderonButton(discord.ui.Button):
    """Button to unlink Alderon ID."""

    def __init__(self, cog, player_data: dict, discord_user: discord.User, panel_message=None, user_permissions=None):
        super().__init__(
            label="Unlink Alderon",
            style=discord.ButtonStyle.danger,
            emoji="🔓"
        )
        self.cog = cog
        self.player_data = player_data
        self.discord_user = discord_user
        self.panel_message = panel_message
        self.user_permissions = user_permissions

    async def callback(self, interaction: discord.Interaction):
        """Show confirmation modal before unlinking Alderon ID."""
        modal = UnlinkAlderonConfirmModal(
            self.cog,
            self.player_data,
            self.discord_user,
            self.panel_message,
            self.user_permissions
        )
        await interaction.response.send_modal(modal)


class UnlinkSteamConfirmModal(discord.ui.Modal, title="Confirm Unlink Steam"):
    """Confirmation modal for unlinking Steam ID."""

    confirmation = discord.ui.TextInput(
        label='Type "CONFIRM" to unlink Steam ID',
        placeholder="CONFIRM",
        required=True,
        max_length=10
    )

    def __init__(self, cog, player_data: dict, discord_user: discord.User, panel_message=None, user_permissions=None):
        super().__init__()
        self.cog = cog
        self.player_data = player_data
        self.discord_user = discord_user
        self.panel_message = panel_message
        self.user_permissions = user_permissions

    async def on_submit(self, interaction: discord.Interaction):
        """Handle confirmation submission."""
        if self.confirmation.value.upper() != "CONFIRM":
            await interaction.response.send_message(
                "❌ Unlink cancelled. You must type CONFIRM to proceed.",
                ephemeral=True
            )
            return

        try:
            guild_id = interaction.guild_id
            user_id = self.player_data.get('user_id')

            if not user_id:
                await interaction.response.send_message("❌ Invalid player data.", ephemeral=True)
                return

            # Unlink Steam ID
            PlayerQueries.unlink_steam(guild_id, user_id)

            embed = discord.Embed(
                title="✅ Steam ID Unlinked",
                description=f"Steam ID unlinked for {self.discord_user.mention if self.discord_user else 'player'}",
                color=discord.Color.green()
            )
            embed.add_field(name="Unlinked by", value=interaction.user.mention, inline=True)
            embed.add_field(name="Steam ID", value=f"`{self.player_data.get('steam_id')}`", inline=True)

            await interaction.response.send_message(embed=embed, ephemeral=True)

            # Refresh the panel dropdown
            if self.panel_message and self.user_permissions:
                await self.cog._refresh_panel(self.panel_message, self.user_permissions)

        except Exception as e:
            logger.error(f"Error unlinking Steam ID: {e}", exc_info=True)
            await interaction.response.send_message(
                "An error occurred while unlinking Steam ID.",
                ephemeral=True
            )


class UnlinkAlderonConfirmModal(discord.ui.Modal, title="Confirm Unlink Alderon"):
    """Confirmation modal for unlinking Alderon ID."""

    confirmation = discord.ui.TextInput(
        label='Type "CONFIRM" to unlink Alderon ID',
        placeholder="CONFIRM",
        required=True,
        max_length=10
    )

    def __init__(self, cog, player_data: dict, discord_user: discord.User, panel_message=None, user_permissions=None):
        super().__init__()
        self.cog = cog
        self.player_data = player_data
        self.discord_user = discord_user
        self.panel_message = panel_message
        self.user_permissions = user_permissions

    async def on_submit(self, interaction: discord.Interaction):
        """Handle confirmation submission."""
        if self.confirmation.value.upper() != "CONFIRM":
            await interaction.response.send_message(
                "❌ Unlink cancelled. You must type CONFIRM to proceed.",
                ephemeral=True
            )
            return

        try:
            guild_id = interaction.guild_id
            user_id = self.player_data.get('user_id')

            if not user_id:
                await interaction.response.send_message("❌ Invalid player data.", ephemeral=True)
                return

            # Unlink Alderon ID
            PlayerQueries.unlink_alderon(guild_id, user_id)

            embed = discord.Embed(
                title="✅ Alderon ID Unlinked",
                description=f"Alderon ID unlinked for {self.discord_user.mention if self.discord_user else 'player'}",
                color=discord.Color.green()
            )
            embed.add_field(name="Unlinked by", value=interaction.user.mention, inline=True)
            embed.add_field(name="Alderon ID", value=f"`{self.player_data.get('player_id')}`", inline=True)

            await interaction.response.send_message(embed=embed, ephemeral=True)

            # Refresh the panel dropdown
            if self.panel_message and self.user_permissions:
                await self.cog._refresh_panel(self.panel_message, self.user_permissions)

        except Exception as e:
            logger.error(f"Error unlinking Alderon ID: {e}", exc_info=True)
            await interaction.response.send_message(
                "An error occurred while unlinking Alderon ID.",
                ephemeral=True
            )


async def setup(bot: commands.Bot):
    """Load the PlayerPanel cog."""
    await bot.add_cog(PlayerPanel(bot))
