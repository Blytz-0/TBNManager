# config/config.py
from decouple import config
import json

# Token and Database Configurations
TOKEN = config('TOKEN')
DATABASE_CONFIG = {
    'host': config('DB_HOST'),
    'user': config('DB_USER'),
    'password': config('DB_PASSWORD'),
    'database': config('DB_NAME')
}

# Trello List IDs and Mappings
BANNED_LIST_ID = config('BANNED_LIST_ID')
THIRD_STRIKE_LIST_ID = config('THIRD_STRIKE_LIST_ID')

# Convert JSON string from .env to dictionaries
STRIKE_LIST_MAPPING = json.loads(config('STRIKE_LIST_MAPPING'))
STRIKE_STAGE = json.loads(config('STRIKE_STAGE'))
