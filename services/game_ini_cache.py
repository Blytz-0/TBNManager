"""
Game.ini Admin Cache Manager
Efficiently caches admin lists from Game.ini to avoid excessive SFTP connections.
"""

import logging
import time
from typing import Set, Optional
import re

logger = logging.getLogger(__name__)

# Global cache: guild_id -> {admin_ids: set, timestamp: float}
_admin_cache = {}
CACHE_TTL = 300  # 5 minutes


class GameIniAdminCache:
    """Manages cached admin lists from Game.ini files."""

    @staticmethod
    def get_admin_ids(guild_id: int) -> Optional[Set[str]]:
        """
        Get cached admin Steam IDs for a guild.

        Returns:
            Set of admin Steam IDs, or None if not cached
        """
        cache_entry = _admin_cache.get(guild_id)
        if not cache_entry:
            return None

        # Check if cache is still valid
        current_time = time.time()
        if current_time - cache_entry['timestamp'] > CACHE_TTL:
            logger.debug(f"Guild {guild_id}: Admin cache expired")
            return None

        return cache_entry['admin_ids']

    @staticmethod
    def set_admin_ids(guild_id: int, admin_ids: Set[str]) -> None:
        """
        Cache admin Steam IDs for a guild.

        Args:
            guild_id: Discord guild ID
            admin_ids: Set of admin Steam IDs
        """
        _admin_cache[guild_id] = {
            'admin_ids': admin_ids,
            'timestamp': time.time()
        }
        logger.info(f"Guild {guild_id}: Cached {len(admin_ids)} admin Steam IDs")

    @staticmethod
    def is_admin(guild_id: int, steam_id: str) -> bool:
        """
        Check if a Steam ID is an admin.

        Args:
            guild_id: Discord guild ID
            steam_id: Steam ID to check

        Returns:
            True if admin, False otherwise (or if cache not available)
        """
        admin_ids = GameIniAdminCache.get_admin_ids(guild_id)
        if admin_ids is None:
            return False

        return steam_id in admin_ids

    @staticmethod
    def parse_game_ini_content(content: str) -> Set[str]:
        """
        Parse Game.ini content to extract admin Steam IDs.

        Args:
            content: Raw Game.ini file content

        Returns:
            Set of admin Steam IDs
        """
        admin_ids = set()

        for line in content.split('\n'):
            line = line.strip()
            if line.startswith('AdminsSteamIDs='):
                # Extract Steam ID from line like: AdminsSteamIDs=76561199003854357
                match = re.search(r'AdminsSteamIDs=(\d+)', line)
                if match:
                    steam_id = match.group(1)
                    admin_ids.add(steam_id)
                    logger.debug(f"Found admin Steam ID: {steam_id}")

        return admin_ids

    @staticmethod
    def clear_cache(guild_id: Optional[int] = None) -> None:
        """
        Clear admin cache.

        Args:
            guild_id: If provided, only clear cache for this guild. Otherwise clear all.
        """
        if guild_id:
            _admin_cache.pop(guild_id, None)
            logger.info(f"Cleared admin cache for guild {guild_id}")
        else:
            _admin_cache.clear()
            logger.info("Cleared all admin cache")
