-- Migration 013: Global Passport-Based Strikes System
-- Transforms strikes from game-specific IDs to Discord user-based global enforcement
--
-- Key Changes:
-- 1. user_id becomes primary identity (required, not nullable for new strikes)
-- 2. Add source tracking (which game/platform caused the strike)
-- 3. Add categorization (type of violation)
-- 4. Add severity levels (minor vs major offenses)
-- 5. Cross-game enforcement (bans apply to all games)

-- Add new columns to strikes table
ALTER TABLE strikes
    -- Source tracking: Where did this strike originate?
    ADD COLUMN source_type VARCHAR(20) DEFAULT 'game' COMMENT 'Origin: game, discord, web, manual',
    ADD COLUMN source_id VARCHAR(100) DEFAULT NULL COMMENT 'Specific game/server/channel identifier',

    -- Categorization: What type of violation?
    ADD COLUMN category VARCHAR(50) DEFAULT 'other' COMMENT 'harassment, hate_speech, cheating, griefing, toxicity, other',

    -- Severity: How serious is this?
    ADD COLUMN severity ENUM('minor', 'major') DEFAULT 'minor' COMMENT 'Minor (warning) or Major (escalation)';

-- Add new columns to bans table (same structure)
ALTER TABLE bans
    -- Source tracking
    ADD COLUMN source_type VARCHAR(20) DEFAULT 'game' COMMENT 'Origin: game, discord, web, manual',
    ADD COLUMN source_id VARCHAR(100) DEFAULT NULL COMMENT 'Specific game/server/channel identifier',

    -- Categorization
    ADD COLUMN category VARCHAR(50) DEFAULT 'accumulated_strikes' COMMENT 'accumulated_strikes, harassment, cheating, etc.',

    -- Severity (all bans are major by definition)
    ADD COLUMN severity ENUM('minor', 'major') DEFAULT 'major' COMMENT 'Always major for bans';

-- Add indexes for new query patterns
CREATE INDEX idx_strikes_source ON strikes(guild_id, source_type, source_id);
CREATE INDEX idx_strikes_category ON strikes(guild_id, category);
CREATE INDEX idx_strikes_severity ON strikes(guild_id, severity);

CREATE INDEX idx_bans_source ON bans(guild_id, source_type, source_id);
CREATE INDEX idx_bans_category ON bans(guild_id, category);

-- Backfill source_type for existing records
-- All existing strikes are from 'game' source (Path of Titans via Alderon ID)
UPDATE strikes
SET source_type = 'game',
    source_id = 'path_of_titans',
    category = 'other'
WHERE source_type IS NULL OR source_type = 'game';

UPDATE bans
SET source_type = 'game',
    source_id = 'path_of_titans',
    category = 'accumulated_strikes'
WHERE source_type IS NULL OR source_type = 'game';

-- Note: user_id is already in the schema and allows NULL for backward compatibility
-- New strikes SHOULD have user_id populated (linked via passport system)
-- Legacy strikes may have NULL user_id if player never linked Discord

-- Migration complete
-- Next step: Update application code to populate these fields
