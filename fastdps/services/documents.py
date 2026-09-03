"""Versioned local document storage with content hashes and tenant checks."""
from __future__ import annotations

import hashlib
from pathlib import Path

from fastdps.config import settings
from fastdps.database import Database, get_database
from fastdps.security import Actor
from fastdps.services.common import audit, now, uid


class DocumentService:
    def __init__(self, db: Database | None = None, storage_root: Path | None = None):
        self.db = db or get_database()
        self.storage_root = storage_root or settings.data_dir / "documents"

    def add(self, actor: Actor, entity_type: str, entity_id: str, title: str,
            file_name: str, content: bytes, mime_type: str = "application/octet-stream") -> dict:
        actor.require("documents.manage")
        if not content:
            raise ValueError("Document is empty")
        document_id, version_id, timestamp = uid(), uid(), now()
        digest = hashlib.sha256(content).hexdigest()
        safe_name = Path(file_name).name or "document.bin"
        relative = Path(actor.organisation_id) / document_id / f"1-{safe_name}"
        target = self.storage_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        try:
            with self.db.transaction() as tx:
                tx.execute(
                    "INSERT INTO documents(id,organisation_id,entity_type,entity_id,title,document_type,current_version,created_by,created_at,updated_at) "
                    "VALUES (?,?,?,?,?,'other',1,?,?,?)",
                    (document_id, actor.organisation_id, entity_type, entity_id, title.strip() or safe_name,
                     actor.user_id, timestamp, timestamp),
                )
                tx.execute(
                    "INSERT INTO document_versions(id,document_id,version,file_name,storage_path,mime_type,size_bytes,sha256,created_by,created_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (version_id, document_id, 1, safe_name, str(relative), mime_type, len(content), digest, actor.user_id, timestamp),
                )
                audit(tx, actor.organisation_id, actor.user_id, "document.created", "document", document_id, {"sha256": digest})
        except Exception:
            target.unlink(missing_ok=True)
            raise
        return self.get(actor, document_id)

    def add_version(self, actor: Actor, document_id: str, file_name: str, content: bytes,
                    mime_type: str = "application/octet-stream") -> dict:
        actor.require("documents.manage")
        document = self.get(actor, document_id)
        version = int(document["current_version"]) + 1
        digest, timestamp = hashlib.sha256(content).hexdigest(), now()
        safe_name = Path(file_name).name or "document.bin"
        relative = Path(actor.organisation_id) / document_id / f"{version}-{safe_name}"
        target = self.storage_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        try:
            with self.db.transaction() as tx:
                tx.execute(
                    "INSERT INTO document_versions(id,document_id,version,file_name,storage_path,mime_type,size_bytes,sha256,created_by,created_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (uid(), document_id, version, safe_name, str(relative), mime_type, len(content), digest, actor.user_id, timestamp),
                )
                tx.execute("UPDATE documents SET current_version=?,updated_at=? WHERE id=? AND organisation_id=?",
                           (version, timestamp, document_id, actor.organisation_id))
                audit(tx, actor.organisation_id, actor.user_id, "document.version_added", "document", document_id, {"version": version})
        except Exception:
            target.unlink(missing_ok=True)
            raise
        return self.get(actor, document_id)

    def get(self, actor: Actor, document_id: str) -> dict:
        actor.require("dps.view")
        document = self.db.one("SELECT * FROM documents WHERE id=? AND organisation_id=?", (document_id, actor.organisation_id))
        if not document:
            raise LookupError("Document not found")
        document["versions"] = self.db.rows("SELECT * FROM document_versions WHERE document_id=? ORDER BY version DESC", (document_id,))
        return document

    def list(self, actor: Actor, entity_type: str | None = None, entity_id: str | None = None) -> list[dict]:
        actor.require("dps.view")
        query, params = "SELECT * FROM documents WHERE organisation_id=?", [actor.organisation_id]
        if entity_type:
            query += " AND entity_type=?"
            params.append(entity_type)
        if entity_id:
            query += " AND entity_id=?"
            params.append(entity_id)
        return self.db.rows(query + " ORDER BY updated_at DESC", params)

    def version_path(self, actor: Actor, version_id: str) -> tuple[Path, dict]:
        actor.require("dps.view")
        version = self.db.one(
            "SELECT v.* FROM document_versions v JOIN documents d ON d.id=v.document_id "
            "WHERE v.id=? AND d.organisation_id=?", (version_id, actor.organisation_id),
        )
        if not version:
            raise LookupError("Document version not found")
        path = (self.storage_root / version["storage_path"]).resolve()
        if self.storage_root.resolve() not in path.parents:
            raise PermissionError("Invalid document path")
        return path, version
