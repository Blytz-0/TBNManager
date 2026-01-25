-- Migration 008: Remove Encryption from Credential Storage (MySQL 5.7 compatible)
-- Description: Simplifies credential storage by using plain text instead of encryption
-- Date: 2026-01-24
-- Note: Database security should be handled at infrastructure level

USE tbnmanager;

-- ============================================
-- RCON SERVERS - Remove encryption
-- ============================================
-- Check if password_encrypted exists, drop it if so
-- Then add password column if it doesn't exist

-- First, check current structure and handle accordingly
-- If password_encrypted exists, we need to drop it and add password
SET @col_exists = (SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
                   WHERE TABLE_SCHEMA = 'tbnmanager'
                   AND TABLE_NAME = 'rcon_servers'
                   AND COLUMN_NAME = 'password_encrypted');

-- Drop encrypted column if it exists
SET @sql = IF(@col_exists > 0,
              'ALTER TABLE rcon_servers DROP COLUMN password_encrypted',
              'SELECT 1');
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- Check if password column exists
SET @pwd_exists = (SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
                   WHERE TABLE_SCHEMA = 'tbnmanager'
                   AND TABLE_NAME = 'rcon_servers'
                   AND COLUMN_NAME = 'password');

-- Add password column if it doesn't exist
SET @sql = IF(@pwd_exists = 0,
              'ALTER TABLE rcon_servers ADD COLUMN password VARCHAR(255) NOT NULL DEFAULT "" AFTER port',
              'SELECT 1');
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- ============================================
-- PTERODACTYL CONNECTIONS - Remove encryption
-- ============================================
SET @col_exists = (SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
                   WHERE TABLE_SCHEMA = 'tbnmanager'
                   AND TABLE_NAME = 'pterodactyl_connections'
                   AND COLUMN_NAME = 'api_key_encrypted');

SET @sql = IF(@col_exists > 0,
              'ALTER TABLE pterodactyl_connections DROP COLUMN api_key_encrypted',
              'SELECT 1');
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @key_exists = (SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
                   WHERE TABLE_SCHEMA = 'tbnmanager'
                   AND TABLE_NAME = 'pterodactyl_connections'
                   AND COLUMN_NAME = 'api_key');

SET @sql = IF(@key_exists = 0,
              'ALTER TABLE pterodactyl_connections ADD COLUMN api_key VARCHAR(255) NOT NULL DEFAULT "" AFTER panel_url',
              'SELECT 1');
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- ============================================
-- SFTP CONFIG - Remove encryption
-- ============================================
SET @col_exists = (SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
                   WHERE TABLE_SCHEMA = 'tbnmanager'
                   AND TABLE_NAME = 'server_sftp_config'
                   AND COLUMN_NAME = 'password_encrypted');

SET @sql = IF(@col_exists > 0,
              'ALTER TABLE server_sftp_config DROP COLUMN password_encrypted',
              'SELECT 1');
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @pwd_exists = (SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
                   WHERE TABLE_SCHEMA = 'tbnmanager'
                   AND TABLE_NAME = 'server_sftp_config'
                   AND COLUMN_NAME = 'password');

SET @sql = IF(@pwd_exists = 0,
              'ALTER TABLE server_sftp_config ADD COLUMN password VARCHAR(255) NOT NULL DEFAULT "" AFTER username',
              'SELECT 1');
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- Add game_type column if it doesn't exist
SET @gt_exists = (SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
                  WHERE TABLE_SCHEMA = 'tbnmanager'
                  AND TABLE_NAME = 'server_sftp_config'
                  AND COLUMN_NAME = 'game_type');

SET @sql = IF(@gt_exists = 0,
              "ALTER TABLE server_sftp_config ADD COLUMN game_type ENUM('path_of_titans', 'the_isle_evrima') DEFAULT 'the_isle_evrima' AFTER password",
              'SELECT 1');
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- ============================================
-- ENCRYPTION KEYS - No longer needed
-- ============================================
DROP TABLE IF EXISTS guild_encryption_keys;

SELECT 'Migration 008 completed: Removed encryption from credential storage' AS status;
