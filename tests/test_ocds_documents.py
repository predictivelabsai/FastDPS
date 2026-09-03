from __future__ import annotations

import hashlib
import json

from fastdps.services.documents import DocumentService
from fastdps.services.ocds import OcdsService
from fastdps.services.procurement import ProcurementService


def test_ocds_export_import_and_file_idempotency(db, owner):
    procurement = ProcurementService(db)
    dps = procurement.create_dps(owner, "Cloud services", estimated_value="100000")
    procurement.add_category(owner, dps["id"], "72000000", "IT services")
    release = OcdsService(db).export_dps(owner, dps["id"])
    assert release["tender"]["procurementMethodDetails"] == "Dynamic purchasing system"
    content = json.dumps({"releases": [release]}).encode()
    first = OcdsService(db).import_json(owner, content, "package.json")
    second = OcdsService(db).import_json(owner, content, "package.json")
    assert first["id"] == second["id"]
    assert db.scalar("SELECT COUNT(*) FROM ocds_releases") == 1
    assert OcdsService(db).notices(owner)[0]["title"] == "Cloud services"


def test_versioned_documents_are_hashed_and_scoped(db, owner, tmp_path):
    service = DocumentService(db, tmp_path / "documents")
    document = service.add(owner, "dps", "record-1", "Specification", "spec.txt", b"version one", "text/plain")
    assert document["versions"][0]["sha256"] == hashlib.sha256(b"version one").hexdigest()
    document = service.add_version(owner, document["id"], "spec.txt", b"version two", "text/plain")
    assert document["current_version"] == 2
    assert [row["version"] for row in document["versions"]] == [2, 1]
    path, version = service.version_path(owner, document["versions"][0]["id"])
    assert path.read_bytes() == b"version two"
    assert version["file_name"] == "spec.txt"
