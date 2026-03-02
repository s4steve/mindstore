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
