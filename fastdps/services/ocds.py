"""OCDS JSON import/export and optional TED/Doffin eForms conversion adapter."""
from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path
from typing import Any

from fastdps.config import settings
from fastdps.database import Database, get_database
from fastdps.security import Actor
from fastdps.services.common import audit, json_dump, now, uid


class OcdsService:
    def __init__(self, db: Database | None = None):
        self.db = db or get_database()

    def _release_list(self, document: dict[str, Any]) -> list[dict[str, Any]]:
        if isinstance(document.get("releases"), list):
            return document["releases"]
        if document.get("ocid"):
            return [document]
        raise ValueError("Expected an OCDS release or release package")

    def import_json(self, actor: Actor, content: bytes, file_name: str = "release.json", source: str = "upload") -> dict:
        actor.require("ocds.import")
        digest = hashlib.sha256(content).hexdigest()
        existing = self.db.one("SELECT * FROM import_jobs WHERE organisation_id=? AND sha256=?", (actor.organisation_id, digest))
        if existing:
            return existing
        job_id, timestamp = uid(), now()
        with self.db.transaction() as tx:
            tx.execute(
                "INSERT INTO import_jobs(id,organisation_id,source,file_name,sha256,status,created_by,created_at) "
                "VALUES (?,?,?,?,?,'processing',?,?)",
                (job_id, actor.organisation_id, source, Path(file_name).name, digest, actor.user_id, timestamp),
            )
        try:
            document = json.loads(content.decode("utf-8"))
            releases = self._release_list(document)
            imported = 0
            with self.db.transaction() as tx:
                for release in releases:
                    if self._store_release(tx, actor, job_id, release, source):
                        imported += 1
                tx.execute("UPDATE import_jobs SET status='completed',imported_count=?,completed_at=? WHERE id=?",
                           (imported, now(), job_id))
                audit(tx, actor.organisation_id, actor.user_id, "ocds.imported", "import_job", job_id, {"count": imported})
        except Exception as exc:
            with self.db.transaction() as tx:
                tx.execute("UPDATE import_jobs SET status='failed',error=?,completed_at=? WHERE id=?", (str(exc)[:1000], now(), job_id))
            raise
        return self.db.one("SELECT * FROM import_jobs WHERE id=?", (job_id,))

    def _store_release(self, tx, actor: Actor, job_id: str, release: dict, source: str) -> bool:
        ocid = str(release.get("ocid", "")).strip()
        release_code = str(release.get("id", "")).strip()
        if not ocid or not release_code:
            raise ValueError("Each OCDS release requires ocid and id")
        canonical = json_dump(release)
        checksum = hashlib.sha256(canonical.encode()).hexdigest()
        if tx.one(
            "SELECT id FROM ocds_releases WHERE organisation_id=? AND ocid=? AND release_id=? AND checksum=?",
            (actor.organisation_id, ocid, release_code, checksum),
        ):
            return False
        row_id = uid()
        tx.execute(
            "INSERT INTO ocds_releases(id,organisation_id,import_job_id,ocid,release_id,release_date,tag_json,source,checksum,release_json,created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (row_id, actor.organisation_id, job_id, ocid, release_code, release.get("date"),
             json_dump(release.get("tag", [])), source, checksum, canonical, now()),
        )
        tender = release.get("tender") or {}
        planning = release.get("planning") or {}
        buyer = release.get("buyer") or {}
        items = tender.get("items") or []
        cpv_codes = ",".join(sorted({str((item.get("classification") or {}).get("id", "")) for item in items if item.get("classification")}))
        value = tender.get("value") or planning.get("budget", {}).get("amount") or {}
        deadline = tender.get("tenderPeriod", {}).get("endDate")
        tags = release.get("tag") or []
        stage = tags[-1] if tags else "notice"
        tx.execute(
            "INSERT INTO notice_index(id,organisation_id,release_id,ocid,stage,title,buyer_name,cpv_codes,value_amount,currency,deadline,status) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (uid(), actor.organisation_id, row_id, ocid, stage, tender.get("title") or planning.get("rationale") or "Untitled notice",
             buyer.get("name", ""), cpv_codes, str(value.get("amount")) if value.get("amount") is not None else None,
             value.get("currency"), deadline, tender.get("status", "")),
        )
        return True

    def import_xml(self, actor: Actor, content: bytes, file_name: str) -> dict:
        actor.require("ocds.import")
        try:
            from ted_and_doffin_to_ocds.main import NoticeConverter
            from ted_and_doffin_to_ocds.utils.config import Config
        except ImportError as exc:
            raise RuntimeError("Install the optional ocds-converter extra to import eForms XML") from exc
        with tempfile.TemporaryDirectory(prefix="fastdps-ocds-") as temporary:
            root = Path(temporary)
            config = Config(
                input_path=root / Path(file_name).name,
                output_folder=root / "output",
                ocid_prefix=settings.ocid_prefix,
                scheme="eu-oj",
                db_path=root / "notices.sqlite",
                clear_db=False,
                log_level="WARNING",
            )
            converter = NoticeConverter(config)
            releases = converter._process_input_file(content)
        package = {"releases": releases}
        return self.import_json(actor, json_dump(package).encode(), f"{Path(file_name).stem}.json", "ted-doffin-xml")

    def notices(self, actor: Actor, query: str = "") -> list[dict]:
        actor.require("dps.view")
        if query.strip():
            term = f"%{query.strip().lower()}%"
            return self.db.rows(
                "SELECT * FROM notice_index WHERE organisation_id=? AND (lower(title) LIKE ? OR lower(buyer_name) LIKE ? OR lower(cpv_codes) LIKE ?) "
                "ORDER BY deadline LIMIT 100", (actor.organisation_id, term, term, term),
            )
        return self.db.rows("SELECT * FROM notice_index WHERE organisation_id=? ORDER BY deadline LIMIT 100", (actor.organisation_id,))

    def jobs(self, actor: Actor) -> list[dict]:
        actor.require("ocds.import")
        return self.db.rows("SELECT * FROM import_jobs WHERE organisation_id=? ORDER BY created_at DESC", (actor.organisation_id,))

    def export_dps(self, actor: Actor, dps_id: str) -> dict:
        actor.require("ocds.export")
        dps = self.db.one(
            "SELECT d.*,o.name buyer_name FROM dynamic_purchasing_systems d JOIN organisations o ON o.id=d.organisation_id "
            "WHERE d.id=? AND d.organisation_id=?", (dps_id, actor.organisation_id),
        )
        if not dps:
            raise LookupError("DPS not found")
        categories = self.db.rows("SELECT * FROM dps_categories WHERE dps_id=? ORDER BY code", (dps_id,))
        release = {
            "ocid": f"{settings.ocid_prefix}-{dps['id']}",
            "id": f"{settings.ocid_prefix}-{dps['id']}-{dps['updated_at'][:10]}",
            "date": dps["updated_at"],
            "tag": ["tender"],
            "initiationType": "tender",
            "buyer": {"id": actor.organisation_id, "name": dps["buyer_name"]},
            "tender": {
                "id": dps["reference"], "title": dps["title"], "description": dps["description"],
                "status": "active" if dps["status"] == "published" else dps["status"],
                "procurementMethod": "selective", "procurementMethodDetails": "Dynamic purchasing system",
                "items": [{"id": category["id"], "description": category["name"],
                           "classification": {"scheme": "CPV", "id": category["code"], "description": category["description"]}}
                          for category in categories],
                "tenderPeriod": {"startDate": dps["opens_at"], "endDate": dps["closes_at"]},
            },
        }
        if dps["estimated_value"]:
            release["tender"]["value"] = {"amount": float(dps["estimated_value"]), "currency": dps["currency"]}
        return release
