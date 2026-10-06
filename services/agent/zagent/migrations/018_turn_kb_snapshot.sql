-- The knowledge snapshot a turn first read; later and resumed steps of that turn read the same one.
ALTER TABLE conversation_turns ADD COLUMN kb_snapshot text CHECK (kb_snapshot ~ '^[a-f0-9]{64}$');
