import re
import sqlite3
from discord import app_commands
from discord.ext import commands
from config.constants import DATABASE_PATH

class PlayerCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="alderonid", description="Link your Discord Account to your Alderon ID")
    async def setid(self, interaction, playerid: str, playername: str):
        if interaction.user.bot:
            return

        if not re.match(r"^\d{3}-\d{3}-\d{3}$", playerid):
            await interaction.response.send_message("Invalid ID format. Please use the format XXX-XXX-XXX.", ephemeral=True)
            return

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

    @app_commands.command(name="playerid", description="Retrieve a player's ID or Discord username based on input")
    async def playerid(self, interaction, query: str):
        if interaction.user.bot:
            return

        try:
            with sqlite3.connect(DATABASE_PATH) as conn:
                c = conn.cursor()
                if re.match(r"^\d{3}-\d{3}-\d{3}$", query):  
                    c.execute("SELECT username, playername FROM players WHERE playerid=?", (query,))
                    result = c.fetchone()

                    if result:
                        username, playername = result
                        await interaction.response.send_message(
                            f"The Discord user associated with player ID {query} is {username} (Player Name: {playername})",
                            ephemeral=True)
                    else:
                        await interaction.response.send_message("No Discord user found for that player ID.", ephemeral=True)
                else:  
                    c.execute("SELECT playerid, playername FROM players WHERE username=?", (query,))
                    result = c.fetchone()

                    if result:
                        playerid, playername = result
                        await interaction.response.send_message(
                            f"The player ID for {query} is {playerid} (Player Name: {playername})", ephemeral=True)
                    else:
                        await interaction.response.send_message("No player ID found for that Discord user.", ephemeral=True)
        except Exception as e:
            print(f"Error in /playerid command: {e}")
            await interaction.response.send_message("An error occurred while retrieving the player ID.", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(PlayerCommands(bot))
