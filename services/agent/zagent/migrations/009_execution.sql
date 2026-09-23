ALTER TABLE jobs DROP CONSTRAINT jobs_status_check;
ALTER TABLE jobs ADD CONSTRAINT jobs_status_check
    CHECK (status IN ('pending', 'starting', 'running', 'retrying', 'completed', 'failed'));
ALTER TABLE jobs ADD COLUMN progress double precision NOT NULL DEFAULT 0
    CHECK (progress >= 0 AND progress <= 1);
ALTER TABLE jobs ADD COLUMN detail text NOT NULL DEFAULT 'Awaiting dispatch';
ALTER TABLE jobs ADD COLUMN attempt integer NOT NULL DEFAULT 1;
ALTER TABLE jobs ADD COLUMN version bigint NOT NULL DEFAULT 0;
ALTER TABLE jobs ADD COLUMN log_seq bigint NOT NULL DEFAULT 0;
ALTER TABLE jobs ADD COLUMN started_at timestamptz;
ALTER TABLE jobs ADD COLUMN finished_at timestamptz;

CREATE TABLE privacy.job_inputs (
    session_id uuid NOT NULL,
    job_id text NOT NULL,
    content_hash text NOT NULL,
    snapshot jsonb NOT NULL,
    PRIMARY KEY (session_id, job_id),
    FOREIGN KEY (session_id, job_id) REFERENCES jobs(session_id, id)
);
CREATE TABLE job_attempts (
    session_id uuid NOT NULL,
    job_id text NOT NULL,
    attempt integer NOT NULL,
    execution_name text NOT NULL UNIQUE,
    status text NOT NULL DEFAULT 'starting',
    started_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    finished_at timestamptz,
    exit_code integer,
    PRIMARY KEY (session_id, job_id, attempt),
    FOREIGN KEY (session_id, job_id) REFERENCES jobs(session_id, id)
);
CREATE TABLE job_logs (
    session_id uuid NOT NULL,
    job_id text NOT NULL,
    seq bigint NOT NULL,
    attempt integer NOT NULL,
    worker_sequence integer NOT NULL,
    record jsonb NOT NULL,
    PRIMARY KEY (session_id, job_id, seq),
    UNIQUE (session_id, job_id, attempt, worker_sequence),
    FOREIGN KEY (session_id, job_id, attempt) REFERENCES job_attempts(session_id, job_id, attempt)
);
REVOKE ALL ON job_attempts, job_logs, privacy.job_inputs FROM zagent_runtime;

ALTER TABLE specimens ADD COLUMN simulation text NOT NULL DEFAULT 'standard'
    CHECK (simulation IN ('standard', 'node_eviction', 'long_running', 'injected_log'));
ALTER TABLE query_handles ADD COLUMN selection_roles jsonb NOT NULL DEFAULT '{}';