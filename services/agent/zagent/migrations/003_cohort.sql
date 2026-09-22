CREATE TABLE clinical_sites (
    id text PRIMARY KEY,
    name text NOT NULL,
    region text NOT NULL,
    mrn_format text NOT NULL
);

INSERT INTO clinical_sites VALUES
    ('northgate', 'Northgate Genomics Centre', 'North', 'NGC-0000000'),
    ('lakeside', 'Lakeside Helix Hospital', 'East', 'LHX/00/00000'),
    ('sequoia', 'Sequoia Research Hospital', 'West', 'SQ-AA-0000'),
    ('cedar', 'Cedar Vale Medical Centre', 'South', 'CV00000000'),
    ('harbor', 'Harbor Light Hospital', 'East', '000-00-0000');

ALTER TABLE sessions ADD COLUMN site_id text NOT NULL DEFAULT 'northgate'
    REFERENCES clinical_sites(id);

CREATE TABLE patients (
    id text NOT NULL,
    site_id text NOT NULL REFERENCES clinical_sites(id),
    mrn text NOT NULL,
    birth_year integer NOT NULL,
    PRIMARY KEY (id, site_id),
    UNIQUE (site_id, mrn)
);

CREATE TABLE specimens (
    id text NOT NULL,
    site_id text NOT NULL REFERENCES clinical_sites(id),
    patient_id text NOT NULL,
    kind text NOT NULL CHECK (kind IN ('tumor', 'normal', 'RNA')),
    assayed_kind text NOT NULL CHECK (assayed_kind IN ('tumor', 'normal', 'RNA')),
    purity double precision CHECK (purity BETWEEN 0 AND 1),
    collected_at timestamptz NOT NULL,
    received_at timestamptz NOT NULL,
    PRIMARY KEY (id, site_id),
    FOREIGN KEY (patient_id, site_id) REFERENCES patients(id, site_id)
);

CREATE INDEX specimens_received ON specimens (site_id, received_at);

CREATE TABLE libraries (
    id text NOT NULL,
    site_id text NOT NULL REFERENCES clinical_sites(id),
    specimen_id text NOT NULL,
    prep text NOT NULL,
    coverage double precision NOT NULL CHECK (coverage >= 0),
    qc_status text NOT NULL CHECK (qc_status IN ('passed', 'review', 'failed')),
    PRIMARY KEY (id, site_id),
    FOREIGN KEY (specimen_id, site_id) REFERENCES specimens(id, site_id)
);

CREATE TABLE query_handles (
    session_id uuid NOT NULL REFERENCES sessions(id),
    handle text NOT NULL,
    site_id text NOT NULL REFERENCES clinical_sites(id),
    entity text NOT NULL CHECK (entity IN ('patients', 'specimens', 'libraries')),
    columns jsonb NOT NULL,
    rows jsonb NOT NULL,
    row_ids text[] NOT NULL,
    row_count integer NOT NULL CHECK (row_count >= 0),
    expires_at timestamptz NOT NULL,
    PRIMARY KEY (session_id, handle)
);

CREATE TABLE tool_audit (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    session_id uuid NOT NULL REFERENCES sessions(id),
    conversation_turn_id uuid NOT NULL REFERENCES conversation_turns(id),
    tool text NOT NULL,
    arguments jsonb NOT NULL,
    result jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

DO $$
DECLARE
    site text;
    site_role text;
    relation text;
BEGIN
    FOREACH site IN ARRAY ARRAY['northgate', 'lakeside', 'sequoia', 'cedar', 'harbor'] LOOP
        site_role := 'zagent_site_' || site;
        IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = site_role) THEN
            EXECUTE format('CREATE ROLE %I NOLOGIN NOSUPERUSER NOBYPASSRLS', site_role);
        END IF;
        EXECUTE format('GRANT %I TO %I', site_role, current_user);
        EXECUTE format('GRANT USAGE ON SCHEMA public TO %I', site_role);
        EXECUTE format('GRANT SELECT ON patients, specimens, libraries, query_handles TO %I',
                       site_role);
    END LOOP;
    FOREACH relation IN ARRAY ARRAY['patients', 'specimens', 'libraries', 'query_handles'] LOOP
        EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', relation);
        EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', relation);
        EXECUTE format(
            'CREATE POLICY site_isolation ON %I USING '
            || '(site_id = replace(current_user, ''zagent_site_'', ''''))', relation
        );
        EXECUTE format('CREATE POLICY fixture_owner ON %I TO %I USING (true) WITH CHECK (true)',
                       relation, current_user);
    END LOOP;
END;
$$;