-- Migration 010: Add SFTP file position tracking
-- Adds columns to track file reading position to prevent re-parsing old entries

ALTER TABLE server_sftp_config
ADD COLUMN last_file_position BIGINT DEFAULT 0 COMMENT 'Byte position in log file';

ALTER TABLE server_sftp_config
ADD COLUMN last_line_hash VARCHAR(32) DEFAULT NULL COMMENT 'MD5 hash of last read line';

ALTER TABLE server_sftp_config
ADD COLUMN last_parsed_at TIMESTAMP NULL COMMENT 'Last time logs were parsed';
