"""H-MEM and the Meterless Web handoff. No live Nightshift call is made here."""

from agent.orchestrator import investigate
from integrations.hmem import Hmem, embed
from integrations.nightshift_web import prepare_task, record_cockpit_answer
from tests.test_investigation import FIXED_ENV, Recorder
from agent.config import load_settings
from integrations.http import HttpResponse
from integrations.meterless_engine import ScoutIntent
from integrations.meterless_nightshift import NightshiftClient
from integrations.zetaris import ZetarisClient


def test_hmem_rejects_a_record_without_a_source():
    memory = Hmem()
    try:
        memory.remember(content="A permit row.", source="  ", origin="document")
    except ValueError as error:
        assert "source" in str(error)
    else:
        raise AssertionError("a sourceless record was stored")
    assert memory.memories == []


def test_hmem_recalls_a_related_record_and_keeps_its_provenance():
    memory = Hmem(clock_ms=lambda: 1_700_000_000_000)
    stored = memory.remember(
        content="housing permits recorded in planning.permits record-1 permit_id A-1 status open",
        source="zetaris:record-1",
        origin="document",
        memory_type="factual",
        tags=["project:planning", "evidence"],
        refs=["record-1"],
        label="Zetaris retrieved row",
        confidence=0.9,
    )
    recalled = memory.query("Which housing permits are recorded?")
    assert recalled["memories"]
    assert recalled["memories"][0]["id"] == stored["id"]
    assert recalled["memories"][0]["standing"] == "retrieved_evidence"
    assert recalled["memories"][0]["provenance"]["refs"] == ["record-1"]
    unrelated = memory.query("glacier ice thickness")
    assert all(item["id"] != stored["id"] for item in unrelated["memories"])


def test_cockpit_answer_is_an_interpretation_and_not_a_finding():
    memory = Hmem()
    recorded = record_cockpit_answer(
        memory,
        question="Which permits are recorded?",
        answer="The only cited row is A-1, and that is an interpretation.",
        record_ids=["record-1"],
    )
    assert recorded["standing"] == "ai_interpretation"
    assert recorded["provenance"]["origin"] == "model_response"
    assert recorded["source"] == "meterless-web-cockpit"
    task = prepare_task("Which permits are recorded?", [], "")
    assert task["automated"] is False
    assert task["api_call"] is False
    assert task["organizer_confirmation_required"] is True
    assert task["url"] == "https://meterless.ai/Nightshift/WEB"
    assert "8088" not in task["prompt"]
    assert "No planning records were retrieved" in task["prompt"]
    assert "Nairobi or Kilimani" in task["prompt"]


def test_second_investigation_recalls_the_first_question():
    memory = Hmem(clock_ms=lambda: 1_700_000_000_000)
    settings = load_settings({}, load_env_file=False)
    scout = ScoutIntent("test-signing-key")
    first = investigate(
        "Which housing permits are in the registered records?",
        settings,
        scout=scout,
        zetaris=ZetarisClient(settings, Recorder(lambda *args: HttpResponse(500, None, ""))),
        nightshift=NightshiftClient(settings, Recorder(lambda *args: HttpResponse(500, None, ""))),
        hmem=memory,
    )
    assert first.findings == []
    assert first.nightshift_handoff["api_call"] is False
    assert first.prior_memories == []
    second = investigate(
        "Which housing permits are in the registered records?",
        settings,
        scout=scout,
        zetaris=ZetarisClient(settings, Recorder(lambda *args: HttpResponse(500, None, ""))),
        nightshift=NightshiftClient(settings, Recorder(lambda *args: HttpResponse(500, None, ""))),
        hmem=memory,
    )
    assert any(item["source"] == "user" for item in second.prior_memories)
    assert second.findings == []


def test_token_hash_embedding_is_stable():
    assert embed("housing permits") == embed("housing permits")
    assert abs(sum(value * value for value in embed("housing permits")) - 1) < 1e-9


def test_configured_nightshift_path_does_not_become_a_browser_handoff():
    settings = load_settings(dict(FIXED_ENV), load_env_file=False)

    def zetaris_transport(method, url, headers, body, timeout):
        return HttpResponse(200, {"headers": ["permit_id"], "data": [["A-1"]]}, "")

    def nightshift_transport(method, url, headers, body, timeout):
        content = '{"findings":[{"statement":"Permit A-1 is open.","record_ids":["record-1"]}]}'
        return HttpResponse(
            200,
            {
                "model": "gpt-oss-20b-nvidia-test",
                "choices": [{"message": {"content": content}}],
            },
            "",
        )

    brief = investigate(
        "Which housing permits are in the registered records?",
        settings,
        scout=ScoutIntent("test-signing-key"),
        zetaris=ZetarisClient(settings, zetaris_transport),
        nightshift=NightshiftClient(settings, nightshift_transport),
    )
    assert brief.nightshift_handoff is None
    assert brief.findings[0].statement == "Permit A-1 is open."
