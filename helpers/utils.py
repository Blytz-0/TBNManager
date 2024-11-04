# helpers/utils.py
import discord
import asyncio

async def prompt_for_ban_confirmation(bot, interaction, player_name, in_game_id):
    # Send a message asking for confirmation
    await interaction.followup.send(f"Has {player_name} | {in_game_id} been banned in game? Confirm with 'yes' or 'no'.")
    
    def check(m):
        return m.author == interaction.user and m.content.lower() in ['yes', 'no']
    
    try:
        response_message = await bot.wait_for('message', timeout=60.0, check=check)
        return response_message.content.lower() == 'yes'
    except asyncio.TimeoutError:
        await interaction.followup.send(f"No confirmed response received. {player_name} | {in_game_id} awaits in-game ban confirmation.")
        return None
