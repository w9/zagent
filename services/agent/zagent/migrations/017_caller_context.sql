ALTER TABLE sessions ADD COLUMN persona text NOT NULL DEFAULT 'analyst'
    CHECK (persona IN ('lab-technologist', 'analyst', 'qa-officer', 'lab-director'));
-- A signed, short-lived context from the BFF; resumed turns reuse it and fail closed once expired.
ALTER TABLE conversation_turns ADD COLUMN caller_context text;
