CREATE TABLE chat_sessions (
    id TEXT PRIMARY KEY,
    organisation_id TEXT NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title TEXT NOT NULL DEFAULT 'New conversation',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE chat_messages (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    event_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE TABLE chat_pending_actions (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
    organisation_id TEXT NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
    requested_by TEXT NOT NULL REFERENCES users(id),
    action_key TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    required_permission TEXT NOT NULL REFERENCES permissions(key),
    status TEXT NOT NULL DEFAULT 'pending',
    expires_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    executed_at TEXT
);

CREATE TABLE import_jobs (
    id TEXT PRIMARY KEY,
    organisation_id TEXT NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
    source TEXT NOT NULL,
    file_name TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    status TEXT NOT NULL,
    error TEXT NOT NULL DEFAULT '',
    imported_count INTEGER NOT NULL DEFAULT 0,
    created_by TEXT NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL,
    completed_at TEXT,
    UNIQUE(organisation_id, sha256)
);

CREATE TABLE ocds_releases (
    id TEXT PRIMARY KEY,
    organisation_id TEXT NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
    import_job_id TEXT REFERENCES import_jobs(id) ON DELETE SET NULL,
    ocid TEXT NOT NULL,
    release_id TEXT NOT NULL,
    release_date TEXT,
    tag_json TEXT NOT NULL DEFAULT '[]',
    source TEXT NOT NULL,
    checksum TEXT NOT NULL,
    release_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(organisation_id, ocid, release_id, checksum)
);

CREATE TABLE notice_index (
    id TEXT PRIMARY KEY,
    organisation_id TEXT NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
    release_id TEXT NOT NULL REFERENCES ocds_releases(id) ON DELETE CASCADE,
    ocid TEXT NOT NULL,
    stage TEXT NOT NULL,
    title TEXT NOT NULL,
    buyer_name TEXT NOT NULL DEFAULT '',
    cpv_codes TEXT NOT NULL DEFAULT '',
    value_amount TEXT,
    currency TEXT,
    deadline TEXT,
    status TEXT NOT NULL DEFAULT '',
    UNIQUE(organisation_id, release_id)
);

CREATE INDEX idx_chat_sessions_user ON chat_sessions(organisation_id, user_id, updated_at DESC);
CREATE INDEX idx_pending_actions_status ON chat_pending_actions(organisation_id, status, expires_at);
CREATE INDEX idx_ocds_ocid ON ocds_releases(organisation_id, ocid);
CREATE INDEX idx_notice_search ON notice_index(organisation_id, stage, status);
