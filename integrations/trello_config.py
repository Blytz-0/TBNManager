from decouple import config
import json

# Trello Authentication
TRELLO_API_KEY = config('TRELLO_API_KEY')
TRELLO_TOKEN = config('TRELLO_TOKEN')

# Trello Board and List IDs
TRELLO_LIST_ID = config('TRELLO_LIST_ID')
BANNED_LIST_ID = config('BANNED_LIST_ID')
THIRD_STRIKE_LIST_ID = config('THIRD_STRIKE_LIST_ID')

# Trello-specific JSON mappings
STRIKE_LIST_MAPPING = json.loads(config('STRIKE_LIST_MAPPING').replace("'", '"'))
STRIKE_STAGE = json.loads(config('STRIKE_STAGE').replace("'", '"'))
