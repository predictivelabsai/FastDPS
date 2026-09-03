"""Organisation-scoped dynamic roles over a fixed permission catalogue."""
from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from fastdps.database import Database, get_database
from fastdps.services.common import audit


PERMISSIONS: tuple[tuple[str, str, str, str], ...] = (
    ("org.manage", "Manage organisation", "Manage members and organisation settings.", "Administration"),
    ("roles.manage", "Manage roles", "Create roles and assign their rights.", "Administration"),
    ("dps.view", "View DPS", "View dynamic purchasing systems.", "DPS"),
    ("dps.create", "Create DPS", "Create dynamic purchasing systems.", "DPS"),
    ("dps.edit", "Edit DPS", "Edit draft or published system details.", "DPS"),
    ("dps.publish", "Publish DPS", "Publish, close, or archive a DPS.", "DPS"),
    ("suppliers.view", "View suppliers", "View supplier profiles and applications.", "Suppliers"),
    ("suppliers.review", "Review suppliers", "Review and request clarification.", "Suppliers"),
    ("suppliers.admit", "Decide admission", "Admit, reject, or suspend suppliers.", "Suppliers"),
    ("competitions.view", "View competitions", "View call-off competitions.", "Competitions"),
    ("competitions.manage", "Manage competitions", "Create, invite, publish, and close competitions.", "Competitions"),
    ("submissions.view", "View submissions", "View competition submissions.", "Evaluation"),
    ("submissions.evaluate", "Evaluate submissions", "Declare conflicts and score submissions.", "Evaluation"),
    ("awards.view", "View awards", "View award recommendations and contracts.", "Awards"),
    ("awards.approve", "Approve awards", "Approve and publish award decisions.", "Awards"),
    ("documents.manage", "Manage documents", "Upload and version procurement documents.", "Documents"),
    ("audit.view", "View audit", "Inspect the immutable activity trail.", "Governance"),
    ("chat.use", "Use assistant", "Use chat and allowed procurement tools.", "Assistant"),
    ("ocds.import", "Import OCDS", "Import OCDS JSON or supported eForms XML.", "Open data"),
    ("ocds.export", "Export OCDS", "Export procurement records as OCDS JSON.", "Open data"),
)

ALL_KEYS = frozenset(item[0] for item in PERMISSIONS)

DEFAULT_ROLES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("Organisation Owner", "Full control of one organisation.", tuple(sorted(ALL_KEYS))),
    ("Procurement Administrator", "Configure and operate procurement workflows.", tuple(k for k in ALL_KEYS if k != "roles.manage")),
    ("Procurement Manager", "Create systems, review suppliers, and manage competitions.", (
        "dps.view", "dps.create", "dps.edit", "dps.publish", "suppliers.view", "suppliers.review",
        "suppliers.admit", "competitions.view", "competitions.manage", "submissions.view",
        "awards.view", "documents.manage", "audit.view", "chat.use", "ocds.import", "ocds.export",
    )),
    ("Evaluator", "Score submissions without award authority.", (
        "dps.view", "competitions.view", "submissions.view", "submissions.evaluate", "documents.manage", "chat.use",
    )),
    ("Approver", "Review procurement and approve awards.", (
        "dps.view", "suppliers.view", "competitions.view", "submissions.view", "awards.view", "awards.approve", "audit.view", "chat.use",
    )),
    ("Auditor", "Read-only governance and audit access.", (
        "dps.view", "suppliers.view", "competitions.view", "submissions.view", "awards.view", "audit.view", "ocds.export",
    )),
    ("Viewer", "Read-only procurement access.", ("dps.view", "competitions.view", "awards.view")),
    ("Supplier Administrator", "Manage the supplier profile and applications.", ("dps.view", "competitions.view", "chat.use")),
    ("Supplier Contributor", "Contribute to supplier responses.", ("dps.view", "competitions.view", "chat.use")),
)


def now() -> str:
    return datetime.now(UTC).isoformat()


class RoleService:
    def __init__(self, db: Database | None = None):
        self.db = db or get_database()

    def seed_catalogue(self) -> None:
        with self.db.transaction() as tx:
            for item in PERMISSIONS:
                tx.execute(
                    "INSERT INTO permissions(key,name,description,category) VALUES (?,?,?,?) "
                    "ON CONFLICT(key) DO UPDATE SET name=excluded.name,description=excluded.description,category=excluded.category",
                    item,
                )

    def seed_roles(self, organisation_id: str) -> dict[str, str]:
        result: dict[str, str] = {}
        with self.db.transaction() as tx:
            for order, (name, description, keys) in enumerate(DEFAULT_ROLES):
                existing = tx.one("SELECT id FROM roles WHERE organisation_id=? AND name=?", (organisation_id, name))
                role_id = existing["id"] if existing else str(uuid4())
                if not existing:
                    tx.execute(
                        "INSERT INTO roles(id,organisation_id,name,description,is_system,sort_order,created_at,updated_at) "
                        "VALUES (?,?,?,?,1,?,?,?)",
                        (role_id, organisation_id, name, description, order, now(), now()),
                    )
                for key in keys:
                    tx.execute(
                        "INSERT INTO role_permissions(role_id,permission_key) VALUES (?,?) ON CONFLICT DO NOTHING",
                        (role_id, key),
                    )
                result[name] = role_id
        return result

    def list_permissions(self) -> list[dict]:
        return self.db.rows("SELECT * FROM permissions ORDER BY category,name")

    def list_roles(self, organisation_id: str) -> list[dict]:
        roles = self.db.rows(
            "SELECT * FROM roles WHERE organisation_id=? AND is_archived=0 ORDER BY sort_order,name",
            (organisation_id,),
        )
        for role in roles:
            role["permissions"] = [row["permission_key"] for row in self.db.rows(
                "SELECT permission_key FROM role_permissions WHERE role_id=? ORDER BY permission_key", (role["id"],)
            )]
        return roles

    def create_role(self, organisation_id: str, name: str, description: str, permissions: list[str], actor_user_id: str | None = None) -> dict:
        clean_name = name.strip()
        if not clean_name:
            raise ValueError("Role name is required")
        unknown = set(permissions) - ALL_KEYS
        if unknown:
            raise ValueError(f"Unknown permissions: {', '.join(sorted(unknown))}")
        role_id = str(uuid4())
        with self.db.transaction() as tx:
            tx.execute(
                "INSERT INTO roles(id,organisation_id,name,description,is_system,sort_order,created_at,updated_at) "
                "VALUES (?,?,?,?,0,100,?,?)",
                (role_id, organisation_id, clean_name, description.strip(), now(), now()),
            )
            for key in sorted(set(permissions)):
                tx.execute("INSERT INTO role_permissions(role_id,permission_key) VALUES (?,?)", (role_id, key))
            if actor_user_id:
                audit(tx, organisation_id, actor_user_id, "role.created", "role", role_id, {"permissions": sorted(set(permissions))})
        return self.get_role(organisation_id, role_id)

    def get_role(self, organisation_id: str, role_id: str) -> dict:
        role = self.db.one("SELECT * FROM roles WHERE id=? AND organisation_id=?", (role_id, organisation_id))
        if not role:
            raise LookupError("Role not found")
        role["permissions"] = [row["permission_key"] for row in self.db.rows(
            "SELECT permission_key FROM role_permissions WHERE role_id=? ORDER BY permission_key", (role_id,)
        )]
        return role

    def update_role(self, organisation_id: str, role_id: str, name: str, description: str, permissions: list[str], actor_user_id: str | None = None) -> dict:
        role = self.get_role(organisation_id, role_id)
        unknown = set(permissions) - ALL_KEYS
        if unknown:
            raise ValueError(f"Unknown permissions: {', '.join(sorted(unknown))}")
        if role["is_system"] and role["sort_order"] == 0 and not {"org.manage", "roles.manage"}.issubset(permissions):
            raise ValueError("The owner role must retain organisation and role management rights")
        with self.db.transaction() as tx:
            tx.execute(
                "UPDATE roles SET name=?,description=?,updated_at=? WHERE id=? AND organisation_id=?",
                (name.strip() or role["name"], description.strip(), now(), role_id, organisation_id),
            )
            tx.execute("DELETE FROM role_permissions WHERE role_id=?", (role_id,))
            for key in sorted(set(permissions)):
                tx.execute("INSERT INTO role_permissions(role_id,permission_key) VALUES (?,?)", (role_id, key))
            if actor_user_id:
                audit(tx, organisation_id, actor_user_id, "role.updated", "role", role_id, {"permissions": sorted(set(permissions))})
        return self.get_role(organisation_id, role_id)

    def archive_role(self, organisation_id: str, role_id: str, actor_user_id: str | None = None) -> None:
        role = self.get_role(organisation_id, role_id)
        if role["is_system"] and role["sort_order"] == 0:
            raise ValueError("The Organisation Owner role cannot be archived")
        with self.db.transaction() as tx:
            tx.execute("DELETE FROM membership_roles WHERE role_id=?", (role_id,))
            tx.execute("UPDATE roles SET is_archived=1,updated_at=? WHERE id=? AND organisation_id=?", (now(), role_id, organisation_id))
            if actor_user_id:
                audit(tx, organisation_id, actor_user_id, "role.archived", "role", role_id)

    def assign_role(self, organisation_id: str, membership_id: str, role_id: str) -> None:
        membership = self.db.one("SELECT id FROM memberships WHERE id=? AND organisation_id=?", (membership_id, organisation_id))
        self.get_role(organisation_id, role_id)
        if not membership:
            raise LookupError("Membership not found")
        with self.db.transaction() as tx:
            tx.execute("INSERT INTO membership_roles(membership_id,role_id) VALUES (?,?) ON CONFLICT DO NOTHING", (membership_id, role_id))

    def permissions_for(self, user_id: str, organisation_id: str) -> frozenset[str]:
        rows = self.db.rows(
            "SELECT DISTINCT rp.permission_key FROM memberships m "
            "JOIN membership_roles mr ON mr.membership_id=m.id "
            "JOIN roles r ON r.id=mr.role_id AND r.organisation_id=m.organisation_id "
            "JOIN role_permissions rp ON rp.role_id=r.id "
            "WHERE m.user_id=? AND m.organisation_id=? AND m.status='active' AND r.is_archived=0",
            (user_id, organisation_id),
        )
        return frozenset(row["permission_key"] for row in rows)
