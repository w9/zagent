ALTER TABLE runs RENAME TO conversation_turns;
ALTER TABLE conversation_turns RENAME CONSTRAINT runs_pkey TO conversation_turns_pkey;
ALTER TABLE conversation_turns RENAME CONSTRAINT runs_session_id_fkey TO conversation_turns_session_id_fkey;
ALTER TABLE conversation_turns RENAME CONSTRAINT runs_status_check TO conversation_turns_status_check;
ALTER TABLE conversation_turns RENAME CONSTRAINT runs_id_session_id_key TO conversation_turns_id_session_id_key;
ALTER INDEX one_active_run_per_session RENAME TO one_active_conversation_turn_per_session;

ALTER TABLE events RENAME COLUMN run_id TO conversation_turn_id;
ALTER TABLE events RENAME CONSTRAINT events_run_id_session_id_fkey TO events_conversation_turn_id_session_id_fkey;
ALTER TABLE events ALTER COLUMN schema_version SET DEFAULT 2;
ALTER TABLE events DROP CONSTRAINT events_schema_version_check;
ALTER TABLE events ADD CONSTRAINT events_schema_version_check CHECK (schema_version IN (1, 2));
ALTER TABLE events DROP CONSTRAINT events_type_check;
ALTER TABLE events ADD CONSTRAINT events_type_check CHECK (
    type IN (
        'user_message', 'text_delta', 'message_done', 'message_dropped',
        'step_started', 'step_finished', 'tool_call', 'tool_result',
        'view_pushed', 'refused', 'draft_updated'
    )
    OR (schema_version = 1 AND type IN ('run_started', 'run_finished', 'run_failed'))
    OR (schema_version = 2 AND type IN (
        'conversation_turn_started', 'conversation_turn_finished', 'conversation_turn_failed'
    ))
);