"""Application initialization and deterministic local demonstration data."""
from __future__ import annotations

from fastdps.database import Database, get_database
from fastdps.rbac import RoleService
from fastdps.services.identity import IdentityService
from fastdps.services.procurement import ProcurementService


DEMO_EMAIL = "demo@fastdps.local"


def initialize(db: Database | None = None) -> list[str]:
    db = db or get_database()
    applied = db.migrate()
    RoleService(db).seed_catalogue()
    return applied


def ensure_demo(db: Database | None = None) -> tuple[dict, dict]:
    db = db or get_database()
    identity = IdentityService(db)
    existing = db.one("SELECT * FROM users WHERE email=?", (DEMO_EMAIL,))
    if existing:
        membership = identity.memberships(existing["id"])[0]
        return existing, identity.organisation(membership["organisation_id"])
    user, organisation = identity.create_workspace(DEMO_EMAIL, None, "Demo User", "Open Procurement Demo")
    ProcurementService(db).seed_workflows(organisation["id"])
    actor = identity.actor(user["id"], organisation["id"])
    dps = ProcurementService(db).create_dps(
        actor, "Digital and cloud services", "An open system for qualified digital service suppliers.",
        reference="DPS-DEMO-001", estimated_value="2500000", opens_at="2026-01-01T00:00:00Z", closes_at="2030-12-31T23:59:59Z",
    )
    ProcurementService(db).add_category(actor, dps["id"], "72000000", "IT services", "Software, cloud, data, and support services.")
    ProcurementService(db).add_criterion(actor, dps["id"], "Relevant delivery capability", "Provide evidence of comparable delivery experience.")
    ProcurementService(db).transition_dps(actor, dps["id"], "published")
    return user, organisation
