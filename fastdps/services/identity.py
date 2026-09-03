"""User, organisation, membership, and actor-context operations."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastdps.config import settings
from fastdps.database import Database, get_database
from fastdps.rbac import RoleService
from fastdps.security import Actor, hash_password, token, token_hash, verify_password
from fastdps.services.common import audit, now, slugify, uid


class IdentityService:
    def __init__(self, db: Database | None = None):
        self.db = db or get_database()
        self.roles = RoleService(self.db)

    def create_workspace(self, email: str, password: str | None, name: str, organisation_name: str) -> tuple[dict, dict]:
        email = email.strip().lower()
        if "@" not in email:
            raise ValueError("A valid email address is required")
        user_id, organisation_id, membership_id = uid(), uid(), uid()
        timestamp = now()
        password_hash = hash_password(password) if password else None
        is_platform_admin = int(email in settings.platform_admins)
        base_slug = slugify(organisation_name)
        slug = base_slug
        suffix = 1
        while self.db.one("SELECT id FROM organisations WHERE slug=?", (slug,)):
            suffix += 1
            slug = f"{base_slug}-{suffix}"
        with self.db.transaction() as tx:
            tx.execute(
                "INSERT INTO users(id,email,password_hash,name,is_platform_admin,created_at,updated_at) VALUES (?,?,?,?,?,?,?)",
                (user_id, email, password_hash, name.strip() or email.split("@")[0], is_platform_admin, timestamp, timestamp),
            )
            tx.execute(
                "INSERT INTO organisations(id,name,slug,kind,created_at,updated_at) VALUES (?,?,?,'buyer',?,?)",
                (organisation_id, organisation_name.strip() or "My workspace", slug, timestamp, timestamp),
            )
            tx.execute(
                "INSERT INTO memberships(id,organisation_id,user_id,status,created_at) VALUES (?,?,?,'active',?)",
                (membership_id, organisation_id, user_id, timestamp),
            )
            audit(tx, organisation_id, user_id, "workspace.created", "organisation", organisation_id, {"name": organisation_name})
        self.roles.seed_catalogue()
        seeded = self.roles.seed_roles(organisation_id)
        self.roles.assign_role(organisation_id, membership_id, seeded["Organisation Owner"])
        return self.user(user_id), self.organisation(organisation_id)

    def ensure_oauth_workspace(self, email: str, name: str) -> tuple[dict, dict]:
        existing = self.db.one("SELECT * FROM users WHERE email=?", (email.lower(),))
        if existing:
            memberships = self.memberships(existing["id"])
            if not memberships:
                raise PermissionError("This account has no active organisation membership")
            return existing, self.organisation(memberships[0]["organisation_id"])
        organisation_name = f"{name.strip() or email.split('@')[0]}'s workspace"
        return self.create_workspace(email, None, name, organisation_name)

    def authenticate(self, email: str, password: str) -> dict | None:
        user = self.db.one("SELECT * FROM users WHERE email=? AND is_active=1", (email.strip().lower(),))
        return user if user and verify_password(password, user.get("password_hash")) else None

    def user(self, user_id: str) -> dict:
        user = self.db.one("SELECT * FROM users WHERE id=?", (user_id,))
        if not user:
            raise LookupError("User not found")
        return user

    def organisation(self, organisation_id: str) -> dict:
        organisation = self.db.one("SELECT * FROM organisations WHERE id=?", (organisation_id,))
        if not organisation:
            raise LookupError("Organisation not found")
        return organisation

    def memberships(self, user_id: str) -> list[dict]:
        return self.db.rows(
            "SELECT m.*,o.name organisation_name,o.slug organisation_slug FROM memberships m "
            "JOIN organisations o ON o.id=m.organisation_id WHERE m.user_id=? AND m.status='active' ORDER BY o.name",
            (user_id,),
        )

    def actor(self, user_id: str, organisation_id: str) -> Actor:
        user = self.user(user_id)
        membership = self.db.one(
            "SELECT m.id,o.name organisation_name FROM memberships m JOIN organisations o ON o.id=m.organisation_id "
            "WHERE m.user_id=? AND m.organisation_id=? AND m.status='active'",
            (user_id, organisation_id),
        )
        if not membership and not bool(user["is_platform_admin"]):
            raise PermissionError("No active membership for this organisation")
        organisation = self.organisation(organisation_id)
        return Actor(
            user_id=user["id"], email=user["email"], name=user["name"], organisation_id=organisation_id,
            organisation_name=organisation["name"], is_platform_admin=bool(user["is_platform_admin"]),
            permissions=self.roles.permissions_for(user_id, organisation_id),
        )

    def list_members(self, actor: Actor) -> list[dict]:
        actor.require("org.manage")
        members = self.db.rows(
            "SELECT m.id,m.status,m.created_at,u.id user_id,u.email,u.name FROM memberships m "
            "JOIN users u ON u.id=m.user_id WHERE m.organisation_id=? ORDER BY u.name,u.email",
            (actor.organisation_id,),
        )
        for member in members:
            member["roles"] = self.db.rows(
                "SELECT r.id,r.name FROM membership_roles mr JOIN roles r ON r.id=mr.role_id "
                "WHERE mr.membership_id=? AND r.is_archived=0 ORDER BY r.name", (member["id"],)
            )
        return members

    def assign_role(self, actor: Actor, membership_id: str, role_id: str) -> None:
        actor.require("roles.manage")
        self.roles.assign_role(actor.organisation_id, membership_id, role_id)
        with self.db.transaction() as tx:
            audit(tx, actor.organisation_id, actor.user_id, "membership.role_assigned", "membership", membership_id, {"role_id": role_id})

    def remove_role(self, actor: Actor, membership_id: str, role_id: str) -> None:
        actor.require("roles.manage")
        role = self.roles.get_role(actor.organisation_id, role_id)
        assigned = self.db.one(
            "SELECT 1 present FROM membership_roles mr JOIN memberships m ON m.id=mr.membership_id "
            "WHERE mr.membership_id=? AND mr.role_id=? AND m.organisation_id=?",
            (membership_id, role_id, actor.organisation_id),
        )
        if not assigned:
            return
        if role["is_system"] and role["sort_order"] == 0:
            owners = int(self.db.scalar(
                "SELECT COUNT(*) FROM membership_roles mr JOIN memberships m ON m.id=mr.membership_id "
                "WHERE mr.role_id=? AND m.organisation_id=? AND m.status='active'", (role_id, actor.organisation_id),
            ) or 0)
            if owners <= 1:
                raise ValueError("The last organisation owner cannot lose the owner role")
        with self.db.transaction() as tx:
            tx.execute("DELETE FROM membership_roles WHERE membership_id=? AND role_id=?", (membership_id, role_id))
            audit(tx, actor.organisation_id, actor.user_id, "membership.role_removed", "membership", membership_id, {"role_id": role_id})

    def invite(self, actor: Actor, email: str, role_ids: list[str]) -> tuple[dict, str]:
        actor.require("org.manage")
        email = email.strip().lower()
        if "@" not in email:
            raise ValueError("A valid email address is required")
        for role_id in role_ids:
            self.roles.get_role(actor.organisation_id, role_id)
        raw_token, invitation_id = token(), uid()
        expires = (datetime.now(UTC) + timedelta(days=7)).isoformat()
        with self.db.transaction() as tx:
            tx.execute(
                "INSERT INTO invitations(id,organisation_id,email,token_hash,status,expires_at,invited_by,created_at) "
                "VALUES (?,?,?,?,'pending',?,?,?)",
                (invitation_id, actor.organisation_id, email, token_hash(raw_token), expires, actor.user_id, now()),
            )
            for role_id in role_ids:
                tx.execute("INSERT INTO invitation_roles(invitation_id,role_id) VALUES (?,?)", (invitation_id, role_id))
            audit(tx, actor.organisation_id, actor.user_id, "member.invited", "invitation", invitation_id, {"email": email})
        return self.db.one("SELECT * FROM invitations WHERE id=?", (invitation_id,)), raw_token

    def invitations(self, actor: Actor) -> list[dict]:
        actor.require("org.manage")
        return self.db.rows(
            "SELECT i.*,u.name invited_by_name FROM invitations i JOIN users u ON u.id=i.invited_by "
            "WHERE i.organisation_id=? ORDER BY i.created_at DESC", (actor.organisation_id,),
        )

    def invitation(self, raw_token: str) -> dict | None:
        invitation = self.db.one(
            "SELECT i.*,o.name organisation_name FROM invitations i JOIN organisations o ON o.id=i.organisation_id "
            "WHERE i.token_hash=?", (token_hash(raw_token),),
        )
        if invitation:
            invitation["roles"] = self.db.rows(
                "SELECT r.id,r.name FROM invitation_roles ir JOIN roles r ON r.id=ir.role_id WHERE ir.invitation_id=?",
                (invitation["id"],),
            )
        return invitation

    def accept_invitation(self, user_id: str, raw_token: str) -> dict:
        invitation = self.invitation(raw_token)
        user = self.user(user_id)
        if not invitation or invitation["status"] != "pending" or invitation["expires_at"] < now():
            raise ValueError("Invitation is invalid or expired")
        if invitation["email"] != user["email"]:
            raise PermissionError("Invitation email does not match the signed-in account")
        membership = self.db.one(
            "SELECT * FROM memberships WHERE organisation_id=? AND user_id=?", (invitation["organisation_id"], user_id),
        )
        membership_id = membership["id"] if membership else uid()
        with self.db.transaction() as tx:
            if membership:
                tx.execute("UPDATE memberships SET status='active' WHERE id=?", (membership_id,))
            else:
                tx.execute("INSERT INTO memberships(id,organisation_id,user_id,status,created_at) VALUES (?,?,?,'active',?)",
                           (membership_id, invitation["organisation_id"], user_id, now()))
            for role in invitation["roles"]:
                tx.execute("INSERT INTO membership_roles(membership_id,role_id) VALUES (?,?) ON CONFLICT DO NOTHING", (membership_id, role["id"]))
            tx.execute("UPDATE invitations SET status='accepted' WHERE id=?", (invitation["id"],))
            audit(tx, invitation["organisation_id"], user_id, "member.joined", "membership", membership_id)
        return self.organisation(invitation["organisation_id"])
