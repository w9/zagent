CREATE TABLE job_queue (
    session_id uuid NOT NULL,
    job_id text NOT NULL,
    available_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    lease_owner uuid,
    lease_until timestamptz,
    revision bigint NOT NULL DEFAULT 0,
    completed_at timestamptz,
    PRIMARY KEY (session_id, job_id),
    FOREIGN KEY (session_id, job_id) REFERENCES jobs(session_id, id)
);
CREATE INDEX job_queue_available ON job_queue (available_at)
    WHERE completed_at IS NULL;
REVOKE ALL ON job_queue FROM zagent_runtime;