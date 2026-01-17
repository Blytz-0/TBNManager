-- TBNManager Database Migration
-- Version: 1.1.0
-- Description: Add strike expiry columns and indexes

USE tbnmanager;

-- Add expiry columns to strikes table
ALTER TABLE strikes
    ADD COLUMN expired_at DATETIME NULL AFTER is_active,
    ADD COLUMN expiry_reason VARCHAR(50) NULL AFTER expired_at;

-- Add index for efficient expiry queries
CREATE INDEX idx_strike_expiry ON strikes(guild_id, in_game_id, is_active, created_at);

-- Update view to exclude expired strikes properly
CREATE OR REPLACE VIEW v_player_strike_counts AS
SELECT
    guild_id,
    in_game_id,
    player_name,
    COUNT(*) as strike_count,
    MAX(created_at) as last_strike_date
FROM strikes
WHERE is_active = TRUE AND expired_at IS NULL
GROUP BY guild_id, in_game_id, player_name;

SELECT 'Migration 002 complete - strike expiry columns added!' AS status;
