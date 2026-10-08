-- Archiving hides a session from the list; its events and audit records stay.
ALTER TABLE sessions ADD COLUMN archived_at timestamptz;
