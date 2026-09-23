ALTER TABLE sessions ADD COLUMN title text NOT NULL DEFAULT 'Session';
ALTER TABLE sessions ADD COLUMN title_source text NOT NULL DEFAULT 'fallback'
    CHECK (title_source IN ('fallback', 'automatic', 'manual'));
ALTER TABLE sessions ADD COLUMN title_attempted boolean NOT NULL DEFAULT false;
UPDATE sessions SET title = 'Session ' || left(replace(id::text, '-', ''), 8);