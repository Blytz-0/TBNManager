-- Migration 005: Granular Role Permissions
-- Description: Adds per-command permission system for roles
-- Date: 2026-01-21

USE tbnmanager;

-- ============================================
-- ROLE PERMISSION SYSTEM
-- ============================================

-- Per-command permissions for each role
-- This replaces the level-based system with granular control
CREATE TABLE IF NOT EXISTS guild_role_permissions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    guild_id BIGINT UNSIGNED NOT NULL,
    role_id BIGINT UNSIGNED NOT NULL,
    command_name VARCHAR(50) NOT NULL,
    allowed BOOLEAN NOT NULL DEFAULT FALSE,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    UNIQUE KEY unique_role_command (guild_id, role_id, command_name),
    INDEX idx_guild_role (guild_id, role_id),
    INDEX idx_guild_command (guild_id, command_name),
    FOREIGN KEY (guild_id) REFERENCES guilds(guild_id) ON DELETE CASCADE
);

-- ============================================
-- MIGRATION NOTES
-- ============================================
-- The old guild_admin_roles table is kept for backward compatibility
-- during the transition period. It can be removed in a future migration
-- once all servers have migrated to the new permission system.
--
-- The new system uses a whitelist approach:
-- - Roles have no permissions until explicitly granted
-- - Server owner and Discord Administrator always have full access
-- - Multiple roles can grant access (union of permissions)

SELECT 'Migration 005 completed: Role permissions table created' AS status;
