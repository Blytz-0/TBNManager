# cogs/player/enforcement_panel.py
"""
Enforcement Panel - Unified strike and ban management interface

Provides a dropdown-based interface for:
- Strike management (add, view, remove, clear)
- Ban management (ban, unban, list)
- Strike history and recent activity
"""

import discord
from discord import app_commands
from discord.ext import commands
from database.queries import GuildQueries, StrikeQueries, AuditQueries
from services.permissions import require_permission, get_user_allowed_commands
from services import strikes_service
from services.enforcement_passport import (
    lookup_player_for_enforcement,
    format_player_identity_embed,
    get_primary_game_id
)
import logging

logger = logging.getLogger(__name__)


# ==========================================
# ENFORCEMENT ACTIONS DEFINITION
# ==========================================

ENFORCEMENT_ACTIONS = [
    # 1️⃣ Review / Awareness (read-only, low risk)
    ("View Strikes", "View active strikes for player", "inpanel_enforcement_viewstrikes", "📋"),
    ("Strike History", "View full strike history", "inpanel_enforcement_history", "📜"),
    ("Recent Strikes", "Server-wide recent strikes", "inpanel_enforcement_recent", "🕒"),
    ("Ban List", "List all banned players", "inpanel_enforcement_banlist", "📊"),

    # 2️⃣ Primary Actions (most common)
    ("Add Strike", "Issue a strike to a player", "inpanel_enforcement_addstrike", "⚠️"),
    ("Remove Strike", "Remove a specific strike", "inpanel_enforcement_remove", "❌"),

    # 3️⃣ Escalation Actions (higher impact)
    ("Ban Player", "Directly ban a player", "inpanel_enforcement_ban", "🔨"),
    ("Unban Player", "Unban a player", "inpanel_enforcement_unban", "✅"),

    # 4️⃣ Administrative / Destructive (danger zone)
    ("Clear Strikes", "Clear all active strikes", "inpanel_enforcement_clear", "🧹"),
    ("Wipe History", "Permanently delete records", "inpanel_enforcement_wipe", "🗑️"),
]


# ==========================================
# DROPDOWN-BASED ENFORCEMENT PANEL INTERFACE
# ==========================================

class EnforcementCommandSelect(discord.ui.Select):
    """Dropdown menu for selecting enforcement actions."""

    def __init__(self, cog, user_permissions: set, panel_message=None):
        self.cog = cog
        self.user_permissions = user_permissions
        self.panel_message = panel_message

        # Filter actions based on user permissions
        options = []
        for label, desc, permission, emoji in ENFORCEMENT_ACTIONS:
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
            placeholder="Choose an enforcement action...",
            options=options,
            row=0
        )

    async def callback(self, interaction: discord.Interaction):
        """Handle action selection."""
        selected = self.values[0]

        # Route to appropriate action handler, passing panel message for refresh (modal actions only)
        if selected == "inpanel_enforcement_addstrike":
            await self.cog._action_add_strike(interaction, self.panel_message, self.user_permissions)
        elif selected == "inpanel_enforcement_viewstrikes":
            await self.cog._action_view_strikes(interaction, self.panel_message, self.user_permissions)
        elif selected == "inpanel_enforcement_history":
            await self.cog._action_strike_history(interaction, self.panel_message, self.user_permissions)
        elif selected == "inpanel_enforcement_remove":
            await self.cog._action_remove_strike(interaction, self.panel_message, self.user_permissions)
        elif selected == "inpanel_enforcement_clear":
            await self.cog._action_clear_strikes(interaction, self.panel_message, self.user_permissions)
        elif selected == "inpanel_enforcement_ban":
            await self.cog._action_ban_player(interaction, self.panel_message, self.user_permissions)
        elif selected == "inpanel_enforcement_unban":
            await self.cog._action_unban_player(interaction, self.panel_message, self.user_permissions)
        elif selected == "inpanel_enforcement_banlist":
            await self.cog._action_ban_list(interaction, self.panel_message, self.user_permissions)
        elif selected == "inpanel_enforcement_wipe":
            await self.cog._action_wipe_history(interaction, self.panel_message, self.user_permissions)
        elif selected == "inpanel_enforcement_recent":
            await self.cog._action_recent_strikes(interaction, self.panel_message, self.user_permissions)


class EnforcementCommandView(discord.ui.View):
    """Main view with enforcement action dropdown."""

    def __init__(self, cog, user_permissions: set, panel_message=None):
        super().__init__(timeout=300)
        self.cog = cog
        self.panel_message = panel_message
        self.add_item(EnforcementCommandSelect(cog, user_permissions, panel_message))


# ==========================================
# MAIN PANEL COG
# ==========================================

class EnforcementPanel(commands.GroupCog, name="enforcement"):
    """Enforcement Panel - unified strike and ban management interface."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        super().__init__()

    @app_commands.command(name="panel", description="Open Enforcement control panel")
    @app_commands.guild_only()
    async def enforcement_panel(self, interaction: discord.Interaction):
        """Show the Enforcement control panel with dropdown selections."""
        # Check if strikes feature enabled
        if not GuildQueries.is_feature_enabled(interaction.guild_id, 'strikes'):
            await interaction.response.send_message(
                "Strike system is not enabled on this server.",
                ephemeral=True
            )
            return

        # Get user's allowed commands
        user_permissions = get_user_allowed_commands(interaction.guild_id, interaction.user)

        # Filter to only inpanel_enforcement_* permissions
        inpanel_permissions = {perm for perm in user_permissions if perm.startswith('inpanel_enforcement_')}

        # If user has no panel permissions, show error
        if not inpanel_permissions:
            await interaction.response.send_message(
                "You don't have permission to use any enforcement panel features.\n"
                "Contact an administrator to configure your permissions.",
                ephemeral=True
            )
            return

        embed = discord.Embed(
            title="⚖️ Enforcement Panel",
            description="Select an action from the dropdown below to manage strikes and bans.",
            color=discord.Color.red()
        )
        embed.set_footer(text="Select an action from the menu")

        # Send initial message without view
        await interaction.response.send_message(embed=embed, ephemeral=True)

        # Get the message object and create view with message reference for refresh capability
        panel_message = await interaction.original_response()
        view = EnforcementCommandView(self, inpanel_permissions, panel_message)

        # Edit message to add the view
        await panel_message.edit(view=view)

    @app_commands.command(name="help", description="Show Enforcement panel help")
    @app_commands.guild_only()
    async def enforcement_help(self, interaction: discord.Interaction):
        """Show help for Enforcement panel."""
        # Get user's allowed commands
        user_permissions = get_user_allowed_commands(interaction.guild_id, interaction.user)

        # Filter to only inpanel_enforcement_* permissions
        inpanel_permissions = {perm for perm in user_permissions if perm.startswith('inpanel_enforcement_')}

        # Build list of available actions
        available_actions = []
        for label, desc, permission, emoji in ENFORCEMENT_ACTIONS:
            if permission in inpanel_permissions:
                available_actions.append((label, desc))

        # Create help embed
        embed = discord.Embed(
            title="⚖️ Enforcement Panel Help",
            description="Strike and ban management commands.",
            color=discord.Color.red()
        )

        # Access instructions
        embed.add_field(
            name="Access Panel",
            value="`/enforcement panel` - Open the Enforcement panel\n"
                  "`/panel` → Select Enforcement - Via main launcher",
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

    async def _action_add_strike(self, interaction: discord.Interaction, panel_message=None, user_permissions=None):
        """Add strike - opens modal for input."""
        modal = AddStrikeModal(self, panel_message, user_permissions)
        await interaction.response.send_modal(modal)

    async def _action_view_strikes(self, interaction: discord.Interaction, panel_message=None, user_permissions=None):
        """View strikes - opens modal for Alderon ID input."""
        modal = ViewStrikesModal(self, panel_message, user_permissions)
        await interaction.response.send_modal(modal)

    async def _action_strike_history(self, interaction: discord.Interaction, panel_message=None, user_permissions=None):
        """Strike history - opens modal for user selection."""
        modal = StrikeHistoryModal(self, panel_message, user_permissions)
        await interaction.response.send_modal(modal)

    async def _action_remove_strike(self, interaction: discord.Interaction, panel_message=None, user_permissions=None):
        """Remove strike - opens modal for strike ID input."""
        modal = RemoveStrikeModal(self, panel_message, user_permissions)
        await interaction.response.send_modal(modal)

    async def _action_clear_strikes(self, interaction: discord.Interaction, panel_message=None, user_permissions=None):
        """Clear strikes - opens modal for Alderon ID input."""
        modal = ClearStrikesModal(self, panel_message, user_permissions)
        await interaction.response.send_modal(modal)

    async def _action_ban_player(self, interaction: discord.Interaction, panel_message=None, user_permissions=None):
        """Ban player - opens modal for ban input."""
        modal = BanPlayerModal(self, panel_message, user_permissions)
        await interaction.response.send_modal(modal)

    async def _action_unban_player(self, interaction: discord.Interaction, panel_message=None, user_permissions=None):
        """Unban player - opens modal for user selection."""
        modal = UnbanPlayerModal(self, panel_message, user_permissions)
        await interaction.response.send_modal(modal)

    async def _action_ban_list(self, interaction: discord.Interaction, panel_message=None, user_permissions=None):
        """Show ban list - immediate action."""
        # Use shared service (independent of StrikeCommands cog)
        await strikes_service.list_bans(interaction, show_unbanned=False)

        # Refresh the panel dropdown to allow reselection
        if panel_message and user_permissions:
            await self._refresh_panel(panel_message, user_permissions)

    async def _action_wipe_history(self, interaction: discord.Interaction, panel_message=None, user_permissions=None):
        """Wipe history - opens modal for user selection."""
        modal = WipeHistoryModal(self, panel_message, user_permissions)
        await interaction.response.send_modal(modal)

    async def _action_recent_strikes(self, interaction: discord.Interaction, panel_message=None, user_permissions=None):
        """Show recent strikes - immediate action."""
        # Use shared service (independent of StrikeCommands cog)
        await strikes_service.recent_strikes(interaction)

        # Refresh the panel dropdown to allow reselection
        if panel_message and user_permissions:
            await self._refresh_panel(panel_message, user_permissions)

    async def _refresh_panel(self, panel_message, user_permissions: set):
        """Refresh the panel dropdown by recreating the view."""
        try:
            embed = discord.Embed(
                title="⚖️ Enforcement Panel",
                description="Select an action from the dropdown below to manage strikes and bans.",
                color=discord.Color.red()
            )
            embed.set_footer(text="Select an action from the menu")

            # Create fresh view with reset dropdown
            view = EnforcementCommandView(self, user_permissions, panel_message)

            # Edit the panel message to refresh the dropdown
            await panel_message.edit(embed=embed, view=view)
        except Exception as e:
            logger.error(f"Error refreshing enforcement panel: {e}", exc_info=True)


# ==========================================
# MODAL CLASSES
# ==========================================

class AddStrikeModal(discord.ui.Modal, title="Add Strike - Step 1: Player Search"):
    """Modal for searching player and entering reason."""

    player_search = discord.ui.TextInput(
        label="Player Search",
        placeholder="Discord username, @mention, Steam ID, or Alderon ID",
        required=True,
        max_length=100
    )

    reason = discord.ui.TextInput(
        label="Reason for Strike",
        placeholder="Describe the rule violation...",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=500
    )

    def __init__(self, cog, panel_message=None, user_permissions=None):
        super().__init__()
        self.cog = cog
        self.panel_message = panel_message
        self.user_permissions = user_permissions

    async def on_submit(self, interaction: discord.Interaction):
        """Handle modal submission - lookup player and show category/severity selection."""
        await interaction.response.defer(ephemeral=True)

        # Look up player using passport system
        from services import enforcement_passport
        lookup_result = await enforcement_passport.lookup_player_for_enforcement(
            interaction,
            self.player_search.value.strip()
        )

        if not lookup_result['success']:
            await interaction.followup.send(
                lookup_result['error'],
                ephemeral=True
            )
            # Refresh panel
            if self.panel_message and self.user_permissions:
                await self.cog._refresh_panel(self.panel_message, self.user_permissions)
            return

        # Show player identity with category/severity dropdowns
        embed = enforcement_passport.format_player_identity_embed(lookup_result)
        embed.title = "⚠️ Add Strike - Step 2: Select Category & Severity"
        embed.description = "Player found! Now select the violation category and severity:"
        embed.add_field(
            name="Reason",
            value=self.reason.value,
            inline=False
        )
        embed.color = discord.Color.orange()

        view = AddStrikeCategoryView(
            self.cog,
            lookup_result,
            self.reason.value,
            interaction.user,
            self.panel_message,
            self.user_permissions
        )

        await interaction.followup.send(embed=embed, view=view, ephemeral=True)


class AddStrikeCategoryView(discord.ui.View):
    """View for selecting strike category and severity with dropdowns."""

    def __init__(self, cog, lookup_result: dict, reason: str, issued_by: discord.User,
                 panel_message=None, user_permissions=None):
        super().__init__(timeout=300)
        self.cog = cog
        self.lookup_result = lookup_result
        self.reason = reason
        self.issued_by = issued_by
        self.panel_message = panel_message
        self.user_permissions = user_permissions

        # Add category dropdown
        self.add_item(CategorySelect())
        # Add severity dropdown
        self.add_item(SeveritySelect())

    def get_selected_values(self):
        """Get currently selected category and severity."""
        category = 'other'
        severity = 'minor'
        for item in self.children:
            if isinstance(item, CategorySelect) and item.values:
                category = item.values[0]
            elif isinstance(item, SeveritySelect) and item.values:
                severity = item.values[0]
        return category, severity

    @discord.ui.button(label="Continue", style=discord.ButtonStyle.primary, row=2)
    async def continue_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Show confirmation after selections are made."""
        category, severity = self.get_selected_values()

        # Show confirmation embed
        from services import enforcement_passport
        embed = enforcement_passport.format_player_identity_embed(self.lookup_result)
        embed.title = "⚠️ Confirm Strike"
        embed.description = "You are about to issue a strike to this player:"
        embed.add_field(
            name="Strike Details",
            value=f"**Category:** {category.replace('_', ' ').title()}\n"
                  f"**Severity:** {severity.title()}\n"
                  f"**Reason:** {self.reason}",
            inline=False
        )
        embed.color = discord.Color.red()

        confirm_view = AddStrikeConfirmView(
            self.cog,
            self.lookup_result,
            category,
            severity,
            self.reason,
            self.issued_by,
            self.panel_message,
            self.user_permissions
        )

        await interaction.response.edit_message(embed=embed, view=confirm_view)


class CategorySelect(discord.ui.Select):
    """Dropdown for selecting strike category."""

    def __init__(self):
        options = [
            discord.SelectOption(label="Harassment", value="harassment", emoji="😠", description="Bullying, targeting, or harassing other players"),
            discord.SelectOption(label="Hate Speech", value="hate_speech", emoji="🚫", description="Discriminatory or hateful language"),
            discord.SelectOption(label="Cheating", value="cheating", emoji="🎯", description="Using exploits, hacks, or cheats"),
            discord.SelectOption(label="Griefing", value="griefing", emoji="💥", description="Intentionally ruining others' experience"),
            discord.SelectOption(label="Toxicity", value="toxicity", emoji="☠️", description="Toxic behavior or poor sportsmanship"),
            discord.SelectOption(label="Other", value="other", emoji="📋", description="Other rule violation", default=True),
        ]

        super().__init__(
            placeholder="Select violation category...",
            options=options,
            row=0
        )

    async def callback(self, interaction: discord.Interaction):
        """Handle category selection."""
        # Just acknowledge the selection
        await interaction.response.defer()


class SeveritySelect(discord.ui.Select):
    """Dropdown for selecting strike severity."""

    def __init__(self):
        options = [
            discord.SelectOption(label="Minor", value="minor", emoji="⚠️", description="Warning - First offense or minor violation", default=True),
            discord.SelectOption(label="Major", value="major", emoji="🔴", description="Serious - Repeated or severe violation"),
        ]

        super().__init__(
            placeholder="Select severity level...",
            options=options,
            row=1
        )

    async def callback(self, interaction: discord.Interaction):
        """Handle severity selection."""
        # Just acknowledge the selection
        await interaction.response.defer()


class AddStrikeConfirmView(discord.ui.View):
    """Final confirmation view for adding a strike."""

    def __init__(self, cog, lookup_result: dict, category: str, severity: str,
                 reason: str, issued_by: discord.User, panel_message=None, user_permissions=None):
        super().__init__(timeout=300)
        self.cog = cog
        self.lookup_result = lookup_result
        self.category = category
        self.severity = severity
        self.reason = reason
        self.issued_by = issued_by
        self.panel_message = panel_message
        self.user_permissions = user_permissions

    @discord.ui.button(label="✅ Confirm Strike", style=discord.ButtonStyle.danger)
    async def confirm_strike(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Confirm and issue the strike."""
        await interaction.response.defer()

        # Delete the confirmation message immediately to avoid clutter
        try:
            await interaction.message.delete()
        except:
            pass

        try:
            guild_id = interaction.guild_id
            user_id = self.lookup_result['user_id']
            player_name = self.lookup_result['player_name']

            # Get primary game ID for backward compatibility
            from services import enforcement_passport
            in_game_id, source_id = enforcement_passport.get_primary_game_id(self.lookup_result)

            if not in_game_id:
                await interaction.followup.send(
                    "❌ Error: Could not determine game ID. Player must have at least one linked ID.",
                    ephemeral=True
                )
                return

            # Check if player is already banned
            if StrikeQueries.is_banned(guild_id, in_game_id):
                await interaction.followup.send(
                    f"❌ **{player_name}** is already banned and cannot receive more strikes.",
                    ephemeral=True
                )
                return

            # Add the strike with new passport fields
            strike = StrikeQueries.add_strike(
                guild_id=guild_id,
                player_name=player_name,
                in_game_id=in_game_id,
                reason=self.reason,
                admin_id=self.issued_by.id,
                admin_name=str(self.issued_by),
                user_id=user_id
                # Note: source_type, source_id, category, severity will be added in next update
            )

            strike_number = strike['strike_number']

            # Log to audit
            AuditQueries.log(
                guild_id=guild_id,
                action_type=AuditQueries.ACTION_STRIKE_ADDED,
                performed_by_id=self.issued_by.id,
                performed_by_name=str(self.issued_by),
                target_user_id=user_id,
                target_player_name=player_name,
                details={
                    'in_game_id': in_game_id,
                    'reason': self.reason,
                    'strike_number': strike_number,
                    'category': self.category,
                    'severity': self.severity,
                    'source_type': 'manual',
                    'source_id': source_id
                }
            )

            # Create response embed
            if strike_number == 1:
                color = discord.Color.yellow()
                title = "1st Strike Issued"
            elif strike_number == 2:
                color = discord.Color.orange()
                title = "2nd Strike Issued"
            else:
                color = discord.Color.red()
                title = f"Strike #{strike_number} Issued"

            import time
            now_timestamp = int(time.time())

            embed = discord.Embed(title=title, color=color)
            embed.add_field(name="Player", value=player_name, inline=True)
            embed.add_field(name="Strike #", value=str(strike_number), inline=True)
            embed.add_field(name="Issued", value=f"<t:{now_timestamp}:F>", inline=False)
            embed.add_field(name="Category", value=self.category.replace('_', ' ').title(), inline=True)
            embed.add_field(name="Severity", value=self.severity.title(), inline=True)
            embed.add_field(name="Reason", value=self.reason, inline=False)
            embed.add_field(name="Issued By", value=self.issued_by.mention, inline=True)

            # Show all linked IDs
            ids_text = []
            if self.lookup_result.get('user_id'):
                ids_text.append(f"**Discord:** `{self.lookup_result['user_id']}`")
            if self.lookup_result.get('steam_id'):
                ids_text.append(f"**Steam:** `{self.lookup_result['steam_id']}`")
            if self.lookup_result.get('alderon_id'):
                ids_text.append(f"**Alderon:** `{self.lookup_result['alderon_id']}`")           
            
            if ids_text:
                embed.add_field(name="Linked Accounts", value="\n".join(ids_text), inline=False)

            if strike.get('reference_id'):
                embed.add_field(name="Reference ID", value=f"`{strike['reference_id']}`", inline=True)

            embed.set_footer(text="Strikes expire after 30 days each • Global enforcement active")

            await interaction.followup.send(embed=embed, ephemeral=True)

            # Check if auto-ban needed (3rd strike)
            auto_ban_needed = (
                strike_number >= 3 and
                GuildQueries.is_feature_enabled(guild_id, 'auto_ban')
            )

            if auto_ban_needed:
                await interaction.followup.send(
                    f"⚠️ **{player_name}** has reached 3 strikes and needs to be banned!",
                    ephemeral=True
                )

            # DM the user if linked and feature enabled
            if user_id and GuildQueries.is_feature_enabled(guild_id, 'dm_notifications'):
                await strikes_service.send_strike_notification(
                    interaction.guild, user_id, strike_number, self.reason,
                    admin_name=str(self.issued_by), in_game_id=in_game_id,
                    reference_id=strike.get('reference_id'),
                    steam_id=self.lookup_result.get('steam_id'),
                    alderon_id=self.lookup_result.get('alderon_id')
                )

            # Log to strikes channel if configured
            from database.queries import LogChannelQueries
            strikes_channel_id = LogChannelQueries.get_strikes_channel(guild_id)
            if strikes_channel_id:
                try:
                    strikes_channel = interaction.guild.get_channel(strikes_channel_id)
                    if strikes_channel:
                        # Create a copy of the embed for logging
                        log_embed = discord.Embed(title=title, color=color)
                        log_embed.add_field(name="Player", value=player_name, inline=True)
                        log_embed.add_field(name="Strike #", value=str(strike_number), inline=True)
                        log_embed.add_field(name="Issued", value=f"<t:{now_timestamp}:F>", inline=False)
                        log_embed.add_field(name="Category", value=self.category.replace('_', ' ').title(), inline=True)
                        log_embed.add_field(name="Severity", value=self.severity.title(), inline=True)
                        log_embed.add_field(name="Reason", value=self.reason, inline=False)
                        log_embed.add_field(name="Issued By", value=self.issued_by.mention, inline=True)

                        # Show all linked IDs
                        ids_text = []
                        if self.lookup_result.get('alderon_id'):
                            ids_text.append(f"**Alderon:** `{self.lookup_result['alderon_id']}`")
                        if self.lookup_result.get('steam_id'):
                            ids_text.append(f"**Steam:** `{self.lookup_result['steam_id']}`")
                        if self.lookup_result.get('user_id'):
                            ids_text.append(f"**Discord:** `{self.lookup_result['user_id']}`")
                        if ids_text:
                            log_embed.add_field(name="Linked Accounts", value="\n".join(ids_text), inline=False)

                        if strike.get('reference_id'):
                            log_embed.add_field(name="Reference ID", value=f"`{strike['reference_id']}`", inline=True)

                        log_embed.set_footer(text="Strikes expire after 30 days each • Global enforcement active")

                        await strikes_channel.send(embed=log_embed)
                except Exception as e:
                    logger.error(f"Error logging strike to channel: {e}", exc_info=True)

        except Exception as e:
            logger.error(f"Error issuing strike: {e}", exc_info=True)
            await interaction.followup.send(
                "❌ An error occurred while issuing the strike. Please try again.",
                ephemeral=True
            )

        # Refresh the panel dropdown
        if self.panel_message and self.user_permissions:
            await self.cog._refresh_panel(self.panel_message, self.user_permissions)

    @discord.ui.button(label="❌ Cancel", style=discord.ButtonStyle.secondary)
    async def cancel_strike(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Cancel the strike and clean up."""
        # Delete this confirmation message
        try:
            await interaction.message.delete()
        except:
            pass

        # Send ephemeral confirmation
        await interaction.response.send_message(
            "❌ Strike cancelled. No action taken.",
            ephemeral=True,
            delete_after=3
        )

        # Refresh the panel dropdown
        if self.panel_message and self.user_permissions:
            await self.cog._refresh_panel(self.panel_message, self.user_permissions)


class ViewStrikesModal(discord.ui.Modal, title="View Strikes"):
    """Modal for viewing strikes."""

    player_search = discord.ui.TextInput(
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
        """Handle modal submission."""
        await interaction.response.defer(ephemeral=True)

        # Look up player using passport system
        query = self.player_search.value.strip()
        lookup_result = await lookup_player_for_enforcement(interaction, query)

        if not lookup_result['success']:
            await interaction.followup.send(lookup_result['error'], ephemeral=True)
            if self.panel_message and self.user_permissions:
                await self.cog._refresh_panel(self.panel_message, self.user_permissions)
            return

        # Get primary game ID for backward compatibility
        in_game_id, source_type = get_primary_game_id(lookup_result)

        if not in_game_id:
            await interaction.followup.send(
                "❌ No valid game ID found for this player. Make sure they have linked their accounts.",
                ephemeral=True
            )
            if self.panel_message and self.user_permissions:
                await self.cog._refresh_panel(self.panel_message, self.user_permissions)
            return

        # Use shared service (independent of StrikeCommands cog)
        await strikes_service.view_strikes(interaction, in_game_id)

        # Refresh the panel dropdown to allow reselection
        if self.panel_message and self.user_permissions:
            await self.cog._refresh_panel(self.panel_message, self.user_permissions)


class StrikeHistoryModal(discord.ui.Modal, title="View Strike History"):
    """Modal for viewing strike history."""

    player_search = discord.ui.TextInput(
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
        """Handle modal submission."""
        await interaction.response.defer(ephemeral=True)

        # Look up player using passport system
        query = self.player_search.value.strip()
        lookup_result = await lookup_player_for_enforcement(interaction, query)

        if not lookup_result['success']:
            await interaction.followup.send(lookup_result['error'], ephemeral=True)
            if self.panel_message and self.user_permissions:
                await self.cog._refresh_panel(self.panel_message, self.user_permissions)
            return

        # Get primary game ID for backward compatibility
        in_game_id, source_type = get_primary_game_id(lookup_result)

        if not in_game_id:
            await interaction.followup.send(
                "❌ No valid game ID found for this player. Make sure they have linked their accounts.",
                ephemeral=True
            )
            if self.panel_message and self.user_permissions:
                await self.cog._refresh_panel(self.panel_message, self.user_permissions)
            return

        # Use shared service (independent of StrikeCommands cog)
        await strikes_service.strike_history(interaction, in_game_id)

        # Refresh the panel dropdown to allow reselection
        if self.panel_message and self.user_permissions:
            await self.cog._refresh_panel(self.panel_message, self.user_permissions)


class RemoveStrikeModal(discord.ui.Modal, title="Remove Strike"):
    """Modal for removing a strike."""

    player_search = discord.ui.TextInput(
        label="Player Search",
        placeholder="Discord username, @mention, Steam ID, or Alderon ID",
        required=True,
        max_length=100
    )

    strike_number = discord.ui.TextInput(
        label="Strike Number (optional)",
        placeholder="Leave blank to remove most recent",
        required=False,
        max_length=2
    )

    def __init__(self, cog, panel_message=None, user_permissions=None):
        super().__init__()
        self.cog = cog
        self.panel_message = panel_message
        self.user_permissions = user_permissions

    async def on_submit(self, interaction: discord.Interaction):
        """Handle modal submission."""
        await interaction.response.defer(ephemeral=True)

        # Parse strike number if provided
        strike_num = None
        if self.strike_number.value.strip():
            try:
                strike_num = int(self.strike_number.value.strip())
            except:
                await interaction.followup.send("❌ Invalid strike number.", ephemeral=True)
                if self.panel_message and self.user_permissions:
                    await self.cog._refresh_panel(self.panel_message, self.user_permissions)
                return

        # Look up player using passport system
        query = self.player_search.value.strip()
        lookup_result = await lookup_player_for_enforcement(interaction, query)

        if not lookup_result['success']:
            await interaction.followup.send(lookup_result['error'], ephemeral=True)
            if self.panel_message and self.user_permissions:
                await self.cog._refresh_panel(self.panel_message, self.user_permissions)
            return

        # Get primary game ID for backward compatibility
        in_game_id, source_type = get_primary_game_id(lookup_result)

        if not in_game_id:
            await interaction.followup.send(
                "❌ No valid game ID found for this player. Make sure they have linked their accounts.",
                ephemeral=True
            )
            if self.panel_message and self.user_permissions:
                await self.cog._refresh_panel(self.panel_message, self.user_permissions)
            return

        # Use shared service (independent of StrikeCommands cog)
        await strikes_service.remove_strike(
            interaction,
            in_game_id,
            strike_num
        )

        # Refresh the panel dropdown to allow reselection
        if self.panel_message and self.user_permissions:
            await self.cog._refresh_panel(self.panel_message, self.user_permissions)


class ClearStrikesModal(discord.ui.Modal, title="Clear All Strikes"):
    """Modal for clearing strikes."""

    player_search = discord.ui.TextInput(
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
        """Handle modal submission."""
        await interaction.response.defer(ephemeral=True)

        # Look up player using passport system
        query = self.player_search.value.strip()
        lookup_result = await lookup_player_for_enforcement(interaction, query)

        if not lookup_result['success']:
            await interaction.followup.send(lookup_result['error'], ephemeral=True)
            if self.panel_message and self.user_permissions:
                await self.cog._refresh_panel(self.panel_message, self.user_permissions)
            return

        # Get primary game ID for backward compatibility
        in_game_id, source_type = get_primary_game_id(lookup_result)

        if not in_game_id:
            await interaction.followup.send(
                "❌ No valid game ID found for this player. Make sure they have linked their accounts.",
                ephemeral=True
            )
            if self.panel_message and self.user_permissions:
                await self.cog._refresh_panel(self.panel_message, self.user_permissions)
            return

        # Use shared service (independent of StrikeCommands cog)
        await strikes_service.clear_strikes(interaction, in_game_id)

        # Refresh the panel dropdown to allow reselection
        if self.panel_message and self.user_permissions:
            await self.cog._refresh_panel(self.panel_message, self.user_permissions)


class BanPlayerModal(discord.ui.Modal, title="Direct Ban - Step 1: Player Search"):
    """Modal for directly banning a player."""

    player_search = discord.ui.TextInput(
        label="Player Search",
        placeholder="Discord username, @mention, Steam ID, or Alderon ID",
        required=True,
        max_length=100
    )

    reason = discord.ui.TextInput(
        label="Reason for Ban",
        placeholder="Describe why this player is being banned...",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=500
    )

    def __init__(self, cog, panel_message=None, user_permissions=None):
        super().__init__()
        self.cog = cog
        self.panel_message = panel_message
        self.user_permissions = user_permissions

    async def on_submit(self, interaction: discord.Interaction):
        """Handle modal submission."""
        await interaction.response.defer(ephemeral=True)

        # Look up player using passport system
        query = self.player_search.value.strip()
        lookup_result = await lookup_player_for_enforcement(interaction, query)

        if not lookup_result['success']:
            await interaction.followup.send(lookup_result['error'], ephemeral=True)
            if self.panel_message and self.user_permissions:
                await self.cog._refresh_panel(self.panel_message, self.user_permissions)
            return

        # Get primary game ID for backward compatibility
        in_game_id, source_type = get_primary_game_id(lookup_result)
        player_name = lookup_result['player_name']
        user_id = lookup_result.get('user_id')

        if not in_game_id:
            await interaction.followup.send(
                "❌ No valid game ID found for this player. Make sure they have linked their accounts.",
                ephemeral=True
            )
            if self.panel_message and self.user_permissions:
                await self.cog._refresh_panel(self.panel_message, self.user_permissions)
            return

        guild_id = interaction.guild_id
        reason = self.reason.value

        # Check eligibility using shared service (independent of StrikeCommands cog)
        can_ban, error_msg, _ = strikes_service.check_direct_ban_eligibility(
            guild_id, in_game_id, player_name
        )

        if not can_ban:
            await interaction.followup.send(error_msg, ephemeral=True)
            if self.panel_message and self.user_permissions:
                await self.cog._refresh_panel(self.panel_message, self.user_permissions)
            return

        # Show player identity confirmation
        identity_embed = format_player_identity_embed(lookup_result)
        identity_embed.title = "Confirm Ban - Player Identity"
        identity_embed.color = discord.Color.red()

        # Show confirmation view for in-game ban status
        view = DirectBanConfirmView(
            cog=self.cog,
            guild_id=guild_id,
            player_name=player_name,
            in_game_id=in_game_id,
            reason=reason,
            banned_by=interaction.user,
            user_id=user_id,
            lookup_result=lookup_result,
            panel_message=self.panel_message,
            user_permissions=self.user_permissions
        )

        await interaction.followup.send(
            f"Ban **{player_name}**?\n"
            f"**Reason:** {reason}\n\n"
            f"Has this player been banned in-game?",
            embed=identity_embed,
            view=view
        )


class UnbanPlayerModal(discord.ui.Modal, title="Unban Player"):
    """Modal for unbanning a player."""

    player_search = discord.ui.TextInput(
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
        """Handle modal submission."""
        await interaction.response.defer(ephemeral=True)

        # Look up player using passport system
        query = self.player_search.value.strip()
        lookup_result = await lookup_player_for_enforcement(interaction, query)

        if not lookup_result['success']:
            await interaction.followup.send(lookup_result['error'], ephemeral=True)
            if self.panel_message and self.user_permissions:
                await self.cog._refresh_panel(self.panel_message, self.user_permissions)
            return

        # Get primary game ID for backward compatibility
        in_game_id, source_type = get_primary_game_id(lookup_result)

        if not in_game_id:
            await interaction.followup.send(
                "❌ No valid game ID found for this player. Make sure they have linked their accounts.",
                ephemeral=True
            )
            if self.panel_message and self.user_permissions:
                await self.cog._refresh_panel(self.panel_message, self.user_permissions)
            return

        # Use shared service (independent of StrikeCommands cog)
        await strikes_service.unban_player(interaction, in_game_id)

        # Refresh the panel dropdown to allow reselection
        if self.panel_message and self.user_permissions:
            await self.cog._refresh_panel(self.panel_message, self.user_permissions)


class WipeHistoryModal(discord.ui.Modal, title="Wipe History (Permanent)"):
    """Modal for wiping history."""

    player_search = discord.ui.TextInput(
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
        """Handle modal submission."""
        await interaction.response.defer(ephemeral=True)

        # Look up player using passport system
        query = self.player_search.value.strip()
        lookup_result = await lookup_player_for_enforcement(interaction, query)

        if not lookup_result['success']:
            await interaction.followup.send(lookup_result['error'], ephemeral=True)
            if self.panel_message and self.user_permissions:
                await self.cog._refresh_panel(self.panel_message, self.user_permissions)
            return

        # Get primary game ID for backward compatibility
        in_game_id, source_type = get_primary_game_id(lookup_result)

        if not in_game_id:
            await interaction.followup.send(
                "❌ No valid game ID found for this player. Make sure they have linked their accounts.",
                ephemeral=True
            )
            if self.panel_message and self.user_permissions:
                await self.cog._refresh_panel(self.panel_message, self.user_permissions)
            return

        # Use shared service (independent of StrikeCommands cog)
        await strikes_service.wipe_history(interaction, in_game_id)

        # Refresh the panel dropdown to allow reselection
        if self.panel_message and self.user_permissions:
            await self.cog._refresh_panel(self.panel_message, self.user_permissions)


class DirectBanConfirmView(discord.ui.View):
    """Confirmation view for direct ban in-game status."""

    def __init__(self, cog, guild_id: int, player_name: str, in_game_id: str,
                 reason: str, banned_by: discord.User, user_id: int | None,
                 lookup_result: dict = None,
                 panel_message=None, user_permissions=None):
        super().__init__(timeout=300)
        self.cog = cog
        self.guild_id = guild_id
        self.player_name = player_name
        self.in_game_id = in_game_id
        self.reason = reason
        self.banned_by = banned_by
        self.user_id = user_id
        self.lookup_result = lookup_result or {}
        self.panel_message = panel_message
        self.user_permissions = user_permissions

    async def _complete_ban(self, interaction: discord.Interaction, banned_in_game: bool):
        """Complete the ban process."""
        # Add the ban
        ban = StrikeQueries.add_ban(
            guild_id=self.guild_id,
            player_name=self.player_name,
            in_game_id=self.in_game_id,
            reason=self.reason,
            banned_by_id=self.banned_by.id,
            banned_by_name=str(self.banned_by),
            user_id=self.user_id,
            banned_in_game=banned_in_game
        )

        # Log to audit
        AuditQueries.log(
            guild_id=self.guild_id,
            action_type=AuditQueries.ACTION_BAN,
            performed_by_id=self.banned_by.id,
            performed_by_name=str(self.banned_by),
            target_user_id=self.user_id,
            target_player_name=self.player_name,
            details={
                'in_game_id': self.in_game_id,
                'reason': self.reason,
                'in_game': banned_in_game,
                'direct_ban': True
            }
        )

        # Create response embed
        embed = discord.Embed(
            title="Player Banned",
            color=discord.Color.dark_red()
        )
        embed.add_field(name="Player", value=self.player_name, inline=True)
        embed.add_field(name="Alderon ID", value=f"`{self.in_game_id}`", inline=True)
        embed.add_field(name="In-Game Ban", value="Yes" if banned_in_game else "Pending", inline=True)
        embed.add_field(name="Reason", value=self.reason, inline=False)
        embed.add_field(name="Banned By", value=self.banned_by.mention, inline=True)

        if ban.get('reference_id'):
            embed.add_field(name="Reference ID", value=f"`{ban['reference_id']}`", inline=True)

        embed.set_footer(text="Direct ban - no strikes required")

        await interaction.response.edit_message(content=None, embed=embed, view=None)

        # DM the user if linked and feature enabled
        if self.user_id and GuildQueries.is_feature_enabled(self.guild_id, 'dm_notifications'):
            await strikes_service.send_direct_ban_notification(
                interaction.guild, self.user_id, self.player_name, self.in_game_id,
                self.reason, str(self.banned_by), ban.get('reference_id')
            )

        # Refresh the panel dropdown to allow reselection
        if self.panel_message and self.user_permissions:
            await self.cog._refresh_panel(self.panel_message, self.user_permissions)

    @discord.ui.button(label="Yes, banned in-game", style=discord.ButtonStyle.danger)
    async def confirm_in_game(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._complete_ban(interaction, banned_in_game=True)

    @discord.ui.button(label="Not yet", style=discord.ButtonStyle.secondary)
    async def pending_in_game(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._complete_ban(interaction, banned_in_game=False)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel_ban(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="Ban cancelled.", view=None)

        # Refresh the panel dropdown to allow reselection
        if self.panel_message and self.user_permissions:
            await self.cog._refresh_panel(self.panel_message, self.user_permissions)


async def setup(bot: commands.Bot):
    """Load the EnforcementPanel cog."""
    await bot.add_cog(EnforcementPanel(bot))
