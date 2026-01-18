-- TBNManager Database Migration
-- Version: 1.2.0
-- Description: Add ticket system tables

USE tbnmanager;

-- ============================================
-- TICKET SYSTEM TABLES
-- ============================================

-- Ticket panels (the embed messages users click to open tickets)
CREATE TABLE IF NOT EXISTS ticket_panels (
    id INT AUTO_INCREMENT PRIMARY KEY,
    guild_id BIGINT UNSIGNED NOT NULL,
    channel_id BIGINT UNSIGNED NOT NULL,
    message_id BIGINT UNSIGNED NULL,
    title VARCHAR(255) NOT NULL DEFAULT 'Support Tickets',
    description TEXT NULL,
    button_label VARCHAR(80) DEFAULT 'Open Ticket',
    button_emoji VARCHAR(50) DEFAULT '🎫',
    ticket_category_id BIGINT UNSIGNED NULL,  -- Category where tickets are created
    transcript_channel_id BIGINT UNSIGNED NULL,  -- Where transcripts are posted
    support_role_id BIGINT UNSIGNED NULL,  -- Role that can see/manage tickets
    welcome_message TEXT NULL,  -- Message sent when ticket is opened
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (guild_id) REFERENCES guilds(guild_id) ON DELETE CASCADE,
    INDEX idx_guild_panel (guild_id)
);

-- Individual tickets
CREATE TABLE IF NOT EXISTS tickets (
    id INT AUTO_INCREMENT PRIMARY KEY,
    ticket_number INT NOT NULL,  -- Per-guild ticket number
    guild_id BIGINT UNSIGNED NOT NULL,
    channel_id BIGINT UNSIGNED NULL,  -- The ticket channel
    user_id BIGINT UNSIGNED NOT NULL,  -- Who opened the ticket
    username VARCHAR(255) NOT NULL,
    panel_id INT NULL,  -- Which panel it was opened from
    subject VARCHAR(255) NULL,
    status ENUM('open', 'claimed', 'closed') DEFAULT 'open',
    claimed_by_id BIGINT UNSIGNED NULL,
    claimed_by_name VARCHAR(255) NULL,
    claimed_at DATETIME NULL,
    closed_by_id BIGINT UNSIGNED NULL,
    closed_by_name VARCHAR(255) NULL,
    close_reason TEXT NULL,
    opened_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    closed_at DATETIME NULL,
    has_transcript BOOLEAN DEFAULT FALSE,
    transcript_message_id BIGINT UNSIGNED NULL,
    FOREIGN KEY (guild_id) REFERENCES guilds(guild_id) ON DELETE CASCADE,
    FOREIGN KEY (panel_id) REFERENCES ticket_panels(id) ON DELETE SET NULL,
    UNIQUE KEY unique_guild_ticket (guild_id, ticket_number),
    INDEX idx_guild_status (guild_id, status),
    INDEX idx_user_tickets (guild_id, user_id)
);

-- Ticket messages (for transcript generation)
CREATE TABLE IF NOT EXISTS ticket_messages (
    id INT AUTO_INCREMENT PRIMARY KEY,
    ticket_id INT NOT NULL,
    message_id BIGINT UNSIGNED NOT NULL,
    user_id BIGINT UNSIGNED NOT NULL,
    username VARCHAR(255) NOT NULL,
    content TEXT NULL,
    attachments JSON NULL,  -- Array of attachment URLs
    embeds JSON NULL,  -- Array of embed data
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    edited_at DATETIME NULL,
    deleted BOOLEAN DEFAULT FALSE,
    FOREIGN KEY (ticket_id) REFERENCES tickets(id) ON DELETE CASCADE,
    INDEX idx_ticket_messages (ticket_id, created_at)
);

-- Ticket participants (users added to the ticket)
CREATE TABLE IF NOT EXISTS ticket_participants (
    id INT AUTO_INCREMENT PRIMARY KEY,
    ticket_id INT NOT NULL,
    user_id BIGINT UNSIGNED NOT NULL,
    username VARCHAR(255) NOT NULL,
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    added_by_id BIGINT UNSIGNED NULL,
    FOREIGN KEY (ticket_id) REFERENCES tickets(id) ON DELETE CASCADE,
    UNIQUE KEY unique_ticket_user (ticket_id, user_id)
);

-- ============================================
-- HELPER FUNCTION FOR TICKET NUMBERS
-- ============================================

-- Get next ticket number for a guild
DELIMITER //
CREATE FUNCTION IF NOT EXISTS get_next_ticket_number(p_guild_id BIGINT UNSIGNED)
RETURNS INT
DETERMINISTIC
BEGIN
    DECLARE next_num INT;
    SELECT COALESCE(MAX(ticket_number), 0) + 1 INTO next_num
    FROM tickets WHERE guild_id = p_guild_id;
    RETURN next_num;
END //
DELIMITER ;

-- ============================================
-- ADD TICKET FEATURE FLAG
-- ============================================

INSERT INTO feature_definitions (feature_name, description, is_premium, default_enabled)
VALUES ('tickets', 'Support ticket system', FALSE, TRUE)
ON DUPLICATE KEY UPDATE description = VALUES(description);

SELECT 'Migration 003 complete - ticket system tables added!' AS status;
