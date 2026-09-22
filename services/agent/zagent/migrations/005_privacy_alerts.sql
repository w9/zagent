ALTER TABLE events DROP CONSTRAINT events_type_check;
ALTER TABLE events ADD CONSTRAINT events_type_check CHECK (
    type IN (
        'user_message', 'text_delta', 'message_done', 'message_dropped',
        'step_started', 'step_finished', 'tool_call', 'tool_result',
        'view_pushed', 'refused', 'draft_updated', 'privacy_alert'
    )
    OR (schema_version = 1 AND type IN ('run_started', 'run_finished', 'run_failed'))
    OR (schema_version = 2 AND type IN (
        'conversation_turn_started', 'conversation_turn_finished', 'conversation_turn_failed'
    ))
);