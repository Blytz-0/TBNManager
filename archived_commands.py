# archived_commands.py

import discord
from discord.ext import commands
from config.constants import CHANNELS, GENDER_ROLE_EMOJIS, PLATFORM_ROLE_EMOJIS, SERVER_ROLE_EMOJIS, GENERAL_COMMANDS
import sqlite3
from config.constants import DATABASE_PATH


# Initialize bot (Only for commands referencing the bot instance)
bot = commands.Bot(command_prefix="/")


# Test command
@bot.tree.command(name="hello")
async def hello(interaction: discord.Interaction):
    await interaction.response.send_message(f"Hey {interaction.user.mention}! This is a test.", ephemeral=True)


# Role selection template functions
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


# Role selection commands
@bot.tree.command(name="chooseyourgender")
async def postgenderroles(interaction: discord.Interaction):
    await post_roles_template(interaction, GENDER_ROLE_EMOJIS, "Gender Roles")

@bot.tree.command(name="chooseyourplatform")
async def postplatformroles(interaction: discord.Interaction):
    await post_roles_template(interaction, PLATFORM_ROLE_EMOJIS, "Platform Roles")

@bot.tree.command(name="chooseyourserverroles")
async def postserverroles(interaction: discord.Interaction):
    await post_roles_template(interaction, SERVER_ROLE_EMOJIS, "Server Notification Roles")


# Reaction role assignment and removal
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
    guild = await bot.fetch_guild(payload.guild_id)
    member = await guild.fetch_member(payload.user_id)

    if member.bot:
        return

    emoji_name = str(payload.emoji)
    if emoji_name in ALL_ROLE_EMOJIS:
        role_name = ALL_ROLE_EMOJIS[emoji_name]
        role = discord.utils.get(guild.roles, name=role_name)
        
        if role and role in member.roles:
            await member.remove_roles(role)


# Announcement commands
@bot.tree.command(name="announce")
async def announce(interaction: discord.Interaction, *, args: str = None):
    if interaction.user.bot:
        return

    if not any(role.name in ["Owner", "Headadmin"] for role in interaction.user.roles):
        await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
        return

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

    if not any(role.name in ["Owner", "Headadmin"] for role in interaction.user.roles):
        await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
        return

    args = args.replace("|", "\n")
    arg_list = args.split(maxsplit=1)

    channel_name = arg_list[0] if arg_list and arg_list[0] in CHANNELS else None
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


# Rules Posting Commands
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
    footer_text = "Maintaining a welcoming and harmonious environment is everyone's responsibility."
    await post_rules_template(interaction, args, "A - GENERAL", discord.Color.blue(), footer_text)


@bot.tree.command(name="tbningamerules")
async def post_ingame_rules(interaction: discord.Interaction, *, args: str = None):
    if not args:
        await interaction.response.send_message("Please provide the rules content.", ephemeral=True)
        return
    footer_text = "Adherence to in-game rules ensures a smooth experience."
    await post_rules_template(interaction, args, "B - IN-GAME", discord.Color.orange(), footer_text)


@bot.tree.command(name="tbnstaffcommands")
async def post_staff_commands(interaction: discord.Interaction, *, args: str = None):
    if not args:
        await interaction.response.send_message("Please provide the commands content.", ephemeral=True)
        return
    footer_text = "Staff commands are tools to facilitate gameplay responsibly."
    await post_rules_template(interaction, args, "0 - STAFF", discord.Color.red(), footer_text)


@bot.tree.command(name="tbnstaffcoc")
async def post_staff_coc(interaction: discord.Interaction, *, args: str = None):
    if not args:
        await interaction.response.send_message("Please provide the code of conduct content.", ephemeral=True)
        return
    footer_text = "Our code of conduct reflects our values."
    await post_rules_template(interaction, args, "1 - CODE", discord.Color.gold(), footer_text)


# Clear Channel Messages Command
@bot.tree.command(name="clear")
async def clear(interaction: discord.Interaction):
    if interaction.user.bot:
        return

    if not any(role.name in ["Owner", "Headadmin"] for role in interaction.user.roles):
        await interaction.response.send_message("You don't have permission to use this command.")
        return

    await interaction.response.defer()

    try:
        messages_to_delete = [message async for message in interaction.channel.history(limit=100)]
        await interaction.channel.delete_messages(messages_to_delete)
        await interaction.channel.send("Messages cleared!", delete_after=5)
    except discord.Forbidden:
        await interaction.followup.send("I don't have permission to delete messages.")
    except discord.HTTPException:
        await interaction.followup.send("An error occurred while clearing messages.")


# Help Command
@bot.tree.command(name="commands")
async def _commands(interaction: discord.Interaction):
    if interaction.user.bot:
        return

    embed = discord.Embed(title="Help", description="Here's a list of my commands:", color=0x00ff00)
    embed.add_field(name="ℹ️ General", value="\n".join(GENERAL_COMMANDS), inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=True)


# Error Handling Functions
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
    with sqlite3.connect(DATABASE_PATH) as conn:
        conn.close()

@bot.event
async def on_close():
    with sqlite3.connect(DATABASE_PATH) as conn:
        conn.close()
