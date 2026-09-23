CREATE TABLE drafts (
    session_id uuid NOT NULL REFERENCES sessions(id),
    id text NOT NULL,
    conversation_turn_id uuid NOT NULL,
    view_id text NOT NULL,
    version integer NOT NULL CHECK (version > 0),
    content_hash text NOT NULL,
    content jsonb NOT NULL,
    validation jsonb NOT NULL,
    status text NOT NULL CHECK (status IN ('editing', 'submitted')),
    PRIMARY KEY (session_id, id),
    FOREIGN KEY (conversation_turn_id, session_id) REFERENCES conversation_turns(id, session_id)
);

CREATE TABLE draft_revisions (
    session_id uuid NOT NULL,
    draft_id text NOT NULL,
    version integer NOT NULL,
    content_hash text NOT NULL,
    content jsonb NOT NULL,
    PRIMARY KEY (session_id, draft_id, version),
    FOREIGN KEY (session_id, draft_id) REFERENCES drafts(session_id, id)
);

CREATE TABLE jobs (
    session_id uuid NOT NULL,
    id text NOT NULL,
    draft_id text NOT NULL,
    confirmed_version integer NOT NULL,
    confirmation_hash text NOT NULL,
    content_hash text NOT NULL CHECK (content_hash = confirmation_hash),
    content jsonb NOT NULL,
    status text NOT NULL DEFAULT 'pending' CHECK (status = 'pending'),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (session_id, id),
    UNIQUE (session_id, draft_id),
    FOREIGN KEY (session_id, draft_id, confirmed_version)
        REFERENCES draft_revisions(session_id, draft_id, version)
);
REVOKE ALL ON drafts, draft_revisions, jobs FROM zagent_runtime;

ALTER TABLE events DROP CONSTRAINT events_type_check;
ALTER TABLE events ADD CONSTRAINT events_type_check CHECK (
    type IN ('user_message', 'text_delta', 'message_done', 'message_dropped',
             'step_started', 'step_finished', 'tool_call', 'tool_result',
             'view_pushed', 'refused', 'draft_updated', 'privacy_alert', 'job_submitted', 'session_updated')
    OR (schema_version = 1 AND type IN ('run_started', 'run_finished', 'run_failed'))
    OR (schema_version = 2 AND type IN (
        'conversation_turn_started', 'conversation_turn_finished', 'conversation_turn_failed'
    ))
);