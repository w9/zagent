CREATE TABLE job_handles (
    session_id uuid NOT NULL REFERENCES sessions(id),
    handle text NOT NULL,
    job_id text,
    state_filter text NOT NULL DEFAULT 'all',
    created_since timestamptz,
    expires_at timestamptz NOT NULL,
    PRIMARY KEY (session_id, handle),
    FOREIGN KEY (session_id, job_id) REFERENCES jobs(session_id, id)
);
REVOKE ALL ON job_handles FROM zagent_runtime;