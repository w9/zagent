CREATE SCHEMA privacy;
REVOKE ALL ON SCHEMA privacy FROM PUBLIC;

ALTER TABLE patients ADD COLUMN display_name text NOT NULL DEFAULT '';

CREATE TABLE privacy.tokens (
    session_id uuid NOT NULL REFERENCES sessions(id),
    token text NOT NULL,
    kind text NOT NULL CHECK (kind IN ('PT', 'SP', 'LB', 'LIT')),
    value text NOT NULL,
    normalized_value text NOT NULL,
    PRIMARY KEY (session_id, token),
    UNIQUE (session_id, kind, normalized_value)
);

CREATE TABLE privacy.execution_audit (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    session_id uuid NOT NULL REFERENCES sessions(id),
    conversation_turn_id uuid NOT NULL REFERENCES conversation_turns(id),
    tool text NOT NULL,
    arguments jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

CREATE TABLE privacy.legacy_events (LIKE events INCLUDING DEFAULTS);
CREATE TABLE privacy.settings (name text PRIMARY KEY, value text NOT NULL);

DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'zagent_runtime') THEN
        CREATE ROLE zagent_runtime LOGIN PASSWORD 'zagent_runtime' NOSUPERUSER NOBYPASSRLS;
    END IF;
END;
$$;

GRANT USAGE ON SCHEMA public TO zagent_runtime;
GRANT SELECT, INSERT, UPDATE ON sessions, conversation_turns TO zagent_runtime;
GRANT SELECT, INSERT ON events TO zagent_runtime;
GRANT INSERT ON tool_audit TO zagent_runtime;
GRANT USAGE ON SEQUENCE tool_audit_id_seq TO zagent_runtime;
REVOKE ALL ON patients, specimens, libraries, query_handles FROM zagent_runtime;
REVOKE ALL ON SCHEMA privacy FROM zagent_runtime;