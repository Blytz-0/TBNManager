-- Migration 015: Track Strike Removal Details
-- Adds columns to track who removed/cleared strikes

ALTER TABLE strikes
    ADD COLUMN removed_by_id BIGINT UNSIGNED NULL COMMENT 'Discord user ID of who removed this strike',
    ADD COLUMN removed_by_name VARCHAR(255) NULL COMMENT 'Display name of who removed this strike';

-- Update expiry_reason to allow longer text
ALTER TABLE strikes
    MODIFY COLUMN expiry_reason VARCHAR(100) NULL COMMENT 'Reason for removal: manual_removal, cleared, auto_expired, etc.';

-- Migration complete
