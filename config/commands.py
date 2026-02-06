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
    'Player': ['alderonid', 'linksteam', 'verifymyid', 'playerid', 'myid', 'unlinkid'],
    'Strikes': [
        'addstrike', 'strikelist', 'strikehistory', 'removestrike',
        'clearstrikes', 'ban', 'unban', 'banlist', 'wipehistory', 'recentstrikes'
    ],
    'Tickets': [
        'ticketpanel', 'addbutton', 'refreshpanel', 'listpanels',
        'ticketlist', 'closeticket', 'claimticket', 'ticketadd', 'ticketremove'
    ],
    'Moderation': ['announce', 'say', 'clear', 'rolepanel', 'serverinfo', 'userinfo'],
    'Config': ['setup', 'setchannel', 'feature', 'rolepermissions', 'help'],
    # Premium: RCON Integration
    'RCON': [
        'rcon_help', 'rcon_addserver', 'rcon_servers', 'rcon_removeserver', 'rcon_test',
        'rcon_kick', 'rcon_ban', 'rcon_announce', 'rcon_dm', 'rcon_players', 'rcon_save', 'rcon_console',
        'rcon_wipecorpses', 'rcon_allowdinos', 'rcon_whitelist', 'rcon_whitelistadd',
        'rcon_whitelistremove', 'rcon_globalchat', 'rcon_togglehumans', 'rcon_toggleai',
        'rcon_disableai', 'rcon_aidensity', 'rcon_startverify', 'rcon_verify'
    ],
    # Premium: Pterodactyl Control
    'Server': [
        'server_help', 'server_setup', 'server_connections', 'server_refresh', 'server_list', 'server_info',
        'server_start', 'server_stop', 'server_restart', 'server_kill',
        'server_files', 'server_readfile', 'server_editfile', 'server_download', 'server_console'
    ],
    # Premium: SFTP Log Monitoring
    'SFTP Logs': [
        'logs_help', 'logs_setup', 'logs_setpath', 'logs_setchannel', 'logs_start', 'logs_stop',
        'logs_status', 'logs_fileinfo', 'logs_test', 'logs_readfile', 'logs_browse'
    ],
    # Panel Access Permissions (Meta-Permissions)
    'Panel Access': [
        'panel.players', 'panel.enforcement', 'panel.tickets', 'panel.moderation', 'panel.settings',
        'panel.rcon', 'panel.pterodactyl', 'panel.logs',
        # Legacy panel access (for compatibility)
        'pterodactyl_panel', 'rcon_panel', 'logs_panel'
    ],
    # Pterodactyl Panel Features
    'Pterodactyl Panel': [
        'inpanel_ptero_setup', 'inpanel_ptero_connections', 'inpanel_ptero_refresh', 'inpanel_ptero_list',
        'inpanel_ptero_info', 'inpanel_ptero_start', 'inpanel_ptero_stop', 'inpanel_ptero_restart',
        'inpanel_ptero_kill', 'inpanel_ptero_files', 'inpanel_ptero_console'
    ],
    # RCON Panel Features
    'RCON Panel': [
        'inpanel_rcon_addserver', 'inpanel_rcon_servers', 'inpanel_rcon_removeserver', 'inpanel_rcon_test',
        'inpanel_rcon_console', 'inpanel_rcon_kick', 'inpanel_rcon_ban', 'inpanel_rcon_announce',
        'inpanel_rcon_dm', 'inpanel_rcon_players', 'inpanel_rcon_wipecorpses', 'inpanel_rcon_allowclasses',
        'inpanel_rcon_addremoveclass', 'inpanel_rcon_globalchat', 'inpanel_rcon_togglehumans',
        'inpanel_rcon_toggleai', 'inpanel_rcon_disableai', 'inpanel_rcon_aidensity',
        'inpanel_rcon_whitelist', 'inpanel_rcon_managewhitelist'
    ],
    # SFTP/Logs Panel Features
    'SFTP Logs Panel': [
        'inpanel_logs_setup', 'inpanel_logs_setpath', 'inpanel_logs_setchannel',
        'inpanel_logs_start', 'inpanel_logs_stop', 'inpanel_logs_status',
        'inpanel_logs_browse', 'inpanel_logs_readfile'
    ],
    # Players Panel Features
    'Players Panel': [
        'inpanel_player_linkids', 'inpanel_player_verify',
        'inpanel_player_lookup', 'inpanel_player_myid', 'inpanel_player_unlink'
    ],
    # Enforcement Panel Features
    'Enforcement Panel': [
        'inpanel_enforcement_addstrike', 'inpanel_enforcement_viewstrikes', 'inpanel_enforcement_history',
        'inpanel_enforcement_remove', 'inpanel_enforcement_clear', 'inpanel_enforcement_ban',
        'inpanel_enforcement_unban', 'inpanel_enforcement_banlist', 'inpanel_enforcement_wipe',
        'inpanel_enforcement_recent'
    ],
    # Tickets Panel Features
    'Tickets Panel': [
        'inpanel_tickets_createpanel', 'inpanel_tickets_addbutton', 'inpanel_tickets_refresh',
        'inpanel_tickets_listpanels', 'inpanel_tickets_list', 'inpanel_tickets_close',
        'inpanel_tickets_claim', 'inpanel_tickets_adduser', 'inpanel_tickets_removeuser'
    ],
    # Moderation Panel Features
    'Moderation Panel': [
        'inpanel_moderation_announce', 'inpanel_moderation_say', 'inpanel_moderation_clear',
        'inpanel_moderation_rolepanel', 'inpanel_moderation_serverinfo', 'inpanel_moderation_userinfo',
        'inpanel_moderation_aidetect', 'inpanel_moderation_aisettings'
    ],
    # Settings Panel Features (Owner Only)
    'Settings Panel': [
        'inpanel_settings_view', 'inpanel_settings_features', 'inpanel_settings_setchannel',
        'inpanel_settings_setadminrole', 'inpanel_settings_removeadminrole', 'inpanel_settings_adminroles',
        'inpanel_settings_permissions', 'inpanel_settings_premium', 'inpanel_settings_subscription'
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
    'player_linking': ['alderonid', 'linksteam', 'verifymyid', 'playerid', 'myid', 'unlinkid'],
    'role_selection': ['rolepanel'],
    # Premium features
    'rcon': [
        'rcon_help', 'rcon_addserver', 'rcon_servers', 'rcon_removeserver', 'rcon_test',
        'rcon_kick', 'rcon_ban', 'rcon_announce', 'rcon_dm', 'rcon_players', 'rcon_save', 'rcon_console',
        'rcon_wipecorpses', 'rcon_allowdinos', 'rcon_whitelist', 'rcon_whitelistadd',
        'rcon_whitelistremove', 'rcon_globalchat', 'rcon_togglehumans', 'rcon_toggleai',
        'rcon_disableai', 'rcon_aidensity', 'rcon_startverify', 'rcon_verify'
    ],
    'pterodactyl': [
        'server_help', 'server_setup', 'server_connections', 'server_refresh', 'server_list', 'server_info',
        'server_start', 'server_stop', 'server_restart', 'server_kill',
        'server_files', 'server_readfile', 'server_editfile', 'server_download', 'server_console'
    ],
    'log_monitoring': [
        'logs_help', 'logs_setup', 'logs_setpath', 'logs_setchannel', 'logs_start', 'logs_stop',
        'logs_status', 'logs_fileinfo', 'logs_test', 'logs_readfile', 'logs_browse'
    ],
}

# Commands that should default to false for all roles (dangerous/sensitive)
RESTRICTED_COMMANDS = [
    'wipehistory',  # Permanently deletes records
    'rolepermissions',    # Modifies permission system
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
    # Panel - Enforcement dangerous commands
    'inpanel_enforcement_ban',   # Direct ban without strikes
    'inpanel_enforcement_clear', # Clear all strikes
    'inpanel_enforcement_wipe',  # Permanently delete records
    # Panel - Players dangerous commands
    'inpanel_player_unlink',     # Unlink IDs (ban evasion risk)
    # Panel - Settings dangerous commands
    'inpanel_settings_features',     # Toggle bot features
    'inpanel_settings_permissions',  # Modify permission system
    'inpanel_settings_setadminrole',    # Add admin role
    'inpanel_settings_removeadminrole', # Remove admin role
    # Panel - Moderation dangerous commands
    'inpanel_moderation_clear',      # Delete messages
    'inpanel_moderation_aisettings', # Configure AI detection
]

# Command descriptions for /help display
COMMAND_DESCRIPTIONS = {
    # Player
    'alderonid': 'Link your Discord to your Alderon ID',
    'linksteam': 'Link your Discord to your Steam ID',
    'verifymyid': '[Premium] Verify by typing a code in-game chat',
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
    'rolepermissions': 'Configure role permissions',
    'help': 'List available commands',

    # RCON (Premium)
    'rcon_help': '[Premium] Show all RCON commands',
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
    'rcon_console': '[Premium] Send raw RCON command (PoT)',
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
    'rcon_startverify': '[Premium] Start RCON verification',
    'rcon_verify': '[Premium] Complete RCON verification',

    # Server Control (Premium)
    'server_help': '[Premium] Show all server commands',
    'server_setup': '[Premium] Configure Pterodactyl connection',
    'server_connections': '[Premium] List Pterodactyl connections',
    'server_refresh': '[Premium] Re-discover servers from panel',
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

    # SFTP Logs (Premium)
    'logs_help': '[Premium] Show all log monitoring commands',
    'logs_setup': '[Premium] Configure SFTP for log monitoring',
    'logs_setpath': '[Premium] Set log file path',
    'logs_setchannel': '[Premium] Set log output channel',
    'logs_start': '[Premium] Start log monitoring',
    'logs_stop': '[Premium] Stop log monitoring',
    'logs_status': '[Premium] Show monitoring status',
    'logs_fileinfo': '[Premium] Check log file details',
    'logs_test': '[Premium] Test log file reading',
    'logs_readfile': '[Premium] Read file contents',
    'logs_browse': '[Premium] Browse SFTP directory',

    # Panel Access Permissions
    'pterodactyl_panel': '[Premium] Access Pterodactyl panel',
    'rcon_panel': '[Premium] Access RCON panel',
    'logs_panel': '[Premium] Access SFTP logs panel',

    # Pterodactyl Panel Features
    'inpanel_ptero_setup': '[Panel] Configure Pterodactyl connection',
    'inpanel_ptero_connections': '[Panel] List Pterodactyl connections',
    'inpanel_ptero_refresh': '[Panel] Re-discover servers',
    'inpanel_ptero_list': '[Panel] List game servers',
    'inpanel_ptero_info': '[Panel] Show server info',
    'inpanel_ptero_start': '[Panel] Start game server',
    'inpanel_ptero_stop': '[Panel] Stop game server',
    'inpanel_ptero_restart': '[Panel] Restart game server',
    'inpanel_ptero_kill': '[Panel] Force kill server',
    'inpanel_ptero_files': '[Panel] Browse server files',
    'inpanel_ptero_console': '[Panel] Send console command',

    # RCON Panel Features
    'inpanel_rcon_addserver': '[Panel] Add RCON server',
    'inpanel_rcon_servers': '[Panel] List RCON servers',
    'inpanel_rcon_removeserver': '[Panel] Remove RCON server',
    'inpanel_rcon_test': '[Panel] Test RCON connection',
    'inpanel_rcon_console': '[Panel] Send raw RCON command',
    'inpanel_rcon_kick': '[Panel] Kick player',
    'inpanel_rcon_ban': '[Panel] Ban player',
    'inpanel_rcon_announce': '[Panel] Send announcement',
    'inpanel_rcon_dm': '[Panel] DM player in-game',
    'inpanel_rcon_players': '[Panel] List online players',
    'inpanel_rcon_wipecorpses': '[Panel] Wipe corpses',
    'inpanel_rcon_allowclasses': '[Panel] Allow/disallow dinos',
    'inpanel_rcon_addremoveclass': '[Panel] Manage dino pool',
    'inpanel_rcon_globalchat': '[Panel] Toggle global chat',
    'inpanel_rcon_togglehumans': '[Panel] Toggle humans',
    'inpanel_rcon_toggleai': '[Panel] Toggle AI',
    'inpanel_rcon_disableai': '[Panel] Disable specific AI',
    'inpanel_rcon_aidensity': '[Panel] Set AI density',
    'inpanel_rcon_whitelist': '[Panel] Toggle whitelist',
    'inpanel_rcon_managewhitelist': '[Panel] Manage whitelist',

    # SFTP Logs Panel Features
    'inpanel_logs_setup': '[Panel] Configure SFTP',
    'inpanel_logs_setpath': '[Panel] Set log file path',
    'inpanel_logs_setchannel': '[Panel] Set log channels',
    'inpanel_logs_start': '[Panel] Start monitoring',
    'inpanel_logs_stop': '[Panel] Stop monitoring',
    'inpanel_logs_status': '[Panel] View status',
    'inpanel_logs_browse': '[Panel] Browse files',
    'inpanel_logs_readfile': '[Panel] Read file',

    # Panel Access (Meta-Permissions)
    'panel.players': 'Access Players panel',
    'panel.enforcement': 'Access Enforcement panel',
    'panel.tickets': 'Access Tickets panel',
    'panel.moderation': 'Access Moderation panel',
    'panel.settings': 'Access Settings panel (Owner)',
    'panel.rcon': '[Premium] Access RCON panel',
    'panel.pterodactyl': '[Premium] Access Pterodactyl panel',
    'panel.logs': '[Premium] Access SFTP Logs panel',

    # Players Panel Features
    'inpanel_player_linkids': '[Panel] Link Steam or Alderon ID',
    'inpanel_player_verify': '[Panel] Verify in-game with code',
    'inpanel_player_lookup': '[Panel] Look up player by ID',
    'inpanel_player_myid': '[Panel] View your linked accounts',
    'inpanel_player_unlink': '[Panel] Unlink user ID (Admin)',

    # Enforcement Panel Features
    'inpanel_enforcement_addstrike': '[Panel] Issue strike to player',
    'inpanel_enforcement_viewstrikes': '[Panel] View active strikes',
    'inpanel_enforcement_history': '[Panel] View full strike history',
    'inpanel_enforcement_remove': '[Panel] Remove specific strike',
    'inpanel_enforcement_clear': '[Panel] Clear all active strikes',
    'inpanel_enforcement_ban': '[Panel] Directly ban player',
    'inpanel_enforcement_unban': '[Panel] Unban player',
    'inpanel_enforcement_banlist': '[Panel] List all banned players',
    'inpanel_enforcement_wipe': '[Panel] Permanently delete records',
    'inpanel_enforcement_recent': '[Panel] View recent strikes',

    # Tickets Panel Features
    'inpanel_tickets_createpanel': '[Panel] Create new ticket panel',
    'inpanel_tickets_addbutton': '[Panel] Add button to panel',
    'inpanel_tickets_refresh': '[Panel] Refresh panel after changes',
    'inpanel_tickets_listpanels': '[Panel] List all ticket panels',
    'inpanel_tickets_list': '[Panel] View all open tickets',
    'inpanel_tickets_close': '[Panel] Close current ticket',
    'inpanel_tickets_claim': '[Panel] Claim ticket to handle',
    'inpanel_tickets_adduser': '[Panel] Add user to ticket',
    'inpanel_tickets_removeuser': '[Panel] Remove user from ticket',

    # Moderation Panel Features
    'inpanel_moderation_announce': '[Panel] Send formatted announcement',
    'inpanel_moderation_say': '[Panel] Send message as bot',
    'inpanel_moderation_clear': '[Panel] Delete messages from channel',
    'inpanel_moderation_rolepanel': '[Panel] Create role selection panel',
    'inpanel_moderation_serverinfo': '[Panel] View server information',
    'inpanel_moderation_userinfo': '[Panel] View user information',
    'inpanel_moderation_aidetect': '[Panel] Run AI detection (Coming Soon)',
    'inpanel_moderation_aisettings': '[Panel] Configure AI detection (Coming Soon)',

    # Settings Panel Features
    'inpanel_settings_view': '[Panel] View bot configuration',
    'inpanel_settings_features': '[Panel] Toggle bot features',
    'inpanel_settings_setchannel': '[Panel] Configure log channels',
    'inpanel_settings_setadminrole': '[Panel] Add admin role',
    'inpanel_settings_removeadminrole': '[Panel] Remove admin role',
    'inpanel_settings_adminroles': '[Panel] View admin roles',
    'inpanel_settings_permissions': '[Panel] Configure role permissions',
    'inpanel_settings_premium': '[Panel] View premium status (Coming Soon)',
    'inpanel_settings_subscription': '[Panel] Manage subscription (Coming Soon)',
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
