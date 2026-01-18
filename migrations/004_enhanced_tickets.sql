-- TBNManager Database Migration
-- Version: 1.3.0
-- Description: Enhanced ticket system with multi-button panels and reference IDs

USE tbnmanager;

-- ============================================
-- ADD REFERENCE IDS TO STRIKES AND BANS
-- ============================================

-- Add reference_id to strikes for appeal tracking
ALTER TABLE strikes
    ADD COLUMN reference_id VARCHAR(12) NULL AFTER id,
    ADD UNIQUE INDEX idx_reference_id (reference_id);

-- Add reference_id to bans
ALTER TABLE bans
    ADD COLUMN reference_id VARCHAR(12) NULL AFTER id,
    ADD UNIQUE INDEX idx_ban_reference_id (reference_id);

-- ============================================
-- TICKET BUTTON TYPES (Templates)
-- ============================================

-- Store different button types/templates for ticket panels
CREATE TABLE IF NOT EXISTS ticket_button_types (
    id INT AUTO_INCREMENT PRIMARY KEY,
    panel_id INT NOT NULL,
    button_label VARCHAR(80) NOT NULL,
    button_emoji VARCHAR(50) NULL,
    button_style INT DEFAULT 1,  -- 1=Primary, 2=Secondary, 3=Success, 4=Danger
    button_order INT DEFAULT 0,  -- Display order

    -- Form fields (what to ask users before creating ticket)
    form_title VARCHAR(45) NOT NULL DEFAULT 'Open Ticket',
    form_fields JSON NULL,  -- Array of field definitions

    -- Template for welcome message in ticket
    welcome_template TEXT NULL,

    -- Ticket channel naming pattern
    channel_name_pattern VARCHAR(100) DEFAULT 'ticket-{number}',

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (panel_id) REFERENCES ticket_panels(id) ON DELETE CASCADE,
    INDEX idx_panel_buttons (panel_id, button_order)
);

-- ============================================
-- UPDATE TICKETS TABLE
-- ============================================

-- Add fields for form responses and appeal references
ALTER TABLE tickets
    ADD COLUMN button_type_id INT NULL AFTER panel_id,
    ADD COLUMN form_responses JSON NULL AFTER subject,
    ADD COLUMN appeal_reference_id VARCHAR(12) NULL AFTER form_responses,
    ADD FOREIGN KEY (button_type_id) REFERENCES ticket_button_types(id) ON DELETE SET NULL;

-- ============================================
-- SAMPLE FORM FIELD FORMAT
-- ============================================
-- form_fields JSON example:
-- [
--   {
--     "name": "player_id",
--     "label": "Your Player ID",
--     "placeholder": "XXX-XXX-XXX",
--     "required": true,
--     "style": "short"  -- "short" or "long"
--   },
--   {
--     "name": "reason",
--     "label": "Reason for Appeal",
--     "placeholder": "Explain why you believe this action was unfair...",
--     "required": true,
--     "style": "long"
--   }
-- ]

-- ============================================
-- HELPER FUNCTION FOR REFERENCE IDS
-- ============================================

-- Generate a unique reference ID (8 chars alphanumeric)
DELIMITER //
CREATE FUNCTION IF NOT EXISTS generate_reference_id()
RETURNS VARCHAR(12)
NOT DETERMINISTIC
BEGIN
    DECLARE ref_id VARCHAR(12);
    DECLARE chars VARCHAR(36) DEFAULT 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789';
    DECLARE i INT DEFAULT 1;

    SET ref_id = '';
    WHILE i <= 8 DO
        SET ref_id = CONCAT(ref_id, SUBSTRING(chars, FLOOR(1 + RAND() * 32), 1));
        SET i = i + 1;
    END WHILE;

    RETURN ref_id;
END //
DELIMITER ;

-- ============================================
-- TRIGGER TO AUTO-GENERATE REFERENCE IDS
-- ============================================

DELIMITER //
CREATE TRIGGER IF NOT EXISTS before_strike_insert
BEFORE INSERT ON strikes
FOR EACH ROW
BEGIN
    IF NEW.reference_id IS NULL THEN
        SET NEW.reference_id = generate_reference_id();
    END IF;
END //

CREATE TRIGGER IF NOT EXISTS before_ban_insert
BEFORE INSERT ON bans
FOR EACH ROW
BEGIN
    IF NEW.reference_id IS NULL THEN
        SET NEW.reference_id = generate_reference_id();
    END IF;
END //
DELIMITER ;

-- ============================================
-- BACKFILL EXISTING RECORDS WITH REFERENCE IDS
-- ============================================

UPDATE strikes SET reference_id = generate_reference_id() WHERE reference_id IS NULL;
UPDATE bans SET reference_id = generate_reference_id() WHERE reference_id IS NULL;

SELECT 'Migration 004 complete - enhanced ticket system with reference IDs!' AS status;
