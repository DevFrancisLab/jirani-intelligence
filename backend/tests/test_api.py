"""Django API smoke tests. No live provider charges."""

import json

import pytest
from django.test import Client

from agent.config import load_settings


@pytest.fixture
def client():
    return Client()


def test_health_and_public_status_hide_secrets(client):
    health = client.get("/api/health/")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"

    status = client.get("/api/status/")
    assert status.status_code == 200
    body = status.json()
    blob = json.dumps(body)
    assert "nsk_" not in blob
    assert "Bearer" not in blob
    assert "zetaris_configured" in body
    assert "nightshift_api_key_set" in body
    assert body.get("nvidia_label_is_not_proof") is True


def test_investigation_requires_question(client):
    response = client.post(
        "/api/investigations/",
        data=json.dumps({}),
        content_type="application/json",
    )
    assert response.status_code == 400


def test_investigation_without_planning_sources_invents_nothing(client, monkeypatch):
    settings = load_settings(
        {
            "ZETARIS_BASE_URL": "http://localhost:3000",
            "ZETARIS_ORG_ID": "1",
            "ZETARIS_API_KEY": "test",
            "METERLESS_ENABLED": "false",
            "SCOUT_SIGNING_KEY": "test-signing-key",
        },
        load_env_file=False,
    )

    from apps.investigations import services
    from agent.orchestrator import investigate
    from integrations.hmem import Hmem

    monkeypatch.setattr(
        services,
        "run_investigation",
        lambda question: investigate(question, settings, hmem=Hmem()).as_dict(),
    )
    response = client.post(
        "/api/investigations/",
        data=json.dumps({"question": "Which housing permits are recorded?"}),
        content_type="application/json",
    )
    assert response.status_code == 200
    body = response.json()
    assert body["findings"] == []
    assert body["supporting_records"] == []
    assert body["nightshift_handoff"]["api_call"] is False
    assert "population" not in json.dumps(body["findings"] + body["supporting_records"]).lower()
