-- Migration to add thread_id column for Slack thread tracking
-- This migration adds thread_id to word_history table

ALTER TABLE word_history ADD COLUMN thread_id VARCHAR(255);

-- Create index on thread_id for efficient lookups
CREATE INDEX IF NOT EXISTS idx_word_history_thread_id ON word_history(thread_id);