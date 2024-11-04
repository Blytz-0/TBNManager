import re
import sqlite3
from discord.ext import commands
from config.constants import DATABASE_PATH

# Command to set a player's ID and name
@commands.command(name="alderonid")
async def setid(interaction, playerid: str, playername: str):
    """
    Command to set a player's in-game ID and name, and associate it with the user's Discord account.
    
    Args:
        interaction (discord.Interaction): The interaction object representing the user's command interaction.
        playerid (str): The player's in-game ID in the format XXX-XXX-XXX.
        playername (str): The player's in-game name.
    """
    if interaction.user.bot:
        return

    if not re.match(r"^\d{3}-\d{3}-\d{3}$", playerid):
        await interaction.response.send_message(
            "Invalid ID format. Please use the format XXX-XXX-XXX.", ephemeral=True)
        return

    # Connect to the database and insert/update player data
    try:
        with sqlite3.connect(DATABASE_PATH) as conn:
            c = conn.cursor()
            c.execute("INSERT OR REPLACE INTO players (username, playerid, playername) VALUES (?, ?, ?)",
                      (str(interaction.user), playerid, playername))
            conn.commit()
            await interaction.response.send_message(
                f"Player ID and name for {interaction.user.mention} set to {playerid}, {playername}", ephemeral=True)
    except Exception as e:
        print(f"Error in /alderonid command: {e}")
        await interaction.response.send_message(
            "An error occurred while setting your player ID and name.", ephemeral=True)

# Command to retrieve a player's ID or username based on input
@commands.command(name="playerid")
async def playerid(interaction, query: str):
    """
    Command to retrieve a player's ID or Discord username based on input.
    
    Args:
        interaction (discord.Interaction): The interaction object representing the user's command interaction.
        query (str): The query string, which can be a player ID or Discord username.
    """
    if interaction.user.bot:
        return

    # Connect to the database and fetch player data
    try:
        with sqlite3.connect(DATABASE_PATH) as conn:
            c = conn.cursor()
            if re.match(r"^\d{3}-\d{3}-\d{3}$", query):  # Query is a player ID
                c.execute("SELECT username, playername FROM players WHERE playerid=?", (query,))
                result = c.fetchone()

                if result:
                    username, playername = result
                    await interaction.response.send_message(
                        f"The Discord user associated with player ID {query} is {username} (Player Name: {playername})",
                        ephemeral=True)
                else:
                    await interaction.response.send_message(
                        "No Discord user found for that player ID.", ephemeral=True)
            else:  # Query is a Discord username
                c.execute("SELECT playerid, playername FROM players WHERE username=?", (query,))
                result = c.fetchone()

                if result:
                    playerid, playername = result
                    await interaction.response.send_message(
                        f"The player ID for {query} is {playerid} (Player Name: {playername})", ephemeral=True)
                else:
                    await interaction.response.send_message(
                        "No player ID found for that Discord user.", ephemeral=True)
    except Exception as e:
        print(f"Error in /playerid command: {e}")
        await interaction.response.send_message(
            "An error occurred while retrieving the player ID.", ephemeral=True)
