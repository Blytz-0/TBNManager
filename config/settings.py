# config/settings.py
"""
Central configuration loader for TBNManager

Loads all settings from environment variables with sensible defaults.
"""

from decouple import config
import logging

# ===========================================
# DISCORD BOT SETTINGS
# ===========================================
TOKEN = config('TOKEN')

# Development settings - set TEST_GUILD_ID for instant command sync
# Leave empty or remove for global sync (production)
TEST_GUILD_ID = config('TEST_GUILD_ID', default=None, cast=lambda x: int(x) if x else None)

# ===========================================
# DATABASE CONFIGURATION
# ===========================================
DATABASE_CONFIG = {
    'host': config('DB_HOST', default='localhost'),
    'port': config('DB_PORT', default=3306, cast=int),
    'user': config('DB_USER', default='tbnbot'),
    'password': config('DB_PASSWORD', default=''),
    'database': config('DB_NAME', default='tbnmanager'),
}

# ===========================================
# BOT DEFAULTS
# ===========================================

# Default permission levels
PERMISSION_LEVELS = {
    'user': 0,
    'mod': 1,
    'admin': 2,
    'owner': 3,
}

# Feature flags that can be toggled per-guild
DEFAULT_FEATURES = [
    'strikes',
    'tickets',
    'player_linking',
    'role_selection',
    'announcements',
    'audit_log',
    'auto_ban',
    'dm_notifications',
]

# Premium features (require subscription)
PREMIUM_FEATURES = [
    'advanced_analytics',
    'custom_branding',
    'api_access',
    'rcon',           # RCON server management (kick, ban, announce)
    'pterodactyl',    # Pterodactyl panel control (power, files)
    'log_monitoring', # SFTP log monitoring (chat, kills, admin feeds)
]

# ===========================================
# STEAM API CONFIGURATION
# ===========================================
# Get your API key from: https://steamcommunity.com/dev/apikey
STEAM_API_KEY = config('STEAM_API_KEY', default=None)

# ===========================================
# ENCRYPTION CONFIGURATION
# ===========================================
# Master key for encrypting sensitive data (RCON passwords, API keys)
# Generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
ENCRYPTION_MASTER_KEY = config('ENCRYPTION_MASTER_KEY', default=None)

# ===========================================
# LOGGING CONFIGURATION
# ===========================================
LOG_LEVEL = config('LOG_LEVEL', default='INFO')

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# ===========================================
# LEGACY TRELLO (Deprecated - will be removed)
# ===========================================
TRELLO_ENABLED = config('TRELLO_ENABLED', default=False, cast=bool)

if TRELLO_ENABLED:
    TRELLO_CONFIG = {
        'api_key': config('TRELLO_API_KEY', default=''),
        'token': config('TRELLO_TOKEN', default=''),
        'list_id': config('TRELLO_LIST_ID', default=''),
        'board_id': config('TRELLO_BOARD_ID', default=''),
        'banned_list_id': config('BANNED_LIST_ID', default=''),
    }
else:
    TRELLO_CONFIG = None
