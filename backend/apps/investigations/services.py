"""Thin wrappers that keep secrets and integrations on the server."""

from __future__ import annotations

from typing import Any

from django.conf import settings as django_settings

from agent.config import load_settings
from agent.orchestrator import investigate
from integrations.hmem import Hmem
from integrations.meterless_engine import ScoutIntent
from integrations.meterless_nightshift import NightshiftClient
from integrations.nightshift_web import record_cockpit_answer
from integrations.zetaris import ZetarisClient


def _memory() -> Hmem:
    path = getattr(django_settings, "HMEM_PATH", None)
    return Hmem(path)


def public_status() -> dict[str, Any]:
    settings = load_settings()
    view = settings.public_view()
    memory = _memory()
    return {
        "zetaris_configured": view["zetaris_configured"],
        "registered_sources": view["registered_sources"],
        "registered_source_count": view["registered_source_count"],
        "meterless_enabled": view["meterless_enabled"],
        "nightshift_configured": view["nightshift_configured"],
        "nightshift_model": view["nightshift_model"],
        "intended_model_label": view["intended_model_label"],
        "nvidia_label_is_not_proof": view["nvidia_label_is_not_proof"],
        "hmem_memory_count": len(memory.memories),
        "warnings": view["warnings"],
        "ui_origin": view.get("zetaris_base_url"),
        # booleans only — never API keys
        "zetaris_api_key_set": view["zetaris_api_key_set"],
        "nightshift_api_key_set": view["nightshift_api_key_set"],
    }


def check_connections() -> dict[str, Any]:
    settings = load_settings()
    scout = ScoutIntent(settings.scout_signing_key)
    zetaris = ZetarisClient(settings).probe()
    nightshift = NightshiftClient(settings).probe()
    stage1 = scout.stage1_self_test()
    memory = _memory()
    return {
        "Zetaris": {"state": zetaris.status, "detail": zetaris.detail},
        "Meterless Nightshift": {"state": nightshift.state, "detail": nightshift.detail},
        "H-MEM": {
            "state": "local_store",
            "detail": (
                f"{len(memory.memories)} stored memories. "
                "Retrieval uses the documented hybrid formula. "
                "The conformance suite has not been run."
            ),
        },
        "Scout Intent": {
            "state": "local_ready" if stage1["within_16ms"] else "local_slow",
            "detail": (
                "Stage-1 self-test %sms. Upstream eval harness has not been run."
                % stage1["latency_ms"]
            ),
        },
    }


def zetaris_select_1() -> dict[str, Any]:
    result = ZetarisClient(load_settings()).probe()
    return _query_payload(result)


def zetaris_taxi_sample() -> dict[str, Any]:
    result = ZetarisClient(load_settings()).query_taxi_trips_sample()
    return _query_payload(result)


def run_investigation(question: str) -> dict[str, Any]:
    settings = load_settings()
    brief = investigate(question, settings, hmem=_memory())
    return brief.as_dict()


def memory_recent(limit: int = 8) -> dict[str, Any]:
    memory = _memory()
    return {
        "memories": memory.recent(limit),
        "audit": memory.audit(limit),
        "count": len(memory.memories),
    }


def save_cockpit_answer(question: str, answer: str, record_ids: list[str]) -> dict[str, Any]:
    recorded = record_cockpit_answer(
        _memory(),
        question=question,
        answer=answer,
        record_ids=record_ids,
    )
    return {"recorded": recorded}


def _query_payload(result) -> dict[str, Any]:
    return {
        "status": result.status,
        "detail": result.detail,
        "rows": result.rows,
        "duration_ms": result.duration_ms,
        "statement": result.statement,
        "http_status": result.http_status,
        "ok": result.ok,
    }
