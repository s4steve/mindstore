CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE IF NOT EXISTS thoughts (
    id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    content      TEXT NOT NULL,
    embedding    vector(384),
    source       TEXT NOT NULL DEFAULT 'api',
    content_type TEXT NOT NULL DEFAULT 'thought',
    title        TEXT,
    tags         TEXT[] DEFAULT '{}',
    metadata     JSONB DEFAULT '{}',
    chunk_index  INTEGER DEFAULT 0,
    parent_id    UUID REFERENCES thoughts(id) ON DELETE CASCADE,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS thoughts_embedding_idx
    ON thoughts USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

CREATE INDEX IF NOT EXISTS thoughts_tags_idx ON thoughts USING gin(tags);
CREATE INDEX IF NOT EXISTS thoughts_content_type_idx ON thoughts(content_type);
CREATE INDEX IF NOT EXISTS thoughts_created_at_idx ON thoughts(created_at DESC);
CREATE INDEX IF NOT EXISTS thoughts_parent_id_idx ON thoughts(parent_id);

CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN NEW.updated_at = NOW(); RETURN NEW; END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER thoughts_updated_at
    BEFORE UPDATE ON thoughts
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ── Tasks ────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS tasks (
    id             UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    title          TEXT NOT NULL,
    notes          TEXT,
    status         TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'done', 'cancelled')),
    priority       TEXT NOT NULL DEFAULT 'medium' CHECK (priority IN ('high', 'medium', 'low')),
    due_date       DATE,
    recurrence_days INTEGER,
    category       TEXT NOT NULL DEFAULT 'general' CHECK (category IN ('general', 'work', 'personal', 'health', 'finance', 'home')),
    tags           TEXT[] DEFAULT '{}',
    embedding      vector(384),
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS tasks_tags_idx ON tasks USING gin(tags);
CREATE INDEX IF NOT EXISTS tasks_due_date_idx ON tasks(due_date);
CREATE INDEX IF NOT EXISTS tasks_status_idx ON tasks(status);
CREATE INDEX IF NOT EXISTS tasks_embedding_idx
    ON tasks USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

DO $$ BEGIN
    CREATE TRIGGER tasks_updated_at
        BEFORE UPDATE ON tasks
        FOR EACH ROW EXECUTE FUNCTION update_updated_at();
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- ── Contacts ─────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS contacts (
    id               UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name             TEXT NOT NULL,
    email            TEXT,
    phone            TEXT,
    company          TEXT,
    last_contact_at  TIMESTAMPTZ,
    notes            TEXT,
    tags             TEXT[] DEFAULT '{}',
    embedding        vector(384),
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS contacts_tags_idx ON contacts USING gin(tags);
CREATE INDEX IF NOT EXISTS contacts_last_contact_idx ON contacts(last_contact_at);
CREATE INDEX IF NOT EXISTS contacts_embedding_idx
    ON contacts USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

DO $$ BEGIN
    CREATE TRIGGER contacts_updated_at
        BEFORE UPDATE ON contacts
        FOR EACH ROW EXECUTE FUNCTION update_updated_at();
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- ── Home items ───────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS home_items (
    id             UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name           TEXT NOT NULL,
    notes          TEXT,
    last_done_at   TIMESTAMPTZ,
    next_due_at    TIMESTAMPTZ,
    interval_days  INTEGER,
    tags           TEXT[] DEFAULT '{}',
    embedding      vector(384),
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS home_items_tags_idx ON home_items USING gin(tags);
CREATE INDEX IF NOT EXISTS home_items_next_due_idx ON home_items(next_due_at);
CREATE INDEX IF NOT EXISTS home_items_embedding_idx
    ON home_items USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

DO $$ BEGIN
    CREATE TRIGGER home_items_updated_at
        BEFORE UPDATE ON home_items
        FOR EACH ROW EXECUTE FUNCTION update_updated_at();
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
