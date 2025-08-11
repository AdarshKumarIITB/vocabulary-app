-- Initial schema for WordHistory table
-- This migration creates the word_history table for v1

CREATE TABLE IF NOT EXISTS word_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    word VARCHAR(255) UNIQUE NOT NULL,
    known_flag BOOLEAN,
    thread_id VARCHAR(255),
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create index on timestamp for efficient ordering
CREATE INDEX IF NOT EXISTS idx_word_history_timestamp ON word_history(timestamp DESC);

-- Create index on known_flag for efficient filtering
CREATE INDEX IF NOT EXISTS idx_word_history_known_flag ON word_history(known_flag);

-- Create index on thread_id for efficient lookups
CREATE INDEX IF NOT EXISTS idx_word_history_thread_id ON word_history(thread_id);