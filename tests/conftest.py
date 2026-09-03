from __future__ import annotations

import pytest

from fastdps.bootstrap import initialize
from fastdps.database import Database, set_database
from fastdps.services.identity import IdentityService
from fastdps.services.procurement import ProcurementService


@pytest.fixture
def db(tmp_path):
    database = Database(path=tmp_path / "fastdps.sqlite")
    set_database(database)
    initialize(database)
    yield database
    set_database(None)


@pytest.fixture
def owner(db):
    identity = IdentityService(db)
    user, organisation = identity.create_workspace(
        "owner@example.test", "correct horse battery staple", "Workspace Owner", "Example Procurement",
    )
    ProcurementService(db).seed_workflows(organisation["id"])
    return identity.actor(user["id"], organisation["id"])
