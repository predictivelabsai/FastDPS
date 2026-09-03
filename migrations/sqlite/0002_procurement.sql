CREATE TABLE dynamic_purchasing_systems (
    id TEXT PRIMARY KEY,
    organisation_id TEXT NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
    reference TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'draft',
    jurisdiction_profile TEXT NOT NULL DEFAULT 'neutral',
    currency TEXT NOT NULL DEFAULT 'EUR',
    estimated_value TEXT,
    opens_at TEXT,
    closes_at TEXT,
    created_by TEXT NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(organisation_id, reference)
);

CREATE TABLE dps_categories (
    id TEXT PRIMARY KEY,
    dps_id TEXT NOT NULL REFERENCES dynamic_purchasing_systems(id) ON DELETE CASCADE,
    code TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    UNIQUE(dps_id, code)
);

CREATE TABLE qualification_criteria (
    id TEXT PRIMARY KEY,
    dps_id TEXT NOT NULL REFERENCES dynamic_purchasing_systems(id) ON DELETE CASCADE,
    category_id TEXT REFERENCES dps_categories(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    required INTEGER NOT NULL DEFAULT 1,
    sort_order INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE workflow_definitions (
    id TEXT PRIMARY KEY,
    organisation_id TEXT NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    is_default INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE workflow_steps (
    id TEXT PRIMARY KEY,
    workflow_id TEXT NOT NULL REFERENCES workflow_definitions(id) ON DELETE CASCADE,
    step_key TEXT NOT NULL,
    name TEXT NOT NULL,
    required_permission TEXT REFERENCES permissions(key),
    sort_order INTEGER NOT NULL,
    UNIQUE(workflow_id, step_key)
);

CREATE TABLE workflow_transitions (
    id TEXT PRIMARY KEY,
    workflow_id TEXT NOT NULL REFERENCES workflow_definitions(id) ON DELETE CASCADE,
    from_step TEXT NOT NULL,
    to_step TEXT NOT NULL,
    action_name TEXT NOT NULL,
    required_permission TEXT REFERENCES permissions(key)
);

CREATE TABLE supplier_organisations (
    id TEXT PRIMARY KEY,
    owner_user_id TEXT NOT NULL REFERENCES users(id),
    name TEXT NOT NULL,
    registration_number TEXT,
    website TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE admission_applications (
    id TEXT PRIMARY KEY,
    dps_id TEXT NOT NULL REFERENCES dynamic_purchasing_systems(id) ON DELETE CASCADE,
    supplier_id TEXT NOT NULL REFERENCES supplier_organisations(id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'draft',
    answers_json TEXT NOT NULL DEFAULT '{}',
    submitted_at TEXT,
    reviewed_by TEXT REFERENCES users(id),
    reviewed_at TEXT,
    decision_reason TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(dps_id, supplier_id)
);

CREATE TABLE competitions (
    id TEXT PRIMARY KEY,
    dps_id TEXT NOT NULL REFERENCES dynamic_purchasing_systems(id) ON DELETE CASCADE,
    organisation_id TEXT NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
    reference TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'draft',
    deadline TEXT,
    created_by TEXT NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(organisation_id, reference)
);

CREATE TABLE competition_invitations (
    competition_id TEXT NOT NULL REFERENCES competitions(id) ON DELETE CASCADE,
    supplier_id TEXT NOT NULL REFERENCES supplier_organisations(id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'invited',
    invited_at TEXT NOT NULL,
    PRIMARY KEY(competition_id, supplier_id)
);

CREATE TABLE submissions (
    id TEXT PRIMARY KEY,
    competition_id TEXT NOT NULL REFERENCES competitions(id) ON DELETE CASCADE,
    supplier_id TEXT NOT NULL REFERENCES supplier_organisations(id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'draft',
    value_amount TEXT,
    currency TEXT NOT NULL DEFAULT 'EUR',
    response_json TEXT NOT NULL DEFAULT '{}',
    submitted_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(competition_id, supplier_id)
);

CREATE TABLE evaluation_criteria (
    id TEXT PRIMARY KEY,
    competition_id TEXT NOT NULL REFERENCES competitions(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    weight TEXT NOT NULL,
    max_score TEXT NOT NULL DEFAULT '10',
    sort_order INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE evaluations (
    id TEXT PRIMARY KEY,
    submission_id TEXT NOT NULL REFERENCES submissions(id) ON DELETE CASCADE,
    criterion_id TEXT NOT NULL REFERENCES evaluation_criteria(id) ON DELETE CASCADE,
    evaluator_user_id TEXT NOT NULL REFERENCES users(id),
    score TEXT NOT NULL,
    comment TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(submission_id, criterion_id, evaluator_user_id)
);

CREATE TABLE conflicts (
    id TEXT PRIMARY KEY,
    competition_id TEXT NOT NULL REFERENCES competitions(id) ON DELETE CASCADE,
    user_id TEXT NOT NULL REFERENCES users(id),
    declaration TEXT NOT NULL,
    has_conflict INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    UNIQUE(competition_id, user_id)
);

CREATE TABLE awards (
    id TEXT PRIMARY KEY,
    competition_id TEXT NOT NULL UNIQUE REFERENCES competitions(id) ON DELETE CASCADE,
    submission_id TEXT NOT NULL REFERENCES submissions(id),
    status TEXT NOT NULL DEFAULT 'draft',
    rationale TEXT NOT NULL DEFAULT '',
    approved_by TEXT REFERENCES users(id),
    approved_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE contracts (
    id TEXT PRIMARY KEY,
    award_id TEXT NOT NULL REFERENCES awards(id),
    reference TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft',
    value_amount TEXT,
    currency TEXT NOT NULL DEFAULT 'EUR',
    starts_at TEXT,
    ends_at TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE documents (
    id TEXT PRIMARY KEY,
    organisation_id TEXT NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    title TEXT NOT NULL,
    document_type TEXT NOT NULL DEFAULT 'other',
    current_version INTEGER NOT NULL DEFAULT 1,
    created_by TEXT NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE document_versions (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    version INTEGER NOT NULL,
    file_name TEXT NOT NULL,
    storage_path TEXT NOT NULL,
    mime_type TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    sha256 TEXT NOT NULL,
    created_by TEXT NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL,
    UNIQUE(document_id, version)
);

CREATE INDEX idx_dps_org_status ON dynamic_purchasing_systems(organisation_id, status);
CREATE INDEX idx_applications_dps_status ON admission_applications(dps_id, status);
CREATE INDEX idx_competitions_org_status ON competitions(organisation_id, status);
CREATE INDEX idx_submissions_competition ON submissions(competition_id, status);
