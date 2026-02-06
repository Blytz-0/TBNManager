-- Migration 014: Add Strikes Logging Channel
-- Adds strikes_channel_id to guild_log_channels for automatic strike logging

ALTER TABLE guild_log_channels
    ADD COLUMN strikes_channel_id BIGINT UNSIGNED NULL COMMENT 'Channel for logging all strikes and bans';

-- Migration complete
