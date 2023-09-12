import os
import re
import json
import discord
import sqlite3
import asyncio
from decouple import config
from discord.ext import commands
from dotenv import load_dotenv
from trello import add_strike_to_trello, move_card_to_list, update_card_description, search_for_card 

conn = sqlite3.connect('players.db')
c = conn.cursor()


c.execute('''CREATE TABLE IF NOT EXISTS players
             (username text, playerid integer)''')
conn.commit()

DATABASE_PATH = 'players.db'
load_dotenv()

PREFIX = '/'

TOKEN = os.getenv('TOKEN')
BAN_LIST_ID = os.getenv('YOUR_BAN_LIST_ID')
THIRD_STRIKE_LIST_ID = os.getenv('THIRD_STRIKE_LIST_ID')
STRIKE_LIST_MAPPING_STR = os.getenv('STRIKE_LIST_MAPPING')
STRIKE_LIST_MAPPING = json.loads(STRIKE_LIST_MAPPING_STR)
STRIKE_STAGE_STR = config('STRIKE_STAGE_STR')
STRIKE_STAGE = json.loads(STRIKE_STAGE_STR)


entries = STRIKE_STAGE_STR.split(";")
STRIKE_STAGE = {entry.split(",")[0]: entry.split(",")[1] for entry in entries}

print(STRIKE_STAGE_STR)



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



intents = discord.Intents.default()
intents.message_content = True
intents.messages = True

bot = commands.Bot(command_prefix=PREFIX, intents=intents)


def has_required_role():
    def predicate(ctx):
        return any(role.name in REQUIRED_ROLES for role in ctx.author.roles)
    return commands.check(predicate)



@bot.event
async def on_ready():
    print(f"Logged in as {bot.user.name} - {bot.user.id}")
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s)")
    except Exception as e:
        print(e)

@bot.tree.command(name="hello")
async def hello(interaction: discord.Interaction):
    await interaction.response.send_message(f"Hey {interaction.user.mention}! this is a test", ephemeral = True)


@bot.event
async def on_command_error(ctx, error):
    print(f"Error: {error}")
    if isinstance(error, commands.MissingAnyRole):
        await ctx.send("You do not have access to this command!")

@bot.event
async def on_error(event, *args, **kwargs):
    import traceback
    traceback.print_exc()


async def post_roles_template(interaction, role_emojis, title, description_header):
    if interaction.user.bot:
        return

    if not any(role.name in ["Owner", "Headadmin"] for role in interaction.user.roles):
        await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
        return

    description_lines = [f"{description_header}\n"]
    for emoji, role_name in role_emojis.items():
        description_lines.append(f"{emoji} - {role_name}")

    description = '\n'.join(description_lines)

    # Send the message to the channel
    channel = interaction.channel
    message = await channel.send(description)

    # Add reactions to the message
    for emoji in role_emojis.keys():
        try:
            await message.add_reaction(emoji)
        except Exception as e:
            print(f"Error while adding reaction {emoji}: {e}")


async def post_roles_template(interaction, role_emojis, title_header):
    embed = discord.Embed(
        title=f"**{title_header}**",
        description="\n".join([f"{emoji} - {role}" for emoji, role in role_emojis.items()]),
        color=discord.Color.blue()
    )
    embed.set_footer(text="React with the appropriate emoji to get your role.")
    
   
    await interaction.response.defer()

    
    message = await interaction.followup.send(embed=embed)
    
    
    for emoji in role_emojis.keys():
        await message.add_reaction(emoji)


@bot.tree.command(name="chooseyourgender")
async def postgenderroles(interaction: discord.Interaction):
    await post_roles_template(interaction, GENDER_ROLE_EMOJIS, "Gender Roles")

@bot.tree.command(name="chooseyourplatform")
async def postplatformroles(interaction: discord.Interaction):
    await post_roles_template(interaction, PLATFORM_ROLE_EMOJIS, "Platform Roles")

@bot.tree.command(name="chooseyourserverroles")
async def postserverroles(interaction: discord.Interaction):
    await post_roles_template(interaction, SERVER_ROLE_EMOJIS, "Server Notification Roles")




ALL_ROLE_EMOJIS = {**GENDER_ROLE_EMOJIS, **PLATFORM_ROLE_EMOJIS, **SERVER_ROLE_EMOJIS}

@bot.event
async def on_raw_reaction_add(payload):
    guild = await bot.fetch_guild(payload.guild_id)
    member = await guild.fetch_member(payload.user_id)

    if member.bot:
        return

    emoji_name = str(payload.emoji)

    if emoji_name in ALL_ROLE_EMOJIS:
        role_name = ALL_ROLE_EMOJIS[emoji_name]
        role = discord.utils.get(guild.roles, name=role_name)
        if role:
            await member.add_roles(role)

@bot.event
async def on_raw_reaction_remove(payload):
    print("Reaction removed detected")  # Debug print

    guild = await bot.fetch_guild(payload.guild_id)
    member = await guild.fetch_member(payload.user_id)

    if member.bot:
        return

    emoji_name = str(payload.emoji)
    print(f"Emoji removed: {emoji_name}")  # Debug print

    if emoji_name in ALL_ROLE_EMOJIS:
        role_name = ALL_ROLE_EMOJIS[emoji_name]
        role = discord.utils.get(guild.roles, name=role_name)
        
        if role and role in member.roles:
            await member.remove_roles(role)
            print(f"Removed role {role_name} from {member.display_name}")
        else:
            print(f"Role {role_name} not found in {member.display_name}'s roles")
    else:
        print(f"Emoji {emoji_name} not found in ALL_ROLE_EMOJIS")




@bot.event
async def on_disconnect():
    conn.close()



# Define the add_strike function
async def add_strike(interaction: discord.Interaction, player_name: str, in_game_id: str, *, reason: str):
    try:
        # Placeholder logic, replace with your own
        # with your_database_connection as conn:
        #     cursor = conn.cursor()
        #     cursor.execute("UPDATE players SET strikes = strikes + 1 WHERE name = ? AND id = ?", (player_name, in_game_id))
        #     conn.commit()
        return True  # Return True if the strike was added successfully
    except Exception as e:
        # Handle the exception if any error occurs
        print(f"Error while adding strike: {e}")
        return False

async def prompt_for_ban_confirmation(interaction, player_name, in_game_id):
    # This method sends a message and waits for a 'Yes' or 'No' reply.
    # This is just a placeholder, you'll need to implement the real method!
    return True  # or False, depending on the response


async def prompt_for_ban_confirmation(interaction, player_name, in_game_id):
    # Send a message asking for confirmation.
    await interaction.followup.send(f"Has {player_name} | {in_game_id} been banned in game? Confirm with 'yes' or 'no'.")
    
    def check(m):
        return m.author == interaction.user and m.content.lower() in ['yes', 'no']
    
    try:
        response_message = await bot.wait_for('message', timeout=60.0, check=check)
        if response_message.content.lower() == 'yes':
            return True
        else:
            return False
    except asyncio.TimeoutError:
        await interaction.followup.send(f"No confirmed response received.{player_name} | {in_game_id} awaits in game ban confirmation.")
        return None

@bot.tree.command(name="addstrike")
async def addstrike_cmd(interaction: discord.Interaction, player_name: str, in_game_id: str, *, reason: str):
    await add_strike(interaction, player_name, in_game_id, reason=reason)

    if interaction.user.bot:
        return

    admin_name = str(interaction.user)
    existing_card = search_for_card(in_game_id)

    messages_to_send = []

    if existing_card:
        current_list_id = existing_card["idList"]
        new_list_id = STRIKE_LIST_MAPPING.get(current_list_id, None)
        
        if new_list_id:
            move_success = move_card_to_list(existing_card["id"], new_list_id)
            
            # Announce the strike stage
            message = STRIKE_STAGE.get(new_list_id, "Strike added")
            formatted_message = f"{message} for {player_name} | {in_game_id}."
            messages_to_send.append(formatted_message)
            
            if new_list_id == THIRD_STRIKE_LIST_ID:
                messages_to_send.append(f"⚠️ {player_name} | {in_game_id} needs to be banned! ⚠️")
                
                # Send the initial response
                await interaction.response.send_message(messages_to_send[0])
                messages_to_send.pop(0)  # Remove the already sent message

                banned_in_game = await prompt_for_ban_confirmation(interaction, player_name, in_game_id)
                if banned_in_game:
                    move_success = move_card_to_list(existing_card["id"], BAN_LIST_ID)
                    if move_success:
                        # Use follow-up for the subsequent messages
                        await interaction.followup.send(f"{player_name} | {in_game_id} has been moved to banned list after in-game ban confirmation.")
                    else:
                        await interaction.followup.send("Failed to ban the player.")
                else:
                    await interaction.followup.send(f"{player_name} | {in_game_id} will remain in the 3rd strike stage until banned in-game.")
            
            updated_desc = existing_card["desc"] + f"\nAdmin: {admin_name}\nRule break - {reason}"
            update_success = update_card_description(existing_card["id"], updated_desc)
            success = move_success and update_success

            if not success:
                messages_to_send.append("Failed to move or update card.")
        else:
            print(f"Error: Unexpected list ID for {player_name} | {in_game_id} or player already banned.")
            messages_to_send.append("Unexpected error. Failed to add strike.")
    else:
        success = add_strike_to_trello(player_name, in_game_id, admin_name, reason)
        if not success:
            messages_to_send.append("Failed to add strike to Trello.")

    # Now, send the remaining messages:
    for msg in messages_to_send:
        # Send the subsequent messages as follow-ups
        await interaction.followup.send(msg)


@bot.tree.command(name="alderonid")
async def setid(interaction: discord.Interaction, playerid: str):
    if interaction.user.bot:
        return

    if not re.match(r"^\d{3}-\d{3}-\d{3}$", playerid):
        await interaction.response.send_message("Invalid ID format. Please use the format XXX-XXX-XXX.", ephemeral=True)
        return

    with sqlite3.connect(DATABASE_PATH) as conn:
        c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO players (username, playerid) VALUES (?, ?)", (str(interaction.user), playerid))
        await interaction.response.send_message(f"Player ID for {interaction.user.mention} set to {playerid}", ephemeral=True)




@bot.tree.command(name="playerid")
async def playerid(interaction: discord.Interaction, query: str):
    if interaction.user.bot:
        return

    with sqlite3.connect(DATABASE_PATH) as conn:
        c = conn.cursor()
        if re.match(r"^\d{3}-\d{3}-\d{3}$", query):
            c.execute("SELECT username FROM players WHERE playerid=?", (query,))
            username = c.fetchone()

            if username:
                await interaction.response.send_message(f"The Discord user associated with player ID {query} is {username[0]}", ephemeral=True)
            else:
                await interaction.response.send_message("No Discord user found for that player ID.", ephemeral=True)
        else:
            c.execute("SELECT playerid FROM players WHERE username=?", (query,))
            pid = c.fetchone()

            if pid:
                await interaction.response.send_message(f"The player ID for {query} is {pid[0]}", ephemeral=True)
            else:
                await interaction.response.send_message("No player ID found for that Discord user.", ephemeral=True)


@bot.tree.command(name="announce")
async def announce(interaction: discord.Interaction, *, args: str = None):
    if interaction.user.bot:
        return

    # Check if the user has the required role
    if not any(role.name in ["Owner", "Headadmin"] for role in interaction.user.roles):
        await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
        return

    # Use'|' for newline in args
    args = args.replace("|", "\n") if args else None

    arg_list = args.split() if args else []

    channel_name = arg_list[0] if arg_list and arg_list[0] in CHANNELS else None
    content = ' '.join(arg_list[1:]) if channel_name else ' '.join(arg_list)

    if not content:
        await interaction.response.send_message("Please provide the content for the announcement after /announce (e.g. /announce Hello)", ephemeral=True)
        return

    if channel_name is None:
        await interaction.response.send_message("Where would you like this announcement to be posted? (rules/community/role_selection)", ephemeral=True)
        response = await bot.wait_for('message', check=lambda m: m.author == interaction.user and m.channel == interaction.channel)
        channel_name = response.content.strip().lower()

        if channel_name not in CHANNELS:
            await interaction.response.send_message("Invalid channel name!", ephemeral=True)
            return

    target_channel = bot.get_channel(CHANNELS[channel_name])
    if target_channel:
        await target_channel.send(content)
    else:
        await interaction.response.send_message(f"Couldn't find the channel associated with name {channel_name}", ephemeral=True)


@bot.tree.command(name="post")
async def post(interaction: discord.Interaction, *, args: str = None):
    if interaction.user.bot:
        return

    # Check if the user has the required role
    if not any(role.name in ["Owner", "Headadmin"] for role in interaction.user.roles):
        await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
        return

    args = args.replace("|", "\n")  # Replace | with a newline

    arg_list = args.split(maxsplit=1)  # Split args only once by space

    channel_name = None
    content = args  # Default content is all of args
    if arg_list and arg_list[0] in CHANNELS:
        channel_name = arg_list[0]
        content = arg_list[1] if len(arg_list) > 1 else ""

    if not content:
        await interaction.response.send_message("Please provide the content to post after /post (e.g. /post Hello)", ephemeral=True)
        return

    if channel_name is None:
        await interaction.response.send_message("Where would you like this content to be posted? (rules/community/role_selection)", ephemeral=True)
        response = await bot.wait_for('message', check=lambda m: m.author == interaction.user and m.channel == interaction.channel)
        channel_name = response.content.strip().lower()

        if channel_name not in CHANNELS:
            await interaction.response.send_message("Invalid channel name!", ephemeral=True)
            return

    target_channel = bot.get_channel(CHANNELS[channel_name])
    if target_channel:
        await target_channel.send(content)
    else:
        await interaction.response.send_message(f"Couldn't find the channel associated with name {channel_name}", ephemeral=True)


async def post_rules_template(interaction, content, title_header, embed_color, footer_text):
   
    formatted_content = content.replace("|", "\n")

    embed = discord.Embed(
        title=f"**{title_header}**",
        description=formatted_content,
        color=embed_color
    )
    embed.set_footer(text=footer_text)
    
    
    await interaction.response.defer()

    
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="tbngeneralrules")
async def post_general_rules(interaction: discord.Interaction, *, args: str = None):
    
    if not args:
        await interaction.response.send_message("Please provide the rules content.", ephemeral=True)
        return

    footer_text = "Remember, maintaining a welcoming and harmonious environment is everyone's responsibility. Let's respect and support one another"
    await post_rules_template(interaction, args, "A - GENERAL", discord.Color.blue(), footer_text)

@bot.tree.command(name="tbningamerules")
async def post_ingame_rules(interaction: discord.Interaction, *, args: str = None):
    
    if not args:
        await interaction.response.send_message("Please provide the rules content.", ephemeral=True)
        return

    footer_text = "Adherence to in-game rules ensures a smooth and enjoyable experience for everyone. Play fair and have fun!"
    await post_rules_template(interaction, args, "B - IN-GAME", discord.Color.orange(), footer_text)

@bot.tree.command(name="tbnstaffcommands")
async def post_staff_commands(interaction: discord.Interaction, *, args: str = None):
    
    if not args:
        await interaction.response.send_message("Please provide the commands content.", ephemeral=True)
        return

    footer_text = "Staff commands are tools to facilitate gameplay. Use responsibly and with discretion. Any form  of abuse will result in removal of the team followed by a permanent ban."
    await post_rules_template(interaction, args, "0 - STAFF", discord.Color.red(), footer_text)

@bot.tree.command(name="tbnstaffcoc")
async def post_staff_coc(interaction: discord.Interaction, *, args: str = None):
    
    if not args:
        await interaction.response.send_message("Please provide the code of conduct content.", ephemeral=True)
        return

    
    footer_text = "Our code of conduct reflects our values. Let's uphold the integrity of our roles."
    await post_rules_template(interaction, args, "1 - CODE", discord.Color.gold(), footer_text)


@bot.tree.command(name="clear")
async def clear(interaction: discord.Interaction):
    if interaction.user.bot:
        return

    # Check if the user has the required role
    if not any(role.name in ["Owner", "Headadmin"] for role in interaction.user.roles):
        await interaction.response.send_message("You don't have permission to use this command.")
        return

    
    await interaction.response.defer()

    try:
        # Fetchs messages in the channel
        messages_to_delete = [message async for message in interaction.channel.history(limit=100)]
        
        # Bulk delete messages
        await interaction.channel.delete_messages(messages_to_delete)

        # Sends confirmation
        confirmation_message = await interaction.channel.send("Messages cleared!", delete_after=5)
    except discord.Forbidden:
        await interaction.followup.send("I don't have permission to delete messages.")
    except discord.HTTPException:
        await interaction.followup.send("An error occurred while clearing messages.")


@bot.tree.command(name="commands")
async def _commands(interaction: discord.Interaction):
    if interaction.user.bot:
        return

    
    general_commands = [
        "/announce: Send an announcement to a specific channel",
        "/post: Post content to a specific channel",
        "/chooseyourgender: Display a message for users to select their roles using reactions",
        "/chooseyourplatform: Display a message for users to select their roles using reactions",
        "/chooseyourserverroles: Display a message for users to select their roles using reactions",
        "/playerid: Query the Discord user associated with a player ID or vice versa",
        "/alderonid: Link your Discord Account to your AlderonID ",
        "/clear: Clear a specified number of messages from a channel"
    ]

    # Creates an embed with a title and description
    embed = discord.Embed(title="Help", description="Here's a list of my commands:", color=0x00ff00)
    
    # Addd the general commands to the embed
    embed.add_field(name="ℹ️ General", value="\n".join(general_commands), inline=False)

    # Sends the embed as an ephemeral message in response to the interaction
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.event
async def on_close():
    with sqlite3.connect(DATABASE_PATH) as conn:
        conn.close()



bot.run(TOKEN)
