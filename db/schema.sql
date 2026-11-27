-- Graduation check-in & stage management: authoritative schema (idempotent).
-- PostgreSQL is the single source of truth for business state.

CREATE TABLE IF NOT EXISTS users (
    id            SERIAL PRIMARY KEY,
    username      VARCHAR(64)  NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    display_name  VARCHAR(128) NOT NULL,
    role          VARCHAR(16)  NOT NULL CHECK (role IN ('admin', 'staff')),
    is_active     BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS participants (
    id               BIGSERIAL PRIMARY KEY,
    participant_code VARCHAR(32)  NOT NULL UNIQUE,
    name             VARCHAR(128) NOT NULL,
    email            VARCHAR(255) NOT NULL,
    qr_token         VARCHAR(64)  NOT NULL UNIQUE,
    status           VARCHAR(16)  NOT NULL DEFAULT 'registered'
                     CHECK (status IN ('registered', 'checked_in', 'queued', 'on_stage', 'completed')),
    checked_in_at    TIMESTAMPTZ,
    checked_in_by    INTEGER REFERENCES users(id),
    queued_at        TIMESTAMPTZ,
    queued_by        INTEGER REFERENCES users(id),
    called_at        TIMESTAMPTZ,
    called_by        INTEGER REFERENCES users(id),
    completed_at     TIMESTAMPTZ,
    completed_by     INTEGER REFERENCES users(id),
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- status <-> audit timestamp consistency (state machine invariants)
    CONSTRAINT ck_checked_in_ts CHECK (status = 'registered' OR checked_in_at IS NOT NULL),
    CONSTRAINT ck_queued_ts     CHECK (status NOT IN ('queued', 'on_stage', 'completed') OR queued_at IS NOT NULL),
    CONSTRAINT ck_called_ts     CHECK (status NOT IN ('on_stage', 'completed') OR called_at IS NOT NULL),
    CONSTRAINT ck_completed_ts  CHECK (status <> 'completed' OR completed_at IS NOT NULL)
);

-- Case-insensitive unique email
CREATE UNIQUE INDEX IF NOT EXISTS uq_participants_email_lower ON participants (lower(email));
-- At most ONE participant on stage at any time, enforced by the database
CREATE UNIQUE INDEX IF NOT EXISTS uq_one_on_stage ON participants ((true)) WHERE status = 'on_stage';
-- Queue ordering (FIFO by queued_at, id as tie-breaker)
CREATE INDEX IF NOT EXISTS ix_participants_queue ON participants (queued_at, id) WHERE status = 'queued';
CREATE INDEX IF NOT EXISTS ix_participants_status ON participants (status);
CREATE INDEX IF NOT EXISTS ix_participants_name_lower ON participants (lower(name));

CREATE TABLE IF NOT EXISTS audit_logs (
    id             BIGSERIAL PRIMARY KEY,
    participant_id BIGINT REFERENCES participants(id) ON DELETE SET NULL,
    action         VARCHAR(32) NOT NULL
                   CHECK (action IN ('create', 'update', 'check_in', 'enqueue', 'call', 'complete', 'regenerate_qr')),
    operator_id    INTEGER REFERENCES users(id),
    details        JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_audit_logs_participant ON audit_logs (participant_id, created_at);
