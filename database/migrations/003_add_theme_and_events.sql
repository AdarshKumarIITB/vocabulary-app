-- Migration to add theme support and event processing tables

-- Create table for tracking processed events (deduplication)
CREATE TABLE IF NOT EXISTS processed_events (
    id SERIAL PRIMARY KEY,
    event_key VARCHAR(255) UNIQUE NOT NULL,
    processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    event_type VARCHAR(50)
);

-- Create indexes for efficient queries
CREATE INDEX IF NOT EXISTS idx_processed_events_key ON processed_events(event_key);
CREATE INDEX IF NOT EXISTS idx_processed_events_time ON processed_events(processed_at);

-- Create table for user themes
CREATE TABLE IF NOT EXISTS user_themes (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(100) UNIQUE NOT NULL,
    theme VARCHAR(100),
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create index for user lookup
CREATE INDEX IF NOT EXISTS idx_user_themes_user ON user_themes(user_id);

-- Create table for system settings (like theme thread ID)
CREATE TABLE IF NOT EXISTS system_settings (
    key VARCHAR(100) PRIMARY KEY,
    value TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Insert default settings
INSERT INTO system_settings (key, value) 
VALUES ('theme_thread_id', NULL)
ON CONFLICT (key) DO NOTHING;