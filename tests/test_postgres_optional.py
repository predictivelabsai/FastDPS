"""Opt-in PostgreSQL parity smoke test.

Set FASTDPS_TEST_POSTGRES_URL to a disposable database. The test creates and
removes a uniquely named schema, leaving the database itself untouched.
"""
from __future__ import annotations

import os
from uuid import uuid4

import pytest

from fastdps.bootstrap import initialize
from fastdps.database import Database
from fastdps.services.identity import IdentityService


@pytest.mark.skipif(not os.getenv("FASTDPS_TEST_POSTGRES_URL"), reason="PostgreSQL test URL not supplied")
def test_postgres_migrations_and_workspace_round_trip():
    schema = f"fastdps_test_{uuid4().hex[:12]}"
    database = Database(url=os.environ["FASTDPS_TEST_POSTGRES_URL"], schema=schema)
    try:
        initialize(database)
        user, organisation = IdentityService(database).create_workspace(
            "postgres-owner@example.test", "correct horse battery staple", "PostgreSQL Owner", "Parity Workspace"
        )
        actor = IdentityService(database).actor(user["id"], organisation["id"])
        assert actor.can("roles.manage")
    finally:
        connection = database.connect()
        try:
            connection.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
            connection.commit()
        finally:
            database._release(connection)
