from __future__ import annotations

import pytest

from fastdps.services.chat import ChatService
from fastdps.services.procurement import ProcurementService


def test_chat_write_is_previewed_then_confirmed_once(db, owner):
    service = ChatService(db)
    session_id, events = service.respond(owner, "Create a DPS for facilities management")
    artifact = next(payload for name, payload in events if name == "artifact")
    assert artifact["kind"] == "confirmation"
    assert db.scalar("SELECT COUNT(*) FROM dynamic_purchasing_systems") == 0
    result = service.confirm(owner, artifact["action_id"])
    assert result["action"] == "dps.create"
    assert db.scalar("SELECT COUNT(*) FROM dynamic_purchasing_systems") == 1
    with pytest.raises(ValueError, match="no longer pending"):
        service.confirm(owner, artifact["action_id"])
    assert len(service.messages(owner, session_id)) == 2


def test_chat_read_tools_return_structured_artifacts(db, owner):
    service = ChatService(db)
    _, events = service.respond(owner, "List DPS")
    artifact = next(payload for name, payload in events if name == "artifact")
    assert artifact["kind"] == "dps_list"
    assert artifact["items"] == []


def test_unknown_chat_request_has_no_side_effect(db, owner):
    _, events = ChatService(db).respond(owner, "Explain how continuous admission works")
    assert not any(name == "artifact" and payload.get("kind") == "confirmation" for name, payload in events)
    assert db.scalar("SELECT COUNT(*) FROM dynamic_purchasing_systems") == 0


def _confirm(service, owner, message):
    _, events = service.respond(owner, message)
    artifact = next(payload for name, payload in events if name == "artifact")
    assert artifact["kind"] == "confirmation"
    return service.confirm(owner, artifact["action_id"])["result"]


def test_chat_can_build_and_publish_a_competition(db, owner):
    chat = ChatService(db)
    dps = ProcurementService(db).create_dps(owner, "Technology services")
    category = _confirm(chat, owner, f"add category {dps['id']} | 72000000 | IT services")
    assert category["code"] == "72000000"
    criterion = _confirm(chat, owner, f"add qualification criterion {dps['id']} | Relevant delivery history")
    assert criterion["name"] == "Relevant delivery history"
    assert _confirm(chat, owner, f"publish DPS {dps['id']}")["status"] == "published"

    competition = _confirm(chat, owner, f"create competition {dps['id']} | Cloud discovery")
    scoring = _confirm(chat, owner, f"add evaluation criterion {competition['id']} | Quality | 100")
    assert scoring["weight"] == "100"
    assert _confirm(chat, owner, f"publish competition {competition['id']}")["status"] == "published"

    _, events = chat.respond(owner, "list competitions")
    artifact = next(payload for name, payload in events if name == "artifact")
    assert artifact["kind"] == "competition_list"
    assert artifact["items"][0]["id"] == competition["id"]
