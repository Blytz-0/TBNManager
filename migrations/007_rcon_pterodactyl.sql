-- Migration 007: RCON & Pterodactyl Integration
-- Description: Adds tables for RCON server management, Pterodactyl control, and log monitoring
-- Date: 2026-01-22
-- Note: These are PREMIUM features

USE tbnmanager;

-- ============================================
-- RCON SERVERS
-- ============================================
-- Stores RCON connection credentials for game servers
-- Each guild can have multiple servers (e.g., "The Isle Server 1", "PoT Main")

CREATE TABLE IF NOT EXISTS rcon_servers (
    id INT AUTO_INCREMENT PRIMARY KEY,
    guild_id BIGINT UNSIGNED NOT NULL,
    server_name VARCHAR(100) NOT NULL,
    game_type ENUM('path_of_titans', 'the_isle_evrima') NOT NULL,
    host VARCHAR(255) NOT NULL,
    port INT NOT NULL DEFAULT 8888,
    password VARCHAR(512) NOT NULL,
    is_default BOOLEAN DEFAULT FALSE,
    is_active BOOLEAN DEFAULT TRUE,
    last_connected_at TIMESTAMP NULL,
    last_error TEXT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    INDEX idx_guild_id (guild_id),
    UNIQUE KEY unique_guild_server_name (guild_id, server_name),
    FOREIGN KEY (guild_id) REFERENCES guilds(guild_id) ON DELETE CASCADE
);

-- ============================================
-- PTERODACTYL CONNECTIONS
-- ============================================
-- Stores Pterodactyl panel API credentials
-- One API key can access multiple servers (auto-discovered via API)

CREATE TABLE IF NOT EXISTS pterodactyl_connections (
    id INT AUTO_INCREMENT PRIMARY KEY,
    guild_id BIGINT UNSIGNED NOT NULL,
    connection_name VARCHAR(100) NOT NULL,
    panel_url VARCHAR(512) NOT NULL,
    api_key VARCHAR(512) NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    last_connected_at TIMESTAMP NULL,
    last_error TEXT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    INDEX idx_guild_id (guild_id),
    UNIQUE KEY unique_guild_connection_name (guild_id, connection_name),
    FOREIGN KEY (guild_id) REFERENCES guilds(guild_id) ON DELETE CASCADE
);

-- ============================================
-- PTERODACTYL SERVERS (discovered from API)
-- ============================================
-- Caches servers discovered from Pterodactyl API
-- Linked to a pterodactyl_connection

CREATE TABLE IF NOT EXISTS pterodactyl_servers (
    id INT AUTO_INCREMENT PRIMARY KEY,
    connection_id INT NOT NULL,
    guild_id BIGINT UNSIGNED NOT NULL,
    server_id VARCHAR(50) NOT NULL,
    server_name VARCHAR(255) NOT NULL,
    server_uuid VARCHAR(36) NULL,
    game_type ENUM('path_of_titans', 'the_isle_evrima', 'unknown') DEFAULT 'unknown',
    is_default BOOLEAN DEFAULT FALSE,
    is_active BOOLEAN DEFAULT TRUE,
    last_status VARCHAR(50) NULL,
    last_synced_at TIMESTAMP NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    INDEX idx_guild_id (guild_id),
    INDEX idx_connection_id (connection_id),
    UNIQUE KEY unique_connection_server (connection_id, server_id),
    FOREIGN KEY (connection_id) REFERENCES pterodactyl_connections(id) ON DELETE CASCADE,
    FOREIGN KEY (guild_id) REFERENCES guilds(guild_id) ON DELETE CASCADE
);

-- ============================================
-- SFTP LOG CONFIGURATION
-- ============================================
-- SFTP credentials for reading game logs (chat, kills, admin)
-- Linked to either an RCON server or Pterodactyl server

CREATE TABLE IF NOT EXISTS server_sftp_config (
    id INT AUTO_INCREMENT PRIMARY KEY,
    guild_id BIGINT UNSIGNED NOT NULL,
    rcon_server_id INT NULL,
    pterodactyl_server_id INT NULL,
    config_name VARCHAR(100) NOT NULL,
    game_type ENUM('path_of_titans', 'the_isle_evrima') DEFAULT 'the_isle_evrima',
    host VARCHAR(255) NOT NULL,
    port INT NOT NULL DEFAULT 22,
    username VARCHAR(100) NOT NULL,
    password VARCHAR(512) NOT NULL,
    chat_log_path VARCHAR(512) NULL,
    kill_log_path VARCHAR(512) NULL,
    admin_log_path VARCHAR(512) NULL,
    game_ini_path VARCHAR(512) NULL,
    is_active BOOLEAN DEFAULT TRUE,
    last_connected_at TIMESTAMP NULL,
    last_error TEXT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    INDEX idx_guild_id (guild_id),
    INDEX idx_rcon_server_id (rcon_server_id),
    INDEX idx_pterodactyl_server_id (pterodactyl_server_id),
    UNIQUE KEY unique_guild_config_name (guild_id, config_name),
    FOREIGN KEY (guild_id) REFERENCES guilds(guild_id) ON DELETE CASCADE,
    FOREIGN KEY (rcon_server_id) REFERENCES rcon_servers(id) ON DELETE SET NULL,
    FOREIGN KEY (pterodactyl_server_id) REFERENCES pterodactyl_servers(id) ON DELETE SET NULL
);

-- ============================================
-- LOG MONITORING STATE
-- ============================================
-- Tracks file positions for incremental log reading

CREATE TABLE IF NOT EXISTS log_monitor_state (
    id INT AUTO_INCREMENT PRIMARY KEY,
    sftp_config_id INT NOT NULL,
    log_type ENUM('chat', 'kill', 'admin') NOT NULL,
    file_path VARCHAR(512) NOT NULL,
    last_position BIGINT DEFAULT 0,
    last_line_hash VARCHAR(64) NULL,
    last_read_at TIMESTAMP NULL,

    UNIQUE KEY unique_config_log_type (sftp_config_id, log_type),
    FOREIGN KEY (sftp_config_id) REFERENCES server_sftp_config(id) ON DELETE CASCADE
);

-- ============================================
-- GUILD LOG CHANNELS
-- ============================================
-- Discord channel assignments for log feeds

CREATE TABLE IF NOT EXISTS guild_log_channels (
    guild_id BIGINT UNSIGNED PRIMARY KEY,
    chatlog_channel_id BIGINT UNSIGNED NULL,
    killfeed_channel_id BIGINT UNSIGNED NULL,
    adminlog_channel_id BIGINT UNSIGNED NULL,
    link_channel_id BIGINT UNSIGNED NULL,
    restart_channel_id BIGINT UNSIGNED NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    FOREIGN KEY (guild_id) REFERENCES guilds(guild_id) ON DELETE CASCADE
);

-- ============================================
-- RCON VERIFICATION CODES
-- ============================================
-- Temporary codes for in-game verification

CREATE TABLE IF NOT EXISTS rcon_verification_codes (
    id INT AUTO_INCREMENT PRIMARY KEY,
    guild_id BIGINT UNSIGNED NOT NULL,
    user_id BIGINT UNSIGNED NOT NULL,
    verification_code VARCHAR(10) NOT NULL,
    game_type ENUM('path_of_titans', 'the_isle_evrima') NOT NULL,
    target_steam_id VARCHAR(20) NULL,
    target_alderon_id VARCHAR(20) NULL,
    server_id INT NULL,
    attempts INT DEFAULT 0,
    max_attempts INT DEFAULT 3,
    expires_at TIMESTAMP NOT NULL,
    verified_at TIMESTAMP NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    INDEX idx_guild_user (guild_id, user_id),
    INDEX idx_code (verification_code),
    INDEX idx_expires (expires_at),
    FOREIGN KEY (guild_id) REFERENCES guilds(guild_id) ON DELETE CASCADE,
    FOREIGN KEY (server_id) REFERENCES rcon_servers(id) ON DELETE SET NULL
);

-- ============================================
-- RCON COMMAND LOG
-- ============================================
-- Audit trail for all RCON commands

CREATE TABLE IF NOT EXISTS rcon_command_log (
    id INT AUTO_INCREMENT PRIMARY KEY,
    guild_id BIGINT UNSIGNED NOT NULL,
    server_id INT NULL,
    command_type ENUM('kick', 'ban', 'unban', 'announce', 'dm', 'save', 'players', 'custom') NOT NULL,
    target_player_id VARCHAR(50) NULL,
    executed_by_id BIGINT UNSIGNED NOT NULL,
    command_data JSON NULL,
    success BOOLEAN NOT NULL,
    response_message TEXT NULL,
    executed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    INDEX idx_guild_id (guild_id),
    INDEX idx_server_id (server_id),
    INDEX idx_executed_by (executed_by_id),
    INDEX idx_executed_at (executed_at),
    FOREIGN KEY (guild_id) REFERENCES guilds(guild_id) ON DELETE CASCADE,
    FOREIGN KEY (server_id) REFERENCES rcon_servers(id) ON DELETE SET NULL
);

-- ============================================
-- GUILD RCON SETTINGS
-- ============================================
-- Per-guild RCON/Pterodactyl configuration

CREATE TABLE IF NOT EXISTS guild_rcon_settings (
    guild_id BIGINT UNSIGNED PRIMARY KEY,
    -- Auto-enforcement settings
    auto_kick_enabled BOOLEAN DEFAULT FALSE,
    auto_kick_strike_threshold INT DEFAULT 2,
    auto_ban_enabled BOOLEAN DEFAULT FALSE,
    auto_ban_strike_threshold INT DEFAULT 3,
    -- Verification settings
    verification_enabled BOOLEAN DEFAULT TRUE,
    verification_timeout_minutes INT DEFAULT 10,
    -- Log monitoring settings
    log_monitoring_enabled BOOLEAN DEFAULT FALSE,
    log_poll_interval_seconds INT DEFAULT 30,
    max_log_monitors INT DEFAULT 5,
    -- Pterodactyl access control
    ptero_whitelist_role_id BIGINT UNSIGNED NULL,
    -- Timestamps
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    FOREIGN KEY (guild_id) REFERENCES guilds(guild_id) ON DELETE CASCADE
);

-- ============================================
-- MIGRATION NOTES
-- ============================================
-- This migration adds support for:
--
-- RCON Integration (Premium):
--   - Multiple game servers per guild
--   - Support for Path of Titans (Source RCON) and The Isle Evrima (binary protocol)
--   - Auto-kick/ban when strike thresholds reached
--   - In-game verification via RCON messages
--   - Full audit trail of all RCON commands
--
-- Pterodactyl Integration (Premium):
--   - Connect to Pterodactyl panels
--   - Auto-discover servers from API
--   - Power control, file editing, console access
--
-- Log Monitoring (Premium):
--   - SFTP connection for reading game logs
--   - Chat, kill, and admin log feeds to Discord
--   - Incremental reading (only new lines)
--
-- Security:
--   - All passwords/API keys stored as plain text (database security at infrastructure level)
--   - Role-based access control for dangerous commands
--   - Audit logging for all RCON commands

SELECT 'Migration 007 completed: RCON & Pterodactyl integration tables created' AS status;
