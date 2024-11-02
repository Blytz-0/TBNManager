REQUIRED_ROLES = ['Owner', 'Headadmin']

CHANNELS = {
    "rules": 1144340352224985189,          # channel ID for "rules"
    "community": 1150112197234671736,      # channel ID for "community"
    "role_selection": 1144339896639697026  # channel ID for "role_selection"
}


GENDER_ROLE_EMOJIS = {
    '<:hehim:1150102718254415944>': "He/Him",
    '<:sheher:1150102749460041748>': "She/Her",
    '<:theythem:1150102766056906804>': "They/Them",
    '<:itits:1150102803797266493>': "It/Its",
    '<:any_pronoun:1150102835627839519>': "Any Pronoun"
    
}

PLATFORM_ROLE_EMOJIS = {
    '<:pc:1150072742742343720>': 'PC',
    '<:playstation:1150072803027062855>': 'Playstation',
    '<:xbox:1150072857674666136>': 'Xbox',
    '<:nintendo:1150072876544827462>': 'Nintendo',
    '<:mobile:1150073175556767815>': 'Mobile',
    
}

SERVER_ROLE_EMOJIS = {
    '📕': 'Rule Changes',
    '🚨': 'Server Restarts',
    '📌': 'Event Announcements',
    '📢': 'Community Announcements',
    
}

GENERAL_COMMANDS = [
        "/announce: Send an announcement to a specific channel",
        "/post: Post content to a specific channel",
        "/chooseyourgender: Display a message for users to select their roles using reactions",
        "/chooseyourplatform: Display a message for users to select their roles using reactions",
        "/chooseyourserverroles: Display a message for users to select their roles using reactions",
        "/playerid: Query the Discord user associated with a player ID or vice versa",
        "/alderonid: Link your Discord Account to your AlderonID ",
        "/clear: Clear a specified number of messages from a channel"
    ]

DATABASE_PATH = 'players.db'