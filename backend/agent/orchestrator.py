"""Investigation workflow.

Order: Scout Intent signs a contract, Zetaris retrieves records named by that
contract, and Meterless Nightshift may reason only over those records.
"""

from __future__ import annotations

from agent.config import Settings, load_settings
from agent.models import Finding, InvestigationBrief, LayerStatus, SupportingRecord
from integrations.hmem import Hmem
from integrations.meterless_engine import ScoutIntent
from integrations.meterless_nightshift import NightshiftClient
from integrations.nightshift_web import prepare_task
from integrations.zetaris import QueryResult, ZetarisClient


def investigate(
    question: str,
    settings: Settings | None = None,
    *,
    scout: ScoutIntent | None = None,
    zetaris: ZetarisClient | None = None,
    nightshift: NightshiftClient | None = None,
    hmem: Hmem | None = None,
) -> InvestigationBrief:
    settings = settings or load_settings()
    scout = scout or ScoutIntent(settings.scout_signing_key)
    zetaris = zetaris or ZetarisClient(settings)
    nightshift = nightshift or NightshiftClient(settings)
    text = (question or "").strip()
    if not text:
        return _empty("Enter an investigation question.")
    recalled = hmem.query(text) if hmem else {"memories": [], "context": "", "trace": {}}

    availability = {
        "zetaris": settings.zetaris_configured,
        "sources": settings.zetaris_configured and bool(settings.zetaris_sources),
        "nightshift": settings.nightshift_configured,
    }
    decision = scout.decide(text, availability=availability)
    if decision.blocked or not decision.contract:
        return InvestigationBrief(
            question=text,
            uncertainty=["The request was blocked before any data source was queried."],
            evidence_gaps=[decision.reason],
            next_steps=["Submit a planning question without instructions aimed at the agent."],
            layer_status=[
                LayerStatus("Scout Intent", "blocked", decision.reason),
                LayerStatus("Zetaris", "not_called", "No contract was issued."),
                LayerStatus("Meterless Nightshift", "not_called", "No contract was issued."),
            ],
            contract=decision.as_public_dict().get("contract"),
        )

    problem = scout.verify(decision.contract)
    if problem:
        return InvestigationBrief(
            question=text,
            uncertainty=["The execution contract was refused before any query."],
            evidence_gaps=[f"Scout Intent contract check failed: {problem}."],
            next_steps=["Re-run the investigation so Scout can issue a fresh contract."],
            layer_status=[
                LayerStatus("Scout Intent", "refused", problem),
                LayerStatus("Zetaris", "not_called", "The contract was refused."),
                LayerStatus("Meterless Nightshift", "not_called", "The contract was refused."),
            ],
        )

    public_contract = decision.as_public_dict()["contract"]
    if decision.clarification:
        return InvestigationBrief(
            question=text,
            uncertainty=[decision.clarification["question"]],
            evidence_gaps=["No query ran because Scout Intent asked for clarification."],
            next_steps=[
                "Name the planning topic, such as housing, zoning, permits, or parcels.",
                "Or ask which data sources are registered.",
            ],
            layer_status=[
                LayerStatus("Scout Intent", "clarification", decision.reason),
                LayerStatus("Zetaris", "not_called", "Waiting for a confident contract."),
                LayerStatus(
                    "Meterless Nightshift",
                    "not_called",
                    "Waiting for retrieved records.",
                ),
            ],
            contract=public_contract,
            clarification=decision.clarification,
        )

    tools = set(public_contract["tool_plan"])
    records: list[SupportingRecord] = []
    uncertainty = [
        "Stage-2 semantic scoring was skipped. The band uses Stage-1 trigger confidence.",
        "Finding text from Nightshift is accepted only when it cites retrieved record ids. It is not independently fact-checked.",
    ]
    gaps: list[str] = []
    steps: list[str] = []
    statuses = [
        LayerStatus(
            "Scout Intent",
            "contract_issued",
            f"{public_contract['intent']} at confidence {public_contract['confidence']}.",
        )
    ]

    if "zetaris.list_sources" in tools:
        catalog = zetaris.list_catalog()
        statuses.append(_zetaris_status(catalog, "Catalog"))
        records.extend(_records(catalog.rows, "catalog", len(records)))
        _note_query(catalog, gaps, steps, label="Zetaris catalog")
        if catalog.excluded_rows:
            names = _sample_names(catalog.excluded_rows)
            gaps.append(
                "Zetaris returned supplied sample data (%s). Those rows were not used as planning evidence."
                % ", ".join(names)
            )
    elif "zetaris.select_registered" not in tools and not public_contract["routing_failures"]:
        statuses.append(
            LayerStatus("Zetaris", "not_called", "The contract did not include a Zetaris tool.")
        )

    if "zetaris.select_registered" in tools:
        selections = zetaris.select_registered()
        if not any(item.ok for item in selections):
            first = selections[0]
            statuses.append(_zetaris_status(first, "Records"))
        else:
            total = sum(len(item.rows) for item in selections if item.ok)
            statuses.append(
                LayerStatus("Zetaris", "ok", f"Retrieved {total} row(s) from registered sources.")
            )
        for result in selections:
            records.extend(_records(result.rows, result.statement or "records", len(records)))
            _note_query(result, gaps, steps, label=result.statement or "registered source")
    elif public_contract["routing_failures"]:
        gaps.append(
            "Scout Intent could not route a required tool: "
            + "; ".join(public_contract["routing_failures"])
        )
        if not settings.zetaris_configured:
            steps.append(
                "Set ZETARIS_BASE_URL to the web UI origin with no path, and set ZETARIS_ORG_ID and ZETARIS_API_KEY in .env."
            )
        elif not settings.zetaris_sources:
            steps.append(
                "Register planning sources in ZETARIS_SOURCES. Do not register NY_TAXI, TPCDS, or TPCH."
            )
        if not any(status.name == "Zetaris" for status in statuses):
            statuses.append(
                LayerStatus("Zetaris", "not_routed", public_contract["routing_failures"][0])
            )

    if not records:
        gaps.append("No planning records were retrieved.")
        uncertainty.append("There is no retrieved evidence for this question.")

    reasoning_records = [record.as_dict() for record in records]
    nightshift_meta: dict | None = None
    if "nightshift.reason_over_records" in tools and reasoning_records:
        reasoning = nightshift.reason(
            text,
            reasoning_records,
            memory_context=recalled.get("context", ""),
        )
        findings = [
            Finding(
                statement=item["statement"],
                record_ids=list(item["record_ids"]),
                source=item.get("source") or "nightshift_ai_interpretation",
            )
            for item in reasoning.findings
        ]
        nightshift_meta = {
            "configured_model": reasoning.configured_model,
            "response_model": reasoning.response_model,
            "state": reasoning.state,
            "http_status": reasoning.http_status,
            "provider_meta": reasoning.provider_meta,
            "intended_label": "GPT-OSS 20B (NVIDIA cloud)",
            "nvidia_label_is_not_proof": True,
        }
        statuses.append(LayerStatus("Meterless Nightshift", reasoning.state, reasoning.detail))
        if reasoning.state == "ok" and not findings:
            gaps.append("Nightshift returned no findings that cite the retrieved records.")
        elif reasoning.state != "ok":
            gaps.append(reasoning.detail)
            if reasoning.response_text:
                uncertainty.append(
                    "Nightshift returned text that was not accepted as cited findings. "
                    "It is an AI interpretation only."
                )
            steps.append(
                "Check METERLESS_BASE_URL, METERLESS_API_KEY, METERLESS_MODEL, and that the "
                "Nightshift hotspot (full Windows / Mac M5+ / DGX) is running. "
                "Meterless Web has no app endpoint."
            )
    else:
        findings = []
        if not settings.nightshift_configured:
            statuses.append(
                LayerStatus(
                    "Meterless Nightshift",
                    "browser_handoff" if not settings.meterless_enabled else "not_configured",
                    (
                        "METERLESS_ENABLED is false or credentials are incomplete. "
                        "A Meterless Web cockpit task is prepared when the HTTP path is off. "
                        "A pasted answer is an AI interpretation, not a retrieved fact."
                    ),
                )
            )
            steps.extend(
                [
                    "To use GPT-OSS 20B over the documented Nightshift HTTP API, set "
                    "METERLESS_ENABLED=true and fill METERLESS_BASE_URL, METERLESS_API_KEY, "
                    "and the exact METERLESS_MODEL id from your Meterless Providers card.",
                    "Or open https://meterless.ai/Nightshift/WEB, queue the prepared task, "
                    "and paste the Morning answer back.",
                ]
            )
        elif not reasoning_records:
            statuses.append(
                LayerStatus(
                    "Meterless Nightshift",
                    "skipped",
                    "Reasoning was skipped because no records were retrieved.",
                )
            )
        else:
            statuses.append(
                LayerStatus(
                    "Meterless Nightshift",
                    "not_called",
                    "The execution contract did not include reasoning.",
                )
            )

    if settings.warnings:
        uncertainty.extend(settings.warnings)
    if not records and not settings.zetaris_sources:
        steps.append(
            "Register a real planning source in ZETARIS_SOURCES as qualified_name|what one row represents. "
            "Do not register NY_TAXI, TPCDS, or TPCH."
        )
    if hmem:
        _remember_investigation(hmem, text, records)
        count = len(recalled.get("memories") or [])
        noun = "memory" if count == 1 else "memories"
        statuses.append(
            LayerStatus(
                "H-MEM",
                "recalled",
                f"{count} prior {noun} above the 0.35 threshold. "
                "The upstream conformance suite has not been run.",
            )
        )
    handoff = None
    if not settings.nightshift_configured:
        handoff = prepare_task(text, [record.as_dict() for record in records], recalled.get("context", ""))
    if not steps:
        steps.append("Compare the cited records with the source system before acting on a finding.")

    return InvestigationBrief(
        question=text,
        findings=findings,
        supporting_records=records,
        uncertainty=_unique(uncertainty),
        evidence_gaps=_unique(gaps),
        next_steps=_unique(steps),
        layer_status=statuses,
        contract=public_contract,
        prior_memories=list(recalled.get("memories") or []),
        nightshift_handoff=handoff,
        nightshift_meta=nightshift_meta,
    )


def _remember_investigation(hmem: Hmem, question: str, records: list[SupportingRecord]) -> None:
    hmem.remember(
        content=question,
        source="user",
        origin="chat_message",
        memory_type="general",
        layer="short_term",
        tags=["project:planning"],
        label="Investigation question",
    )
    for record in records:
        visible = " ".join(f"{key} {value}" for key, value in list(record.fields.items())[:8])
        hmem.remember(
            content=f"{record.source} {record.record_id} {visible}".strip(),
            source=f"zetaris:{record.record_id}",
            origin="document",
            memory_type="factual",
            layer="working",
            refs=[record.record_id],
            tags=["project:planning", "evidence"],
            label="Zetaris retrieved row",
            confidence=0.9,
        )


def _empty(message: str) -> InvestigationBrief:
    return InvestigationBrief(
        question="",
        uncertainty=[message],
        evidence_gaps=["No question was submitted."],
        next_steps=["Enter an urban-planning question and run the investigation."],
        layer_status=[
            LayerStatus("Scout Intent", "idle", "Waiting for a question."),
            LayerStatus("Zetaris", "idle", "Waiting for a question."),
            LayerStatus("Meterless Nightshift", "idle", "Waiting for a question."),
        ],
    )


def _records(rows: list[dict[str, str]], kind: str, start: int) -> list[SupportingRecord]:
    records = []
    for offset, row in enumerate(rows):
        source = row.get("_source") or row.get("_statement") or kind
        fields = {key: value for key, value in row.items() if not key.startswith("_")}
        records.append(
            SupportingRecord(
                record_id=f"record-{start + offset + 1}",
                source=str(source),
                kind="catalog" if "SHOW" in str(row.get("_statement", "")) else "table_row",
                fields=fields,
                statement=str(row.get("_statement") or ""),
            )
        )
    return records


def _note_query(result: QueryResult, gaps: list[str], steps: list[str], *, label: str) -> None:
    if result.ok:
        if not result.rows and not result.excluded_rows:
            gaps.append(f"{label} returned no rows.")
        return
    gaps.append(f"{label}: {result.detail}")
    if result.status == "not_configured":
        steps.append(
            "Set ZETARIS_BASE_URL to the web UI origin with no path, and set ZETARIS_ORG_ID and ZETARIS_API_KEY in .env."
        )
    elif result.status == "no_sources":
        steps.append(
            "Register planning sources in ZETARIS_SOURCES using qualified names from your Zetaris catalog."
        )
    elif result.status in {"unreachable", "unauthorized", "error", "unrecognized"}:
        steps.append("Check the Zetaris UI origin, organisation id, and credential, then run again.")


def _zetaris_status(result: QueryResult, label: str) -> LayerStatus:
    return LayerStatus("Zetaris", result.status, f"{label}: {result.detail}")


def _sample_names(rows: list[dict[str, str]]) -> list[str]:
    names = []
    for row in rows:
        for key in ("database", "name", "namespace", "datasource", "table", "tableName"):
            if row.get(key):
                names.append(row[key])
                break
        else:
            values = [value for key, value in row.items() if not key.startswith("_") and value]
            if values:
                names.append(values[0])
    return list(dict.fromkeys(names))


def _unique(items: list[str]) -> list[str]:
    seen = set()
    ordered = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            ordered.append(item)
    return ordered
