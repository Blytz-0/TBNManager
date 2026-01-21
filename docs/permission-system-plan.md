# Permission System Implementation Plan

> **Created:** 2026-01-21
> **Status:** Planning phase - ready for implementation
> **Context:** This document captures the design discussion for a granular role-based permission system.

---

## Overview

Replace the current level-based permission system (Level 1-3) with a granular per-command permission system where server owners can configure exactly which commands each Discord role can access.

## Key Design Decisions

1. **Whitelist approach** - New roles have no permissions until configured
2. **Server owner always has full access** - Cannot be restricted
3. **INI-style configuration** - Edit permissions via text in a modal
4. **Dynamic /help** - Only shows commands the user can access
5. **Feature toggles hide commands** - If a feature is disabled, related commands are hidden even from /help

---

## All Commands (37 total)

### Player Commands (3)
| Command | Description |
|---------|-------------|
| `alderonid` | Link Discord to Alderon ID |
| `playerid` | Look up player info |
| `myid` | View your linked ID |

### Strike & Ban Commands (10)
| Command | Description |
|---------|-------------|
| `addstrike` | Add a strike to a player |
| `strikes` | View active strikes |
| `strikehistory` | View full strike history |
| `removestrike` | Remove a specific strike |
| `clearstrikes` | Clear all active strikes |
| `ban` | Directly ban a player |
| `unban` | Unban a player |
| `bans` | List all banned players |
| `wipehistory` | Permanently delete all records |
| `recentstrikes` | View recent strikes server-wide |

### Ticket Commands (9)
| Command | Description |
|---------|-------------|
| `ticketpanel` | Create a new ticket panel |
| `addbutton` | Add a button to a ticket panel |
| `refreshpanel` | Refresh a panel after changes |
| `listpanels` | List all ticket panels |
| `tickets` | View all open tickets |
| `close` | Close current ticket |
| `claim` | Claim a ticket |
| `adduser` | Add user to ticket |
| `removeuser` | Remove user from ticket |

### Moderation Commands (6)
| Command | Description |
|---------|-------------|
| `announce` | Send announcement |
| `say` | Send message as bot |
| `clear` | Delete messages |
| `rolepanel` | Create role selection panel |
| `serverinfo` | View server info |
| `userinfo` | View user info |

### Configuration Commands (6)
| Command | Description |
|---------|-------------|
| `setup` | View bot configuration |
| `roleperms` | Edit role permissions (NEW) |
| `setchannel` | Set channel for logs/announcements |
| `feature` | Enable/disable bot features |
| `help` | List available commands |

**Note:** `setadminrole`, `removeadminrole`, and `adminroles` will be deprecated/removed once the new system is in place.

---

## User Flow

### Step 1: Run `/roleperms`
Shows a dropdown with all server roles (excluding @everyone and bot roles).

### Step 2: Select a Role
After selecting (e.g., @Admin), a modal opens with the current configuration.

### Step 3: Edit Configuration in Modal
The modal contains a single large text field pre-filled with:

```ini
[Player]
alderonid=false
playerid=true
myid=true

[Strikes]
addstrike=true
strikes=true
strikehistory=true
removestrike=false
clearstrikes=false
ban=false
unban=false
bans=true
wipehistory=false
recentstrikes=true

[Tickets]
ticketpanel=false
addbutton=false
refreshpanel=false
listpanels=true
tickets=true
close=true
claim=true
adduser=true
removeuser=true

[Moderation]
announce=false
say=false
clear=true
rolepanel=false
serverinfo=true
userinfo=true

[Config]
setup=true
setchannel=false
feature=false
roleperms=false
```

### Step 4: Save
On submit, parse the INI, validate, save to database, show summary of changes.

---

## Database Schema

### New Table: `guild_role_permissions`

```sql
CREATE TABLE guild_role_permissions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    guild_id BIGINT NOT NULL,
    role_id BIGINT NOT NULL,
    command_name VARCHAR(50) NOT NULL,
    allowed BOOLEAN NOT NULL DEFAULT FALSE,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    UNIQUE KEY unique_role_command (guild_id, role_id, command_name),
    INDEX idx_guild_role (guild_id, role_id),
    FOREIGN KEY (guild_id) REFERENCES guilds(guild_id) ON DELETE CASCADE
);
```

### Migration Notes
- Keep `guild_admin_roles` table temporarily for backward compatibility
- Add migration to convert existing level-based permissions to new system
- Level 3 (Owner) → All commands = true
- Level 2 (Admin) → Most commands = true, dangerous ones = false
- Level 1 (Mod) → Basic moderation commands only

---

## Implementation Components

### 1. Database Queries (`database/queries/permissions.py`)

```python
class PermissionQueries:
    @staticmethod
    def get_role_permissions(guild_id: int, role_id: int) -> dict:
        """Get all permissions for a role as {command: bool}"""

    @staticmethod
    def set_role_permissions(guild_id: int, role_id: int, permissions: dict):
        """Set multiple permissions at once"""

    @staticmethod
    def get_user_allowed_commands(guild_id: int, user_roles: list[int]) -> set:
        """Get all commands a user can access based on their roles"""

    @staticmethod
    def can_use_command(guild_id: int, user_roles: list[int], command: str) -> bool:
        """Check if user can use a specific command"""

    @staticmethod
    def get_configured_roles(guild_id: int) -> list:
        """Get all roles that have been configured"""

    @staticmethod
    def count_allowed_commands(guild_id: int, role_id: int) -> int:
        """Count how many commands a role has access to"""
```

### 2. Permission Checker (`services/permissions.py`)

Update `require_admin()` or create new `require_permission()`:

```python
async def require_permission(interaction: discord.Interaction, command_name: str) -> bool:
    """Check if user has permission for a specific command."""
    guild_id = interaction.guild_id
    user = interaction.user

    # Server owner always has access
    if user.id == interaction.guild.owner_id:
        return True

    # Discord Administrator permission = full access
    if user.guild_permissions.administrator:
        return True

    # Check role-based permissions
    user_role_ids = [role.id for role in user.roles]
    if PermissionQueries.can_use_command(guild_id, user_role_ids, command_name):
        return True

    await interaction.response.send_message(
        "You don't have permission to use this command.",
        ephemeral=True
    )
    return False
```

### 3. Command Definition Constant

```python
# config/commands.py
COMMAND_CATEGORIES = {
    'Player': ['alderonid', 'playerid', 'myid'],
    'Strikes': ['addstrike', 'strikes', 'strikehistory', 'removestrike',
                'clearstrikes', 'ban', 'unban', 'bans', 'wipehistory', 'recentstrikes'],
    'Tickets': ['ticketpanel', 'addbutton', 'refreshpanel', 'listpanels',
                'tickets', 'close', 'claim', 'adduser', 'removeuser'],
    'Moderation': ['announce', 'say', 'clear', 'rolepanel', 'serverinfo', 'userinfo'],
    'Config': ['setup', 'setchannel', 'feature', 'roleperms', 'help']
}

# Feature to commands mapping (for hiding when feature disabled)
FEATURE_COMMANDS = {
    'strikes': ['addstrike', 'strikes', 'strikehistory', 'removestrike',
                'clearstrikes', 'ban', 'unban', 'bans', 'wipehistory', 'recentstrikes'],
    'tickets': ['ticketpanel', 'addbutton', 'refreshpanel', 'listpanels',
                'tickets', 'close', 'claim', 'adduser', 'removeuser'],
    'announcements': ['announce'],
    'player_linking': ['alderonid', 'playerid', 'myid'],
    'role_selection': ['rolepanel']
}

def get_all_commands() -> list[str]:
    """Get flat list of all commands."""
    commands = []
    for cmds in COMMAND_CATEGORIES.values():
        commands.extend(cmds)
    return commands
```

### 4. INI Parser Utilities

```python
# services/ini_parser.py
def parse_permissions_ini(text: str) -> dict:
    """Parse INI-style permission text into {command: bool} dict."""
    permissions = {}
    current_section = None

    for line in text.strip().split('\n'):
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if line.startswith('[') and line.endswith(']'):
            current_section = line[1:-1]
            continue
        if '=' in line:
            key, value = line.split('=', 1)
            key = key.strip().lower()
            value = value.strip().lower()
            permissions[key] = value in ('true', '1', 'yes', 'on')

    return permissions

def generate_permissions_ini(permissions: dict) -> str:
    """Generate INI text from permissions dict."""
    lines = []
    for category, commands in COMMAND_CATEGORIES.items():
        lines.append(f'[{category}]')
        for cmd in commands:
            value = 'true' if permissions.get(cmd, False) else 'false'
            lines.append(f'{cmd}={value}')
        lines.append('')
    return '\n'.join(lines)
```

### 5. Role Permissions Command & Modal

```python
# In cogs/admin/config.py

@app_commands.command(name="roleperms", description="Configure command permissions for a role")
@app_commands.guild_only()
async def role_perms(self, interaction: discord.Interaction):
    """Configure permissions for a role - shows role selector."""
    # Only server owner or users with roleperms permission can use this
    if not await require_permission(interaction, 'roleperms'):
        return

    # Show role selector dropdown
    view = RoleSelectView()
    await interaction.response.send_message(
        "Select a role to configure permissions:",
        view=view,
        ephemeral=True
    )

class RoleSelectView(discord.ui.View):
    @discord.ui.select(cls=discord.ui.RoleSelect, placeholder="Select a role...")
    async def role_select(self, interaction: discord.Interaction, select: discord.ui.RoleSelect):
        role = select.values[0]

        # Get current permissions
        current = PermissionQueries.get_role_permissions(interaction.guild_id, role.id)
        ini_text = generate_permissions_ini(current)

        modal = RolePermissionsModal(role, ini_text)
        await interaction.response.send_modal(modal)

class RolePermissionsModal(discord.ui.Modal):
    def __init__(self, role: discord.Role, current_ini: str):
        super().__init__(title=f"Permissions: {role.name[:20]}")
        self.role = role

        self.permissions = discord.ui.TextInput(
            label="Edit permissions (true/false)",
            style=discord.TextStyle.paragraph,
            default=current_ini,
            max_length=4000,
            required=True
        )
        self.add_item(self.permissions)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            # Parse the INI
            new_perms = parse_permissions_ini(self.permissions.value)

            # Validate - check all commands exist
            all_commands = get_all_commands()
            invalid = [cmd for cmd in new_perms if cmd not in all_commands]
            if invalid:
                await interaction.response.send_message(
                    f"Invalid commands: {', '.join(invalid)}",
                    ephemeral=True
                )
                return

            # Save to database
            PermissionQueries.set_role_permissions(
                interaction.guild_id, self.role.id, new_perms
            )

            # Count enabled
            enabled_count = sum(1 for v in new_perms.values() if v)

            await interaction.response.send_message(
                f"Permissions updated for {self.role.mention}\n"
                f"**{enabled_count}** commands enabled out of {len(all_commands)}",
                ephemeral=True
            )
        except Exception as e:
            await interaction.response.send_message(
                f"Error parsing permissions: {e}",
                ephemeral=True
            )
```

### 6. Dynamic /help Command

```python
@app_commands.command(name="help", description="List available commands")
@app_commands.guild_only()
async def help_command(self, interaction: discord.Interaction):
    guild_id = interaction.guild_id
    user_role_ids = [role.id for role in interaction.user.roles]

    # Get commands this user can access
    allowed = PermissionQueries.get_user_allowed_commands(guild_id, user_role_ids)

    # Server owner sees all
    if interaction.user.id == interaction.guild.owner_id:
        allowed = set(get_all_commands())

    # Filter by enabled features
    for feature, commands in FEATURE_COMMANDS.items():
        if not GuildQueries.is_feature_enabled(guild_id, feature):
            allowed -= set(commands)

    embed = discord.Embed(
        title="Available Commands",
        color=discord.Color.green()
    )

    for category, commands in COMMAND_CATEGORIES.items():
        visible = [cmd for cmd in commands if cmd in allowed]
        if visible:
            cmd_list = '\n'.join([f'`/{cmd}`' for cmd in visible])
            embed.add_field(name=category, value=cmd_list, inline=True)

    if not any(embed.fields):
        embed.description = "You don't have access to any commands."

    embed.set_footer(text=f"You have access to {len(allowed)} commands")
    await interaction.response.send_message(embed=embed, ephemeral=True)
```

### 7. Updated /setup Display

```python
# In /setup command, update the Permission Roles section:

configured_roles = PermissionQueries.get_configured_roles(guild_id)

if configured_roles:
    role_lines = []
    for role_data in configured_roles:
        role_id = role_data['role_id']
        count = PermissionQueries.count_allowed_commands(guild_id, role_id)
        role_lines.append(f"<@&{role_id}> - {count} commands")

    role_text = "Use `/roleperms` to edit\n" + "\n".join(role_lines)
else:
    role_text = "No roles configured.\nUse `/roleperms` to set up permissions."

embed.add_field(name="Permission Roles", value=role_text, inline=False)
```

---

## Migration Path

1. **Phase 1:** Add new database table and queries
2. **Phase 2:** Add `/roleperms` command alongside existing system
3. **Phase 3:** Update permission checker to use new system (with fallback)
4. **Phase 4:** Update `/help` to be dynamic
5. **Phase 5:** Update `/setup` display
6. **Phase 6:** Deprecate old commands (`setadminrole`, etc.)
7. **Phase 7:** Remove old system after testing

---

## Edge Cases to Handle

1. **Deleted roles** - Clean up permissions when role is deleted (event listener)
2. **New commands added** - Default to `false` if not in config
3. **Invalid INI syntax** - Show helpful error message
4. **Modal text limit** - Current config is ~800 chars, limit is 4000, so we're safe
5. **Multiple roles** - User gets union of all role permissions (if ANY role allows, user can use)

---

## Answers to Planning Questions

1. **Config category for dangerous commands?** - Yes, `roleperms`, `feature`, `wipehistory` should be in Config category and default to false for all roles except owner.

2. **Show ALL server roles in dropdown?** - Show all roles except @everyone and bot roles. Any role can be configured.

3. **Keep old commands?** - Deprecate them. Show a message pointing to `/roleperms` if someone uses `setadminrole`.

4. **/help grouping** - Group by category like the config, matching the INI structure.

---

## Next Steps

When resuming on Mac:
1. Read this file: `docs/permission-system-plan.md`
2. Start with database schema creation
3. Implement `PermissionQueries` class
4. Add the `/roleperms` command
5. Update permission checker
6. Update `/help` to be dynamic
7. Update `/setup` display
8. Test thoroughly
9. Remove deprecated commands
