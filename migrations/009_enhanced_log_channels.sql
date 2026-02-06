-- Migration 009: Enhanced Log Channel Configuration
-- Adds separate channel configurations for each log type

-- Step 1: Add new channel columns to guild_log_channels table
ALTER TABLE guild_log_channels
ADD COLUMN player_login_channel_id BIGINT DEFAULT NULL;

ALTER TABLE guild_log_channels
ADD COLUMN player_logout_channel_id BIGINT DEFAULT NULL;

ALTER TABLE guild_log_channels
ADD COLUMN player_chat_channel_id BIGINT DEFAULT NULL;

ALTER TABLE guild_log_channels
ADD COLUMN admin_command_channel_id BIGINT DEFAULT NULL;

ALTER TABLE guild_log_channels
ADD COLUMN player_death_channel_id BIGINT DEFAULT NULL;

ALTER TABLE guild_log_channels
ADD COLUMN rcon_command_channel_id BIGINT DEFAULT NULL;

-- Step 2: Migrate existing data
-- chatlog_channel → player_chat_channel
UPDATE guild_log_channels
SET player_chat_channel_id = chatlog_channel_id
WHERE chatlog_channel_id IS NOT NULL;

-- adminlog_channel → admin_command_channel + rcon_command_channel
UPDATE guild_log_channels
SET admin_command_channel_id = adminlog_channel_id,
    rcon_command_channel_id = adminlog_channel_id
WHERE adminlog_channel_id IS NOT NULL;

-- killfeed_channel → player_death_channel
UPDATE guild_log_channels
SET player_death_channel_id = killfeed_channel_id
WHERE killfeed_channel_id IS NOT NULL;

-- Step 3: Add indexes for faster lookups
CREATE INDEX idx_guild_log_channels_player_login
ON guild_log_channels(player_login_channel_id);

CREATE INDEX idx_guild_log_channels_player_logout
ON guild_log_channels(player_logout_channel_id);

CREATE INDEX idx_guild_log_channels_player_chat
ON guild_log_channels(player_chat_channel_id);

CREATE INDEX idx_guild_log_channels_admin_command
ON guild_log_channels(admin_command_channel_id);

CREATE INDEX idx_guild_log_channels_player_death
ON guild_log_channels(player_death_channel_id);

CREATE INDEX idx_guild_log_channels_rcon_command
ON guild_log_channels(rcon_command_channel_id);
