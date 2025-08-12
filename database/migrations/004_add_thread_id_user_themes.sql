-- Add thread_id to user_themes (SQLite-safe)

ALTER TABLE user_themes
    ADD COLUMN thread_id VARCHAR(100);      -- NULL-able is required for SQLite

-- Optional: speed up look-ups by thread_id
CREATE INDEX IF NOT EXISTS idx_user_themes_thread
    ON user_themes(thread_id);
