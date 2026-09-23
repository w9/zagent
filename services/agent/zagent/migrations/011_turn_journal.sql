CREATE TABLE turn_checkpoints (
    session_id uuid NOT NULL,
    conversation_turn_id uuid NOT NULL,
    step integer NOT NULL CHECK (step >= 0),
    response jsonb NOT NULL,
    PRIMARY KEY (conversation_turn_id, step),
    FOREIGN KEY (conversation_turn_id, session_id) REFERENCES conversation_turns(id, session_id)
);
GRANT SELECT, INSERT ON turn_checkpoints TO zagent_runtime;

CREATE TABLE tool_receipts (
    session_id uuid NOT NULL,
    conversation_turn_id uuid NOT NULL,
    operation_id text NOT NULL,
    arguments_hash text NOT NULL,
    result jsonb NOT NULL,
    PRIMARY KEY (conversation_turn_id, operation_id),
    FOREIGN KEY (conversation_turn_id, session_id) REFERENCES conversation_turns(id, session_id)
);
REVOKE ALL ON tool_receipts FROM zagent_runtime;