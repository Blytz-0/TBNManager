-- Migration 008: Remove Encryption from Credential Storage
-- Description: Simplifies credential storage by using plain text instead of encryption
-- Date: 2026-01-23
-- Note: Database security should be handled at infrastructure level

USE tbnmanager;

-- ============================================
-- RCON SERVERS - Remove encryption
-- ============================================
-- First, drop the old encrypted column and add plain text column

-- Drop existing data since it can't be decrypted anyway
DELETE FROM rcon_servers;

-- Alter table to use plain password
ALTER TABLE rcon_servers
    DROP COLUMN IF EXISTS password_encrypted,
    ADD COLUMN IF NOT EXISTS password VARCHAR(255) NOT NULL AFTER port;

-- ============================================
-- PTERODACTYL CONNECTIONS - Remove encryption
-- ============================================
DELETE FROM pterodactyl_connections;

ALTER TABLE pterodactyl_connections
    DROP COLUMN IF EXISTS api_key_encrypted,
    ADD COLUMN IF NOT EXISTS api_key VARCHAR(255) NOT NULL AFTER panel_url;

-- ============================================
-- SFTP CONFIG - Remove encryption
-- ============================================
DELETE FROM server_sftp_config;

ALTER TABLE server_sftp_config
    DROP COLUMN IF EXISTS password_encrypted,
    ADD COLUMN IF NOT EXISTS password VARCHAR(255) NOT NULL AFTER username,
    ADD COLUMN IF NOT EXISTS game_type ENUM('path_of_titans', 'the_isle_evrima') DEFAULT 'the_isle_evrima' AFTER password;

-- ============================================
-- ENCRYPTION KEYS - No longer needed
-- ============================================
DROP TABLE IF EXISTS guild_encryption_keys;

-- ============================================
-- MIGRATION NOTES
-- ============================================
-- This migration removes encryption from credential storage.
-- Reasons:
--   1. Encryption was causing persistent issues with key management
--   2. Most Discord bots store credentials in plain text
--   3. Security should be handled at database/infrastructure level
--   4. Simplifies code significantly
--
-- Security recommendations:
--   - Restrict database access to bot only
--   - Use MySQL user with limited privileges
--   - Keep database on private network
--   - Use SSL for database connections

SELECT 'Migration 008 completed: Removed encryption from credential storage' AS status;
