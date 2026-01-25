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
    'Player': ['alderonid', 'linksteam', 'playerid', 'myid', 'unlinkid'],
    'Strikes': [
        'addstrike', 'strikelist', 'strikehistory', 'removestrike',
        'clearstrikes', 'ban', 'unban', 'banlist', 'wipehistory', 'recentstrikes'
    ],
    'Tickets': [
        'ticketpanel', 'addbutton', 'refreshpanel', 'listpanels',
        'ticketlist', 'closeticket', 'claimticket', 'ticketadd', 'ticketremove'
    ],
    'Moderation': ['announce', 'say', 'clear', 'rolepanel', 'serverinfo', 'userinfo'],
    'Config': ['setup', 'setchannel', 'feature', 'roleperms', 'help'],
    # Premium: RCON Integration
    'RCON': [
        'rcon_addserver', 'rcon_servers', 'rcon_removeserver', 'rcon_test',
        'rcon_kick', 'rcon_ban', 'rcon_announce', 'rcon_dm', 'rcon_players', 'rcon_save',
        'rcon_wipecorpses', 'rcon_allowdinos', 'rcon_whitelist', 'rcon_whitelistadd',
        'rcon_whitelistremove', 'rcon_globalchat', 'rcon_togglehumans', 'rcon_toggleai',
        'rcon_disableai', 'rcon_aidensity'
    ],
    # Premium: Pterodactyl Control
    'Server': [
        'server_setup', 'server_connections', 'server_list', 'server_info',
        'server_start', 'server_stop', 'server_restart', 'server_kill',
        'server_files', 'server_readfile', 'server_editfile', 'server_download', 'server_console'
    ],
    # Premium: Log Monitoring
    'Logs': [
        'logs_setup', 'logs_setpath', 'logs_setchannel', 'logs_start', 'logs_stop', 'logs_status'
    ],
}

# Feature to commands mapping
# When a feature is disabled, these commands are hidden from /help
FEATURE_COMMANDS = {
    'strikes': [
        'addstrike', 'strikelist', 'strikehistory', 'removestrike',
        'clearstrikes', 'ban', 'unban', 'banlist', 'wipehistory', 'recentstrikes'
    ],
    'tickets': [
        'ticketpanel', 'addbutton', 'refreshpanel', 'listpanels',
        'ticketlist', 'closeticket', 'claimticket', 'ticketadd', 'ticketremove'
    ],
    'announcements': ['announce'],
    'player_linking': ['alderonid', 'linksteam', 'playerid', 'myid', 'unlinkid'],
    'role_selection': ['rolepanel'],
    # Premium features
    'rcon': [
        'rcon_addserver', 'rcon_servers', 'rcon_removeserver', 'rcon_test',
        'rcon_kick', 'rcon_ban', 'rcon_announce', 'rcon_dm', 'rcon_players', 'rcon_save',
        'rcon_wipecorpses', 'rcon_allowdinos', 'rcon_whitelist', 'rcon_whitelistadd',
        'rcon_whitelistremove', 'rcon_globalchat', 'rcon_togglehumans', 'rcon_toggleai',
        'rcon_disableai', 'rcon_aidensity'
    ],
    'pterodactyl': [
        'server_setup', 'server_connections', 'server_list', 'server_info',
        'server_start', 'server_stop', 'server_restart', 'server_kill',
        'server_files', 'server_readfile', 'server_editfile', 'server_download', 'server_console'
    ],
    'log_monitoring': [
        'logs_setup', 'logs_setpath', 'logs_setchannel', 'logs_start', 'logs_stop', 'logs_status'
    ],
}

# Commands that should default to false for all roles (dangerous/sensitive)
RESTRICTED_COMMANDS = [
    'wipehistory',  # Permanently deletes records
    'roleperms',    # Modifies permission system
    'feature',      # Toggles bot features
    'ban',          # Direct ban without strikes
    'clearstrikes', # Removes all strikes
    'unlinkid',     # Unlocks player IDs (ban evasion risk)
    # Premium - RCON dangerous commands
    'rcon_ban',         # Bans from game server
    'rcon_removeserver', # Removes server config
    'rcon_wipecorpses',  # Wipes all corpses
    'rcon_allowdinos',   # Changes playable dinosaurs
    'rcon_whitelist',    # Toggles whitelist
    'rcon_whitelistadd', # Modifies whitelist
    'rcon_whitelistremove', # Modifies whitelist
    'rcon_globalchat',   # Toggles global chat
    'rcon_togglehumans', # Toggles human players
    'rcon_toggleai',     # Toggles AI
    'rcon_disableai',    # Disables AI classes
    'rcon_aidensity',    # Changes AI density
    # Premium - Server control dangerous commands
    'server_stop',      # Stops game server
    'server_kill',      # Force kills server
    'server_editfile',  # Edits server files
    'server_console',   # Direct console access
]

# Command descriptions for /help display
COMMAND_DESCRIPTIONS = {
    # Player
    'alderonid': 'Link your Discord to your Alderon ID',
    'linksteam': 'Link your Discord to your Steam ID',
    'playerid': 'Look up player by Discord, Steam, or Alderon ID',
    'myid': 'View your linked accounts',
    'unlinkid': '[Admin] Unlock a user\'s linked ID',

    # Strikes
    'addstrike': 'Add a strike to a player',
    'strikelist': 'View active strikes for a player',
    'strikehistory': 'View full strike history',
    'removestrike': 'Remove a specific strike',
    'clearstrikes': 'Clear all active strikes',
    'ban': 'Directly ban a player',
    'unban': 'Unban a player',
    'banlist': 'List all banned players',
    'wipehistory': 'Permanently delete all records',
    'recentstrikes': 'View recent strikes server-wide',

    # Tickets
    'ticketpanel': 'Create a new ticket panel',
    'addbutton': 'Add a button to a ticket panel',
    'refreshpanel': 'Refresh a panel after changes',
    'listpanels': 'List all ticket panels',
    'ticketlist': 'View all open tickets',
    'closeticket': 'Close current ticket',
    'claimticket': 'Claim a ticket to handle it',
    'ticketadd': 'Add user to ticket',
    'ticketremove': 'Remove user from ticket',

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

    # RCON (Premium)
    'rcon_addserver': '[Premium] Add RCON server configuration',
    'rcon_servers': '[Premium] List configured RCON servers',
    'rcon_removeserver': '[Premium] Remove RCON server',
    'rcon_test': '[Premium] Test RCON connection',
    'rcon_kick': '[Premium] Kick player from game server',
    'rcon_ban': '[Premium] Ban player from game server',
    'rcon_announce': '[Premium] Send in-game announcement',
    'rcon_dm': '[Premium] DM player in-game',
    'rcon_players': '[Premium] List online players with dino info',
    'rcon_save': '[Premium] Save game server state',
    'rcon_wipecorpses': '[Premium] Wipe all corpses from server',
    'rcon_allowdinos': '[Premium] Update allowed playable dinosaurs',
    'rcon_whitelist': '[Premium] Toggle server whitelist',
    'rcon_whitelistadd': '[Premium] Add players to whitelist',
    'rcon_whitelistremove': '[Premium] Remove players from whitelist',
    'rcon_globalchat': '[Premium] Toggle global chat',
    'rcon_togglehumans': '[Premium] Toggle human players',
    'rcon_toggleai': '[Premium] Toggle AI spawns',
    'rcon_disableai': '[Premium] Disable specific AI classes',
    'rcon_aidensity': '[Premium] Set AI spawn density',

    # Server Control (Premium)
    'server_setup': '[Premium] Configure Pterodactyl connection',
    'server_connections': '[Premium] List Pterodactyl connections',
    'server_list': '[Premium] List game servers',
    'server_info': '[Premium] Show server info and resources',
    'server_start': '[Premium] Start game server',
    'server_stop': '[Premium] Stop game server',
    'server_restart': '[Premium] Restart game server',
    'server_kill': '[Premium] Force kill game server',
    'server_files': '[Premium] List server files',
    'server_readfile': '[Premium] Read file contents',
    'server_editfile': '[Premium] Edit server file',
    'server_download': '[Premium] Download server file',
    'server_console': '[Premium] Send console command',

    # Logs (Premium)
    'logs_setup': '[Premium] Configure SFTP for log monitoring',
    'logs_setpath': '[Premium] Set log file path',
    'logs_setchannel': '[Premium] Set log output channel',
    'logs_start': '[Premium] Start log monitoring',
    'logs_stop': '[Premium] Stop log monitoring',
    'logs_status': '[Premium] Show monitoring status',
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
