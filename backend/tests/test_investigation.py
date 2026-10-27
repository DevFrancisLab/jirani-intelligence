"""Workflow tests. They prove the desk does not invent records when services are absent."""

import json

from agent.config import load_settings
from agent.orchestrator import investigate
from integrations.http import HttpResponse
from integrations.meterless_engine import ScoutIntent
from integrations.meterless_nightshift import NightshiftClient
from integrations.zetaris import ZetarisClient

FIXED_ENV = {
    "ZETARIS_BASE_URL": "http://localhost:3000",
    "ZETARIS_ORG_ID": "7",
    "ZETARIS_API_KEY": "test-api-key",
    "ZETARIS_SOURCES": "planning.permits|Permit rows",
    "METERLESS_ENABLED": "true",
    "METERLESS_BASE_URL": "http://127.0.0.1:8088/v1",
    "METERLESS_API_KEY": "test-runtime-token",
    "METERLESS_MODEL": "gpt-oss-20b-nvidia-test",
    "SCOUT_SIGNING_KEY": "test-signing-key",
}


class Recorder:
    def __init__(self, responder):
        self.calls = []
        self.responder = responder

    def __call__(self, method, url, headers, body, timeout):
        self.calls.append(body)
        return self.responder(method, url, headers, body, timeout)


def test_unconfigured_investigation_invents_nothing():
    calls = []

    def transport(*args):
        calls.append(args)
        raise AssertionError("no service should be called")

    settings = load_settings({}, load_env_file=False)
    brief = investigate(
        "Which housing permits are recorded?",
        settings,
        scout=ScoutIntent("test-signing-key"),
        zetaris=ZetarisClient(settings, transport),
        nightshift=NightshiftClient(settings, transport),
    )
    assert calls == []
    assert brief.findings == []
    assert brief.supporting_records == []
    blob = json.dumps(
        {
            "findings": brief.as_dict()["findings"],
            "supporting_records": brief.as_dict()["supporting_records"],
            "evidence_gaps": brief.evidence_gaps,
            "uncertainty": brief.uncertainty,
        }
    )
    assert "Nairobi" not in blob
    assert "population" not in blob.lower()
    assert any(layer.name == "Zetaris" and layer.state == "not_routed" for layer in brief.layer_status)
    assert any("ZETARIS_BASE_URL" in step for step in brief.next_steps)
    assert brief.nightshift_handoff is not None
    assert brief.nightshift_handoff["api_call"] is False
    assert "not evidence about Nairobi or Kilimani" in brief.nightshift_handoff["prompt"]
    assert any(layer.name == "Meterless Nightshift" and layer.state == "browser_handoff" for layer in brief.layer_status)


def test_retrieved_rows_are_the_only_records_sent_to_nightshift():
    def zetaris_transport(method, url, headers, body, timeout):
        assert body["sql"] == "SELECT * FROM planning.permits LIMIT 25"
        return HttpResponse(
            200,
            {"headers": ["permit_id", "status"], "data": [["A-1", "open"]]},
            "",
        )

    def nightshift_transport(method, url, headers, body, timeout):
        user = body["messages"][1]["content"]
        assert "A-1" in user
        assert "test-runtime-token" not in user
        assert "test-api-key" not in user
        content = json.dumps(
            {"findings": [{"statement": "Record A-1 is open.", "record_ids": ["record-1"]}]}
        )
        return HttpResponse(200, {"choices": [{"message": {"content": content}}]}, "")

    settings = load_settings(FIXED_ENV, load_env_file=False)
    brief = investigate(
        "Which housing permits are recorded?",
        settings,
        scout=ScoutIntent(settings.scout_signing_key),
        zetaris=ZetarisClient(settings, zetaris_transport),
        nightshift=NightshiftClient(settings, nightshift_transport),
    )
    assert [record.fields["permit_id"] for record in brief.supporting_records] == ["A-1"]
    assert brief.findings[0].statement == "Record A-1 is open."
    assert brief.findings[0].record_ids == ["record-1"]


def test_sample_databases_never_become_planning_evidence():
    def transport(method, url, headers, body, timeout):
        if "chat/completions" in url:
            raise AssertionError("Nightshift should not reason over sample rows")
        if "DATASOURCES" in body["sql"]:
            return HttpResponse(200, {"headers": ["name"], "data": [["NY_TAXI"]]}, "")
        return HttpResponse(200, {"headers": ["database"], "data": [["TPCDS_DB"]]}, "")

    env = dict(FIXED_ENV)
    env["ZETARIS_SOURCES"] = ""
    env["METERLESS_API_KEY"] = "test-runtime-token"
    settings = load_settings(env, load_env_file=False)
    brief = investigate(
        "What data sources are registered?",
        settings,
        scout=ScoutIntent(settings.scout_signing_key),
        zetaris=ZetarisClient(settings, transport),
        nightshift=NightshiftClient(settings, transport),
    )
    assert brief.supporting_records == []
    assert brief.findings == []
    assert any("sample" in gap.lower() for gap in brief.evidence_gaps)


def test_refused_contract_does_not_query():
    settings = load_settings(FIXED_ENV, load_env_file=False)
    scout = ScoutIntent(settings.scout_signing_key)

    class Refusing(ScoutIntent):
        def verify(self, contract, **kwargs):
            return "tampered"

    calls = []
    brief = investigate(
        "Which housing permits are recorded?",
        settings,
        scout=Refusing(settings.scout_signing_key),
        zetaris=ZetarisClient(settings, lambda *args: calls.append(args)),
        nightshift=NightshiftClient(settings, lambda *args: calls.append(args)),
    )
    assert calls == []
    assert any("tampered" in gap for gap in brief.evidence_gaps)
    assert scout.verify(scout.decide("catalog").contract) is None


def test_blank_question_does_nothing():
    brief = investigate("  ", load_settings({}, load_env_file=False))
    assert brief.supporting_records == []
    assert brief.findings == []
