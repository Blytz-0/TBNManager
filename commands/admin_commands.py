import asyncio
import discord
from discord import app_commands
from discord.ext import commands
from integrations.trello import add_strike_to_trello, move_card_to_list, update_card_description, search_for_card
from integrations.trello_config import TRELLO_LIST_ID, BANNED_LIST_ID, STRIKE_LIST_MAPPING, STRIKE_STAGE
from helpers.utils import prompt_for_ban_confirmation
from config.constants import DATABASE_PATH
from discord.utils import find
import sqlite3

class AdminCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="addstrike", description="Add a strike to a player")
    async def addstrike_cmd(self, interaction: discord.Interaction, player_name: str, in_game_id: str, reason: str):
        try:
            await interaction.response.send_message("Processing the strike...")

            if interaction.user.bot:
                return

            admin_name = str(interaction.user)
            existing_card = search_for_card(in_game_id)
            messages_to_send = []

            if existing_card:
                current_list_id = existing_card["idList"]

                if current_list_id == BANNED_LIST_ID:
                    messages_to_send.append(f"{player_name} | {in_game_id} is already banned and cannot receive more strikes.")
                else:
                    new_list_id = STRIKE_LIST_MAPPING.get(current_list_id, None)

                    if new_list_id:
                        move_success = move_card_to_list(existing_card["id"], new_list_id)
                        message = STRIKE_STAGE[new_list_id]
                        formatted_message = f"<@{interaction.user.id}> - Issued a {message} for {player_name} | {in_game_id}"
                        messages_to_send.append(formatted_message)

                        added_description = f"Admin: {admin_name}\nRule break - {reason}"
                        update_success = update_card_description(existing_card["id"], added_description)
                        success = move_success and update_success

                        if not success:
                            messages_to_send.append("Failed to move or update card.")

                        third_strike_id = next(key for key, value in STRIKE_STAGE.items() if value == "**3rd Strike**")

                        if new_list_id == third_strike_id:
                            messages_to_send.append(f"⚠️ {player_name} | {in_game_id} needs to be banned! ⚠️")
                            await interaction.followup.send('\n'.join(messages_to_send))
                            messages_to_send = []  

                            banned_in_game = await prompt_for_ban_confirmation(self.bot, interaction, player_name, in_game_id)

                            if banned_in_game:
                                move_success = move_card_to_list(existing_card["id"], BANNED_LIST_ID)
                                if move_success:
                                    await interaction.followup.send(f"{player_name} | {in_game_id} has been moved to banned list after in-game ban confirmation.")
                                else:
                                    await interaction.followup.send("Failed to ban the player.")
                            else:
                                await interaction.followup.send(f"{player_name} | {in_game_id} will remain on hold until banned in-game.")
                            return
                    else:
                        messages_to_send.append("Unexpected error. Failed to add strike.")
            else:
                success = add_strike_to_trello(player_name, in_game_id, admin_name, reason)
                if success:
                    new_list_id = TRELLO_LIST_ID
                    message = STRIKE_STAGE[new_list_id]
                    formatted_message = f"<@{interaction.user.id}> - Issued a {message} for {player_name} | {in_game_id}"
                    messages_to_send.append(formatted_message)
                else:
                    messages_to_send.append("Failed to add strike to Trello.")

            for msg in messages_to_send:
                await interaction.followup.send(msg)

            try:
                with sqlite3.connect(DATABASE_PATH) as conn:
                    c = conn.cursor()
                    c.execute("SELECT username FROM players WHERE playerid=?", (in_game_id,))
                    result = c.fetchone()
                    if result:
                        discord_username = result[0]
                        guild = interaction.guild
                        user = find(lambda m: str(m) == discord_username, guild.members)
                        if user:
                            try:
                                await user.send(f"You have received a strike for the following reason:\n{reason}")
                            except discord.Forbidden:
                                print(f"Could not send DM to user {user.name}.")
            except Exception as e:
                print(f"Error in notifying user about strike: {e}")

        except Exception as e:
            print(f"An error occurred in addstrike_cmd: {e}")
            await interaction.followup.send("An unexpected error occurred while processing the strike. Please try again later.")

async def setup(bot: commands.Bot):
    await bot.add_cog(AdminCommands(bot))
