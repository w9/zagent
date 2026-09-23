DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='zagent_worker') THEN
        CREATE ROLE zagent_worker NOLOGIN;
    END IF;
END $$;

CREATE TABLE privacy.worker_pods (
    session_id uuid NOT NULL,
    job_id text NOT NULL,
    pod_uid uuid NOT NULL,
    attempt integer NOT NULL CHECK (attempt BETWEEN 1 AND 2),
    PRIMARY KEY (session_id, job_id, pod_uid),
    UNIQUE (session_id, job_id, attempt),
    FOREIGN KEY (session_id, job_id) REFERENCES jobs(session_id, id)
);
REVOKE ALL ON privacy.worker_pods FROM PUBLIC, zagent_runtime, zagent_worker;

CREATE FUNCTION public.register_worker_pod(execution text, pod uuid, token text)
RETURNS integer LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE
    session uuid := split_part(execution, ':', 1)::uuid;
    job text := split_part(execution, ':', 2);
    ordinal integer;
BEGIN
    PERFORM 1 FROM public.jobs WHERE session_id=session AND id=job FOR UPDATE;
    IF NOT EXISTS (
        SELECT 1 FROM privacy.job_inputs AS inputs JOIN public.jobs AS jobs
          ON jobs.session_id=inputs.session_id AND jobs.id=inputs.job_id
        WHERE inputs.session_id=session AND inputs.job_id=job
          AND inputs.snapshot->>'worker_token'=token AND length(token)>=32
          AND jobs.finished_at IS NULL
    ) THEN
        RAISE EXCEPTION 'Worker admission denied';
    END IF;
    SELECT attempt INTO ordinal FROM privacy.worker_pods
        WHERE session_id=session AND job_id=job AND pod_uid=pod;
    IF ordinal IS NULL THEN
        SELECT count(*)+1 INTO ordinal FROM privacy.worker_pods
            WHERE session_id=session AND job_id=job;
        INSERT INTO privacy.worker_pods VALUES (session,job,pod,ordinal);
    END IF;
    RETURN ordinal;
END $$;
REVOKE ALL ON FUNCTION public.register_worker_pod(text,uuid,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.register_worker_pod(text,uuid,text) TO zagent_worker;