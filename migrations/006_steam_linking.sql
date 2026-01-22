-- Migration 006: Steam ID Linking
-- Description: Adds Steam ID support alongside Alderon ID for player passport system
-- Date: 2026-01-22

USE tbnmanager;

-- ============================================
-- EXPAND PLAYERS TABLE FOR STEAM SUPPORT
-- ============================================

-- Make Alderon ID nullable (players can have Steam only, Alderon only, or both)
ALTER TABLE players
    MODIFY player_id VARCHAR(20) NULL,
    MODIFY player_name VARCHAR(255) NULL;

-- Add Steam ID columns
ALTER TABLE players
    ADD COLUMN steam_id VARCHAR(20) NULL AFTER player_name,
    ADD COLUMN steam_name VARCHAR(100) NULL AFTER steam_id;

-- Add verification columns (for future RCON verification)
ALTER TABLE players
    ADD COLUMN verified_at TIMESTAMP NULL AFTER steam_name,
    ADD COLUMN verification_method ENUM('manual', 'steam_api', 'rcon') NULL AFTER verified_at;

-- Add unique constraint for Steam ID (one Steam ID per guild)
ALTER TABLE players
    ADD UNIQUE KEY unique_guild_steam_id (guild_id, steam_id);

-- ============================================
-- GUILD SETTINGS FOR REQUIRED IDS
-- ============================================

-- Add required_ids setting to guilds table
ALTER TABLE guilds
    ADD COLUMN required_ids ENUM('none', 'alderon', 'steam', 'any', 'both') DEFAULT 'none';

-- ============================================
-- MIGRATION NOTES
-- ============================================
-- Players table now supports:
--   - Discord-only registration (no game IDs)
--   - Alderon ID only (Path of Titans players)
--   - Steam ID only (The Isle players)
--   - Both Alderon and Steam IDs
--
-- Servers can configure required_ids to enforce:
--   - 'none': No ID required (default)
--   - 'alderon': Must link Alderon ID
--   - 'steam': Must link Steam ID
--   - 'any': Must link at least one game ID
--   - 'both': Must link both Alderon and Steam IDs
--
-- Future RCON verification:
--   - verified_at: When full verification completed via RCON
--   - verification_method: How the account was verified
--     - 'manual': Admin manually verified
--     - 'steam_api': Validated via Steam Web API
--     - 'rcon': Verified via in-game RCON code

SELECT 'Migration 006 completed: Steam ID linking support added' AS status;
