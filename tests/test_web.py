from __future__ import annotations

import re

from starlette.testclient import TestClient


def test_public_landing_and_authenticated_workspace(db):
    import web_app

    with TestClient(web_app.app) as client:
        landing = client.get("/")
        assert landing.status_code == 200
        assert "Run fair, flexible procurement" in landing.text
        assert 'href="/login"' in landing.text
        assert 'rel="canonical"' in landing.text
        assert "https://github.com/predictivelabsai/FastDPS" in landing.text
        assert client.get("/robots.txt").status_code == 200
        assert "sitemap.xml" in client.get("/robots.txt").text
        assert client.get("/sitemap.xml").headers["content-type"].startswith("application/xml")
        assert client.get("/developers", follow_redirects=False).status_code == 303
        response = client.post("/signup", data={
            "name": "Browser User", "organisation": "Browser Buyer", "email": "browser@example.test",
            "password": "browser-secure-password",
        }, follow_redirects=False)
        assert response.status_code == 303
        workspace = client.get("/app")
        assert workspace.status_code == 200
        assert "What would you like to move forward?" in workspace.text
        for path in ("/dps", "/suppliers", "/competitions", "/documents", "/imports", "/supplier", "/admin/roles", "/audit"):
            assert client.get(path).status_code == 200


def test_chat_http_requires_csrf_and_streams_typed_events(db):
    import web_app

    with TestClient(web_app.app) as client:
        client.post("/signup", data={"name": "Chat User", "organisation": "Chat Buyer", "email": "chat@example.test", "password": "chat-secure-password"})
        page = client.get("/app")
        csrf = re.search(r"window\.FASTDPS_CSRF='([^']+)'", page.text).group(1)
        assert client.post("/api/chat/stream", data={"message": "List DPS"}).status_code == 403
        response = client.post("/api/chat/stream", data={"message": "List DPS"}, headers={"X-CSRF-Token": csrf})
        assert response.status_code == 200
        assert "event: artifact" in response.text
        assert "event: done" in response.text


def test_api_docs_and_health_are_available(db):
    import web_app

    with TestClient(web_app.app) as client:
        assert client.get("/healthz").json()["database"]["dialect"] == "sqlite"
        assert client.get("/api/v1/health").json()["product"] == "FastDPS"
        schema = client.get("/api/v1/openapi.json").json()
        assert "/dps" in schema["paths"]
        assert "/roles/{role_id}" in schema["paths"]
        assert "/workflows/{workflow_id}/transitions" in schema["paths"]
        assert "/documents/{document_id}/versions" in schema["paths"]
        assert "/awards/{award_id}/contracts" in schema["paths"]
        assert "/ocds/notices" in schema["paths"]
