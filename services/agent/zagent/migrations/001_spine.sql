CREATE TABLE sessions (
    id uuid PRIMARY KEY,
    last_seq bigint NOT NULL DEFAULT 0 CHECK (last_seq >= 0),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

CREATE TABLE runs (
    id uuid PRIMARY KEY,
    session_id uuid NOT NULL REFERENCES sessions(id),
    status text NOT NULL CHECK (status IN ('running', 'finished', 'failed')),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    finished_at timestamptz,
    UNIQUE (id, session_id)
);

CREATE UNIQUE INDEX one_active_run_per_session ON runs (session_id) WHERE status = 'running';

CREATE TABLE events (
    session_id uuid NOT NULL REFERENCES sessions(id),
    seq bigint NOT NULL CHECK (seq > 0),
    run_id uuid NOT NULL,
    schema_version integer NOT NULL DEFAULT 1 CHECK (schema_version = 1),
    type text NOT NULL CHECK (type IN (
        'user_message', 'run_started', 'run_finished', 'run_failed',
        'text_delta', 'message_done', 'message_dropped', 'step_started',
        'step_finished', 'tool_call', 'tool_result', 'view_pushed', 'refused', 'draft_updated'
    )),
    payload jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (session_id, seq),
    FOREIGN KEY (run_id, session_id) REFERENCES runs(id, session_id)
);

CREATE FUNCTION reject_event_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'The event log is append-only';
END;
$$;

CREATE TRIGGER immutable_events BEFORE UPDATE OR DELETE ON events
    FOR EACH ROW EXECUTE FUNCTION reject_event_mutation();
