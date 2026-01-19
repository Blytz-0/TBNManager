# bot.py
"""
TBNManager Discord Bot - Entry Point

A modular Discord bot for server administration and moderation.
Supports multi-guild deployment with per-server configuration.
"""

import discord
from discord.ext import commands
from config.settings import TOKEN, LOG_LEVEL, TEST_GUILD_ID
from database.connection import test_connection, close_pool
from database.queries import GuildQueries
import logging
import asyncio

# Configure logging
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Bot configuration
intents = discord.Intents.default()
intents.message_content = True
intents.members = True  # Required for member lookup
intents.guilds = True   # Required for guild events

bot = commands.Bot(
    command_prefix='/',
    intents=intents,
    description="TBNManager - Server Administration Bot"
)

# List of cogs to load
COGS = [
    # Player commands
    'cogs.player.linking',
    'cogs.player.roles',

    # Admin commands
    'cogs.admin.strikes',
    'cogs.admin.moderation',
    'cogs.admin.config',
    'cogs.admin.tickets',
]


async def load_cogs():
    """Load all cogs before the bot starts."""
    for cog in COGS:
        try:
            await bot.load_extension(cog)
            logger.info(f"Loaded cog: {cog}")
        except Exception as e:
            logger.error(f"Failed to load cog {cog}: {e}")


@bot.event
async def on_ready():
    """Called when bot is ready and connected."""
    logger.info(f"Logged in as {bot.user.name} (ID: {bot.user.id})")
    logger.info(f"Connected to {len(bot.guilds)} guild(s)")

    # Test database connection
    if test_connection():
        logger.info("Database connection successful")
    else:
        logger.error("Database connection FAILED - some features may not work")

    # Sync commands (cogs already loaded in main())
    try:
        if TEST_GUILD_ID:
            # Guild-specific sync for instant updates during development
            test_guild = discord.Object(id=TEST_GUILD_ID)

            # Clear global commands first (prevents duplicates)
            bot.tree.clear_commands(guild=None)
            await bot.tree.sync()  # Sync empty global tree
            logger.info("Cleared global commands")

            # Copy global commands to the guild for instant sync
            bot.tree.copy_global_to(guild=test_guild)
            synced = await bot.tree.sync(guild=test_guild)
            logger.info(f"Synced {len(synced)} command(s) to test guild {TEST_GUILD_ID}")
        else:
            # Global sync (takes up to an hour to propagate)
            synced = await bot.tree.sync()
            logger.info(f"Synced {len(synced)} global command(s)")

    except Exception as e:
        logger.error(f"Failed to sync commands: {e}")

    # Set bot status
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.watching,
            name=f"{len(bot.guilds)} servers"
        )
    )


@bot.event
async def on_guild_join(guild: discord.Guild):
    """Called when bot joins a new guild."""
    logger.info(f"Joined new guild: {guild.name} (ID: {guild.id})")

    # Register guild in database
    try:
        GuildQueries.get_or_create(guild.id, guild.name)
        logger.info(f"Registered guild {guild.name} in database")
    except Exception as e:
        logger.error(f"Failed to register guild {guild.name}: {e}")

    # Update presence
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.watching,
            name=f"{len(bot.guilds)} servers"
        )
    )


@bot.event
async def on_guild_remove(guild: discord.Guild):
    """Called when bot is removed from a guild."""
    logger.info(f"Left guild: {guild.name} (ID: {guild.id})")

    # Note: We don't delete guild data immediately in case they re-add the bot
    # Data cleanup can be done via a scheduled task for guilds inactive for X days

    # Update presence
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.watching,
            name=f"{len(bot.guilds)} servers"
        )
    )


@bot.event
async def on_command_error(ctx, error):
    """Global error handler for command errors."""
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("You don't have permission to use this command.", ephemeral=True)
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"Missing required argument: {error.param.name}", ephemeral=True)
    elif isinstance(error, commands.CommandNotFound):
        pass  # Ignore unknown commands
    else:
        logger.error(f"Command error: {error}", exc_info=True)


@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error):
    """Global error handler for app (slash) command errors."""
    logger.error(f"App command error in {interaction.command}: {error}", exc_info=True)

    try:
        if interaction.response.is_done():
            await interaction.followup.send(
                "An error occurred while processing your command.",
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                "An error occurred while processing your command.",
                ephemeral=True
            )
    except Exception:
        pass  # Couldn't send error message


async def main():
    """Main entry point."""
    logger.info("Starting TBNManager bot...")

    try:
        # Load cogs BEFORE starting the bot so commands are registered
        await load_cogs()

        async with bot:
            await bot.start(TOKEN)
    except KeyboardInterrupt:
        logger.info("Shutdown requested...")
    finally:
        # Cleanup
        close_pool()
        logger.info("Bot shutdown complete")


if __name__ == "__main__":
    asyncio.run(main())
