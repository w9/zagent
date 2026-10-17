-- Schema v3 publishes artifacts. Stored v1 and v2 events stay as written; Event translates
-- view_pushed and draft view_id to artifact_published and artifact_id on read.
ALTER TABLE events ALTER COLUMN schema_version SET DEFAULT 3;
ALTER TABLE events DROP CONSTRAINT events_schema_version_check;
ALTER TABLE events ADD CONSTRAINT events_schema_version_check CHECK (schema_version IN (1, 2, 3));
ALTER TABLE events DROP CONSTRAINT events_type_check;
ALTER TABLE events ADD CONSTRAINT events_type_check CHECK (
    type IN ('user_message', 'text_delta', 'message_done', 'message_dropped',
             'step_started', 'step_finished', 'tool_call', 'tool_result',
             'artifact_published', 'refused', 'draft_updated', 'privacy_alert', 'job_submitted',
             'session_updated')
    OR (schema_version IN (1, 2) AND type = 'view_pushed')
    OR (schema_version = 1 AND type IN ('run_started', 'run_finished', 'run_failed'))
    OR (schema_version IN (2, 3) AND type IN (
        'conversation_turn_started', 'conversation_turn_finished', 'conversation_turn_failed'
    ))
);

ALTER TABLE drafts RENAME COLUMN view_id TO artifact_id;
