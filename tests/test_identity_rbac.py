from __future__ import annotations

import pytest

from fastdps.rbac import RoleService
from fastdps.services.identity import IdentityService


def test_default_roles_and_dynamic_role_rights(db, owner):
    service = RoleService(db)
    roles = service.list_roles(owner.organisation_id)
    assert {role["name"] for role in roles} >= {"Organisation Owner", "Evaluator", "Auditor", "Supplier Contributor"}
    custom = service.create_role(owner.organisation_id, "Category Lead", "Runs one category", ["dps.view", "dps.edit"], owner.user_id)
    assert custom["permissions"] == ["dps.edit", "dps.view"]
    updated = service.update_role(owner.organisation_id, custom["id"], "Technology Lead", "Updated", ["dps.view", "competitions.view"], owner.user_id)
    assert updated["name"] == "Technology Lead"
    assert updated["permissions"] == ["competitions.view", "dps.view"]
    service.archive_role(owner.organisation_id, custom["id"], owner.user_id)
    assert custom["id"] not in {role["id"] for role in service.list_roles(owner.organisation_id)}


def test_owner_role_cannot_be_weakened_or_archived(db, owner):
    service = RoleService(db)
    owner_role = next(role for role in service.list_roles(owner.organisation_id) if role["sort_order"] == 0)
    with pytest.raises(ValueError, match="owner role"):
        service.update_role(owner.organisation_id, owner_role["id"], "Renamed owner", "", ["dps.view"], owner.user_id)
    with pytest.raises(ValueError, match="cannot be archived"):
        service.archive_role(owner.organisation_id, owner_role["id"], owner.user_id)


def test_invitation_acceptance_and_last_owner_guard(db, owner):
    identity = IdentityService(db)
    viewer_role = next(role for role in identity.roles.list_roles(owner.organisation_id) if role["name"] == "Viewer")
    invitation, raw = identity.invite(owner, "member@example.test", [viewer_role["id"]])
    assert invitation["status"] == "pending"
    member_user, _ = identity.create_workspace("member@example.test", "a-secure-member-password", "Member", "Personal Workspace")
    joined = identity.accept_invitation(member_user["id"], raw)
    assert joined["id"] == owner.organisation_id
    member_actor = identity.actor(member_user["id"], owner.organisation_id)
    assert member_actor.can("dps.view")
    assert not member_actor.can("dps.create")
    with pytest.raises(PermissionError):
        identity.list_members(member_actor)

    owner_membership = next(item for item in identity.list_members(owner) if item["user_id"] == owner.user_id)
    owner_role = next(role for role in identity.roles.list_roles(owner.organisation_id) if role["sort_order"] == 0)
    with pytest.raises(ValueError, match="last organisation owner"):
        identity.remove_role(owner, owner_membership["id"], owner_role["id"])


def test_cross_tenant_role_lookup_is_rejected(db, owner):
    identity = IdentityService(db)
    other_user, other_org = identity.create_workspace("other@example.test", "another-secure-password", "Other", "Other Buyer")
    other_actor = identity.actor(other_user["id"], other_org["id"])
    foreign_role = RoleService(db).list_roles(other_actor.organisation_id)[0]
    with pytest.raises(LookupError):
        RoleService(db).get_role(owner.organisation_id, foreign_role["id"])
