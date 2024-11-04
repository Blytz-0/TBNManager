import os
import json
import discord
import sqlite3
from decouple import config
from discord.ext import commands
from dotenv import load_dotenv
from database.mysql import get_db_connection
from config.constants import DATABASE_PATH, REQUIRED_ROLES
from config.config import TOKEN

# Import command modules
from commands import admin_commands, player_commands

# Load environment variables
load_dotenv()

# Database connection
conn = sqlite3.connect(DATABASE_PATH)
c = conn.cursor()
c.execute('''
    CREATE TABLE IF NOT EXISTS players (
        username TEXT PRIMARY KEY,
        playerid TEXT,
        playername TEXT
    )
''')
conn.commit()
conn.close()

# Bot configuration
PREFIX = '/'
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix=PREFIX, intents=intents)

# Role checker
def has_required_role():
    def predicate(ctx):
        return any(role.name in REQUIRED_ROLES for role in ctx.author.roles)
    return commands.check(predicate)

# Events
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user.name} - {bot.user.id}")
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s)")
    except Exception as e:
        print(e)

@bot.event
async def on_command_error(ctx, error):
    print(f"Error: {error}")
    if isinstance(error, commands.MissingAnyRole):
        await ctx.send("You do not have access to this command!")

@bot.event
async def on_error(event, *args, **kwargs):
    import traceback
    traceback.print_exc()

@bot.event
async def on_disconnect():
    conn.close()

# Run the bot
bot.run(TOKEN)
