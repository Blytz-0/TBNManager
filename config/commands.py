# config/commands.py
"""
Command definitions and categories for the permission system.

This file defines all available commands organized by category,
which is used for:
- INI-style permission configuration
- Dynamic /help display
- Feature-based command hiding
"""

# All commands organized by category
# Order matters - this determines the order in INI config and /help
COMMAND_CATEGORIES = {
    'Player': ['alderonid', 'playerid', 'myid'],
    'Strikes': [
        'addstrike', 'strikes', 'strikehistory', 'removestrike',
        'clearstrikes', 'ban', 'unban', 'bans', 'wipehistory', 'recentstrikes'
    ],
    'Tickets': [
        'ticketpanel', 'addbutton', 'refreshpanel', 'listpanels',
        'tickets', 'close', 'claim', 'adduser', 'removeuser'
    ],
    'Moderation': ['announce', 'say', 'clear', 'rolepanel', 'serverinfo', 'userinfo'],
    'Config': ['setup', 'setchannel', 'feature', 'roleperms', 'help']
}

# Feature to commands mapping
# When a feature is disabled, these commands are hidden from /help
FEATURE_COMMANDS = {
    'strikes': [
        'addstrike', 'strikes', 'strikehistory', 'removestrike',
        'clearstrikes', 'ban', 'unban', 'bans', 'wipehistory', 'recentstrikes'
    ],
    'tickets': [
        'ticketpanel', 'addbutton', 'refreshpanel', 'listpanels',
        'tickets', 'close', 'claim', 'adduser', 'removeuser'
    ],
    'announcements': ['announce'],
    'player_linking': ['alderonid', 'playerid', 'myid'],
    'role_selection': ['rolepanel'],
}

# Commands that should default to false for all roles (dangerous/sensitive)
RESTRICTED_COMMANDS = [
    'wipehistory',  # Permanently deletes records
    'roleperms',    # Modifies permission system
    'feature',      # Toggles bot features
    'ban',          # Direct ban without strikes
    'clearstrikes', # Removes all strikes
]

# Command descriptions for /help display
COMMAND_DESCRIPTIONS = {
    # Player
    'alderonid': 'Link your Discord to your Alderon ID',
    'playerid': 'Look up player info by ID or name',
    'myid': 'View your linked Alderon ID',

    # Strikes
    'addstrike': 'Add a strike to a player',
    'strikes': 'View active strikes for a player',
    'strikehistory': 'View full strike history',
    'removestrike': 'Remove a specific strike',
    'clearstrikes': 'Clear all active strikes',
    'ban': 'Directly ban a player',
    'unban': 'Unban a player',
    'bans': 'List all banned players',
    'wipehistory': 'Permanently delete all records',
    'recentstrikes': 'View recent strikes server-wide',

    # Tickets
    'ticketpanel': 'Create a new ticket panel',
    'addbutton': 'Add a button to a ticket panel',
    'refreshpanel': 'Refresh a panel after changes',
    'listpanels': 'List all ticket panels',
    'tickets': 'View all open tickets',
    'close': 'Close current ticket',
    'claim': 'Claim a ticket to handle it',
    'adduser': 'Add user to ticket',
    'removeuser': 'Remove user from ticket',

    # Moderation
    'announce': 'Send a formatted announcement',
    'say': 'Send a message as the bot',
    'clear': 'Delete messages from a channel',
    'rolepanel': 'Create a role selection panel',
    'serverinfo': 'View server information',
    'userinfo': 'View user information',

    # Config
    'setup': 'View bot configuration',
    'setchannel': 'Set channel for logs/announcements',
    'feature': 'Enable/disable bot features',
    'roleperms': 'Configure role permissions',
    'help': 'List available commands',
}


def get_all_commands() -> list[str]:
    """Get a flat list of all commands."""
    commands = []
    for cmds in COMMAND_CATEGORIES.values():
        commands.extend(cmds)
    return commands


def get_command_count() -> int:
    """Get total number of commands."""
    return len(get_all_commands())


def get_category_for_command(command: str) -> str | None:
    """Get the category a command belongs to."""
    for category, commands in COMMAND_CATEGORIES.items():
        if command in commands:
            return category
    return None


def is_valid_command(command: str) -> bool:
    """Check if a command name is valid."""
    return command in get_all_commands()
