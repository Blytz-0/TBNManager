# services/steam_api.py
"""
Steam Web API integration for player verification.

Provides Steam ID validation and player profile lookup using the Steam Web API.
Requires STEAM_API_KEY to be set in environment variables.
"""

import aiohttp
import re
import logging
from config.settings import STEAM_API_KEY

logger = logging.getLogger(__name__)

# Steam API endpoints
STEAM_API_BASE = "https://api.steampowered.com"
GET_PLAYER_SUMMARIES = f"{STEAM_API_BASE}/ISteamUser/GetPlayerSummaries/v2/"
RESOLVE_VANITY_URL = f"{STEAM_API_BASE}/ISteamUser/ResolveVanityURL/v1/"

# Steam ID format: 17 digit number (64-bit Steam ID)
STEAM_ID_PATTERN = re.compile(r'^\d{17}$')


class SteamAPIError(Exception):
    """Raised when Steam API call fails."""
    pass


class SteamAPI:
    """Steam Web API client for player verification."""

    @staticmethod
    def is_configured() -> bool:
        """Check if Steam API key is configured."""
        return bool(STEAM_API_KEY)

    @staticmethod
    def is_valid_steam_id_format(steam_id: str) -> bool:
        """
        Check if string matches Steam ID format (17 digits).

        Args:
            steam_id: The Steam ID to validate

        Returns:
            True if format is valid, False otherwise
        """
        return bool(STEAM_ID_PATTERN.match(steam_id))

    @staticmethod
    async def resolve_vanity_url(vanity_name: str) -> str | None:
        """
        Resolve a Steam vanity URL to a Steam ID.

        Args:
            vanity_name: The vanity URL name (e.g., 'gabelogannewell')

        Returns:
            Steam ID (17 digits) if found, None otherwise
        """
        if not STEAM_API_KEY:
            logger.warning("Steam API key not configured")
            return None

        try:
            async with aiohttp.ClientSession() as session:
                params = {
                    'key': STEAM_API_KEY,
                    'vanityurl': vanity_name
                }
                async with session.get(RESOLVE_VANITY_URL, params=params) as response:
                    if response.status != 200:
                        logger.error(f"Steam API error: {response.status}")
                        return None

                    data = await response.json()
                    result = data.get('response', {})

                    if result.get('success') == 1:
                        return result.get('steamid')
                    return None

        except Exception as e:
            logger.error(f"Error resolving vanity URL: {e}")
            return None

    @staticmethod
    async def get_player_summary(steam_id: str) -> dict | None:
        """
        Get player profile information from Steam.

        Args:
            steam_id: The 64-bit Steam ID (17 digits)

        Returns:
            Dict with player info or None if not found:
            {
                'steam_id': '76561199003854357',
                'personaname': 'PlayerName',
                'profileurl': 'https://steamcommunity.com/id/...',
                'avatar': 'https://...',
                'avatarmedium': 'https://...',
                'avatarfull': 'https://...',
                'personastate': 1,  # 0=Offline, 1=Online, etc.
                'communityvisibilitystate': 3,  # 1=Private, 3=Public
            }
        """
        if not STEAM_API_KEY:
            logger.warning("Steam API key not configured")
            return None

        if not SteamAPI.is_valid_steam_id_format(steam_id):
            logger.warning(f"Invalid Steam ID format: {steam_id}")
            return None

        try:
            async with aiohttp.ClientSession() as session:
                params = {
                    'key': STEAM_API_KEY,
                    'steamids': steam_id
                }
                async with session.get(GET_PLAYER_SUMMARIES, params=params) as response:
                    if response.status != 200:
                        logger.error(f"Steam API error: {response.status}")
                        return None

                    data = await response.json()
                    players = data.get('response', {}).get('players', [])

                    if players:
                        player = players[0]
                        return {
                            'steam_id': player.get('steamid'),
                            'personaname': player.get('personaname'),
                            'profileurl': player.get('profileurl'),
                            'avatar': player.get('avatar'),
                            'avatarmedium': player.get('avatarmedium'),
                            'avatarfull': player.get('avatarfull'),
                            'personastate': player.get('personastate', 0),
                            'communityvisibilitystate': player.get('communityvisibilitystate', 1),
                        }
                    return None

        except Exception as e:
            logger.error(f"Error fetching player summary: {e}")
            return None

    @staticmethod
    async def validate_steam_id(steam_id_or_url: str) -> dict | None:
        """
        Validate and resolve a Steam ID or vanity URL.

        Accepts:
        - 17-digit Steam ID: '76561199003854357'
        - Vanity URL name: 'gabelogannewell'
        - Full profile URL: 'https://steamcommunity.com/id/gabelogannewell'
        - Full profile URL with ID: 'https://steamcommunity.com/profiles/76561199003854357'

        Args:
            steam_id_or_url: Steam ID, vanity name, or profile URL

        Returns:
            Player summary dict if valid, None otherwise
        """
        steam_id = steam_id_or_url.strip()

        # Extract from full profile URL
        if 'steamcommunity.com' in steam_id:
            # /profiles/76561199003854357
            if '/profiles/' in steam_id:
                match = re.search(r'/profiles/(\d{17})', steam_id)
                if match:
                    steam_id = match.group(1)
            # /id/vanityname
            elif '/id/' in steam_id:
                match = re.search(r'/id/([^/]+)', steam_id)
                if match:
                    vanity = match.group(1)
                    resolved = await SteamAPI.resolve_vanity_url(vanity)
                    if resolved:
                        steam_id = resolved
                    else:
                        return None

        # If not a valid Steam ID format, try as vanity URL
        if not SteamAPI.is_valid_steam_id_format(steam_id):
            resolved = await SteamAPI.resolve_vanity_url(steam_id)
            if resolved:
                steam_id = resolved
            else:
                return None

        # Now we should have a valid Steam ID, get player summary
        return await SteamAPI.get_player_summary(steam_id)
