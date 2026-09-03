from __future__ import annotations

from fastdps.database import Database


def test_migrations_are_numbered_complete_and_idempotent(tmp_path):
    db = Database(path=tmp_path / "new.sqlite")
    assert db.migrate() == ["0001_identity", "0002_procurement", "0003_chat_ocds", "0004_collaboration"]
    assert db.migrate() == []
    tables = {row["name"] for row in db.rows("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {
        "organisations", "roles", "role_permissions", "dynamic_purchasing_systems", "admission_applications",
        "competitions", "submissions", "evaluations", "awards", "contracts", "chat_pending_actions",
        "ocds_releases", "documents", "audit_events", "outbox_events",
    } <= tables


def test_postgres_adapter_is_declared_without_being_required_for_local_use(db):
    assert db.dialect == "sqlite"
    postgres = Database(url="postgresql://example.invalid/db", schema="fast_dps_test")
    assert postgres.dialect == "postgres"
    assert postgres.schema == "fast_dps_test"
