-- TBNManager Database Schema
-- Version: 1.0.0
-- Description: Initial schema for multi-guild Discord bot

-- Use the database
USE tbnmanager;

-- ============================================
-- CORE TABLES
-- ============================================

-- Guild (Discord server) configuration
CREATE TABLE IF NOT EXISTS guilds (
    guild_id BIGINT UNSIGNED PRIMARY KEY,
    guild_name VARCHAR(255) NOT NULL,
    is_premium BOOLEAN DEFAULT FALSE,
    premium_until DATETIME NULL,
    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

-- Per-guild feature toggles
CREATE TABLE IF NOT EXISTS guild_features (
    id INT AUTO_INCREMENT PRIMARY KEY,
    guild_id BIGINT UNSIGNED NOT NULL,
    feature_name VARCHAR(50) NOT NULL,
    enabled BOOLEAN DEFAULT TRUE,
    UNIQUE KEY unique_guild_feature (guild_id, feature_name),
    FOREIGN KEY (guild_id) REFERENCES guilds(guild_id) ON DELETE CASCADE
);

-- Admin/moderator roles per guild
CREATE TABLE IF NOT EXISTS guild_admin_roles (
    id INT AUTO_INCREMENT PRIMARY KEY,
    guild_id BIGINT UNSIGNED NOT NULL,
    role_id BIGINT UNSIGNED NOT NULL,
    permission_level INT DEFAULT 1,  -- 1=mod, 2=admin, 3=owner
    UNIQUE KEY unique_guild_role (guild_id, role_id),
    FOREIGN KEY (guild_id) REFERENCES guilds(guild_id) ON DELETE CASCADE
);

-- Channel configurations per guild
CREATE TABLE IF NOT EXISTS guild_channels (
    id INT AUTO_INCREMENT PRIMARY KEY,
    guild_id BIGINT UNSIGNED NOT NULL,
    channel_type VARCHAR(50) NOT NULL,  -- 'rules', 'announcements', 'logs', 'role_selection'
    channel_id BIGINT UNSIGNED NOT NULL,
    UNIQUE KEY unique_guild_channel_type (guild_id, channel_type),
    FOREIGN KEY (guild_id) REFERENCES guilds(guild_id) ON DELETE CASCADE
);

-- ============================================
-- PLAYER LINKING
-- ============================================

-- Player ID linking (Discord user <-> Alderon ID)
CREATE TABLE IF NOT EXISTS players (
    id INT AUTO_INCREMENT PRIMARY KEY,
    guild_id BIGINT UNSIGNED NOT NULL,
    user_id BIGINT UNSIGNED NOT NULL,
    username VARCHAR(255) NOT NULL,
    player_id VARCHAR(20) NOT NULL,  -- XXX-XXX-XXX format
    player_name VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY unique_guild_user (guild_id, user_id),
    UNIQUE KEY unique_guild_player_id (guild_id, player_id),
    FOREIGN KEY (guild_id) REFERENCES guilds(guild_id) ON DELETE CASCADE
);

-- ============================================
-- STRIKE SYSTEM (Replaces Trello)
-- ============================================

-- Strikes table
CREATE TABLE IF NOT EXISTS strikes (
    id INT AUTO_INCREMENT PRIMARY KEY,
    guild_id BIGINT UNSIGNED NOT NULL,
    user_id BIGINT UNSIGNED NULL,  -- Discord user ID (if known)
    player_name VARCHAR(255) NOT NULL,
    in_game_id VARCHAR(20) NOT NULL,
    reason TEXT NOT NULL,
    admin_id BIGINT UNSIGNED NOT NULL,
    admin_name VARCHAR(255) NOT NULL,
    strike_number INT NOT NULL,  -- 1, 2, or 3
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (guild_id) REFERENCES guilds(guild_id) ON DELETE CASCADE,
    INDEX idx_guild_ingame (guild_id, in_game_id),
    INDEX idx_guild_user (guild_id, user_id)
);

-- Bans table (for 3rd strike or manual bans)
CREATE TABLE IF NOT EXISTS bans (
    id INT AUTO_INCREMENT PRIMARY KEY,
    guild_id BIGINT UNSIGNED NOT NULL,
    user_id BIGINT UNSIGNED NULL,
    player_name VARCHAR(255) NOT NULL,
    in_game_id VARCHAR(20) NOT NULL,
    reason TEXT NOT NULL,
    banned_by_id BIGINT UNSIGNED NOT NULL,
    banned_by_name VARCHAR(255) NOT NULL,
    banned_in_game BOOLEAN DEFAULT FALSE,
    banned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    unbanned_at DATETIME NULL,
    unbanned_by_id BIGINT UNSIGNED NULL,
    FOREIGN KEY (guild_id) REFERENCES guilds(guild_id) ON DELETE CASCADE,
    INDEX idx_guild_ingame (guild_id, in_game_id),
    INDEX idx_active_bans (guild_id, unbanned_at)
);

-- ============================================
-- ROLE SYSTEM
-- ============================================

-- Role reaction messages
CREATE TABLE IF NOT EXISTS role_messages (
    id INT AUTO_INCREMENT PRIMARY KEY,
    guild_id BIGINT UNSIGNED NOT NULL,
    channel_id BIGINT UNSIGNED NOT NULL,
    message_id BIGINT UNSIGNED NOT NULL,
    role_type VARCHAR(50) NOT NULL,  -- 'gender', 'platform', 'server'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY unique_message (message_id),
    FOREIGN KEY (guild_id) REFERENCES guilds(guild_id) ON DELETE CASCADE
);

-- Emoji to role mappings for reaction roles
CREATE TABLE IF NOT EXISTS role_emoji_mappings (
    id INT AUTO_INCREMENT PRIMARY KEY,
    message_id BIGINT UNSIGNED NOT NULL,
    emoji VARCHAR(100) NOT NULL,  -- Custom emoji format or unicode
    role_id BIGINT UNSIGNED NOT NULL,
    role_name VARCHAR(100) NOT NULL,
    FOREIGN KEY (message_id) REFERENCES role_messages(message_id) ON DELETE CASCADE
);

-- ============================================
-- AUDIT LOG
-- ============================================

-- All moderation actions logged here
CREATE TABLE IF NOT EXISTS audit_log (
    id INT AUTO_INCREMENT PRIMARY KEY,
    guild_id BIGINT UNSIGNED NOT NULL,
    action_type VARCHAR(50) NOT NULL,  -- 'strike_added', 'strike_removed', 'ban', 'unban', 'config_change', etc.
    target_user_id BIGINT UNSIGNED NULL,
    target_player_name VARCHAR(255) NULL,
    performed_by_id BIGINT UNSIGNED NOT NULL,
    performed_by_name VARCHAR(255) NOT NULL,
    details JSON NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (guild_id) REFERENCES guilds(guild_id) ON DELETE CASCADE,
    INDEX idx_guild_action (guild_id, action_type),
    INDEX idx_guild_date (guild_id, created_at)
);

-- ============================================
-- DEFAULT FEATURE FLAGS
-- ============================================

-- Insert default feature definitions (reference table)
CREATE TABLE IF NOT EXISTS feature_definitions (
    feature_name VARCHAR(50) PRIMARY KEY,
    description VARCHAR(255) NOT NULL,
    is_premium BOOLEAN DEFAULT FALSE,
    default_enabled BOOLEAN DEFAULT TRUE
);

INSERT INTO feature_definitions (feature_name, description, is_premium, default_enabled) VALUES
    ('strikes', 'Strike system for player moderation', FALSE, TRUE),
    ('player_linking', 'Link Discord accounts to Alderon IDs', FALSE, TRUE),
    ('role_selection', 'Reaction-based role assignment', FALSE, TRUE),
    ('announcements', 'Announcement and posting commands', FALSE, TRUE),
    ('audit_log', 'Detailed moderation audit logging', FALSE, TRUE),
    ('auto_ban', 'Automatic ban on 3rd strike', FALSE, TRUE),
    ('dm_notifications', 'DM users when they receive strikes', FALSE, TRUE),
    ('advanced_analytics', 'Detailed statistics and reports', TRUE, FALSE),
    ('custom_branding', 'Custom embed colors and footer', TRUE, FALSE),
    ('api_access', 'REST API access for integrations', TRUE, FALSE)
ON DUPLICATE KEY UPDATE description = VALUES(description);

-- ============================================
-- VIEWS FOR COMMON QUERIES
-- ============================================

-- View: Active strikes count per player
CREATE OR REPLACE VIEW v_player_strike_counts AS
SELECT
    guild_id,
    in_game_id,
    player_name,
    COUNT(*) as strike_count,
    MAX(created_at) as last_strike_date
FROM strikes
WHERE is_active = TRUE
GROUP BY guild_id, in_game_id, player_name;

-- View: Active bans
CREATE OR REPLACE VIEW v_active_bans AS
SELECT * FROM bans WHERE unbanned_at IS NULL;

-- ============================================
-- INITIAL DATA COMPLETE
-- ============================================
SELECT 'Schema created successfully!' AS status;
