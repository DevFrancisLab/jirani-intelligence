"""Legacy Streamlit prototype.

The primary UI is the React app in frontend/. Keep this file only for
compatibility checks. Run from backend/: streamlit run legacy/streamlit_app.py
"""

from __future__ import annotations

import html

import streamlit as st

from agent.config import ROOT, load_settings
from agent.models import InvestigationBrief
from agent.orchestrator import investigate
from integrations.hmem import Hmem
from integrations.meterless_engine import ScoutIntent
from integrations.meterless_nightshift import NightshiftClient
from integrations.nightshift_web import record_cockpit_answer
from integrations.zetaris import ZetarisClient

STYLES = """
<style>
    .block-container { max-width: 1080px; padding-top: 1.6rem; }
    .eyebrow {
        letter-spacing: 0.08em;
        text-transform: uppercase;
        font-size: 0.78rem;
        color: #9a3412;
        margin-bottom: 0.2rem;
    }
    .lede { color: #44403c; font-size: 1.05rem; }
    .pill {
        display: inline-block;
        border: 1px solid #e7e5e4;
        border-radius: 999px;
        padding: 0.15rem 0.6rem;
        margin: 0 0.35rem 0.35rem 0;
        background: #fff;
        font-size: 0.85rem;
    }
    .section-label {
        font-size: 0.78rem;
        letter-spacing: 0.06em;
        text-transform: uppercase;
        color: #78716c;
        margin-top: 1.2rem;
    }
    div[data-testid="stSidebar"] { background: #f7f4ee; }
</style>
"""


def main() -> None:
    st.set_page_config(
        page_title="Jirani Intelligence",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    st.markdown(STYLES, unsafe_allow_html=True)
    settings = load_settings()
    _sidebar(settings)
    st.markdown(
        '<p class="eyebrow">Open Agent Hackathon 2026 · Track 01 · Solving Fragmented Intelligence</p>',
        unsafe_allow_html=True,
    )
    st.title("Jirani Intelligence")
    st.markdown(
        '<p class="lede">Ask one urban-planning question. Scout Intent decides which '
        "registered sources are in scope, Zetaris retrieves those records, H-MEM recalls "
        "prior notes, and Meterless Web receives a cockpit task. The Web edition has no "
        "app endpoint, so the answer comes back only when you paste it.</p>",
        unsafe_allow_html=True,
    )
    if settings.warnings:
        for warning in settings.warnings:
            st.warning(warning)

    _zetaris_panel(settings)
    _hmem_panel()

    if settings.zetaris_sources:
        st.caption("Registered planning sources: " + ", ".join(source.name for source in settings.zetaris_sources))
    else:
        st.info(
            "Zetaris can run, and no planning sources are registered. "
            "Add ZETARIS_SOURCES as qualified_name|what one row represents. "
            "Do not register NY_TAXI, TPCDS, or TPCH. Those samples are not evidence about a place."
        )

    with st.form("investigation"):
        question = st.text_area(
            "Investigation question",
            height=120,
            placeholder="Which registered records mention housing permits?",
        )
        submitted = st.form_submit_button("Run investigation", type="primary")

    if st.button("Check connections"):
        with st.spinner("Checking Zetaris and Nightshift…"):
            st.session_state["connections"] = _check(settings)
    if "connections" in st.session_state:
        _render_connections(st.session_state["connections"])

    if submitted:
        with st.spinner("Running the investigation…"):
            st.session_state["brief"] = investigate(question, settings, hmem=_memory())

    brief = st.session_state.get("brief")
    if isinstance(brief, InvestigationBrief):
        _render_brief(brief)
        _render_handoff(brief)
    else:
        st.info(
            "Nothing on this page is planning evidence until a query returns rows. "
            "A connection check that fails stays failed."
        )


def _sidebar(settings) -> None:
    view = settings.public_view()
    with st.sidebar:
        st.header("How a question moves")
        st.markdown(
            "1. **Scout Intent** signs an execution contract.\n"
            "2. **Zetaris** retrieves records from registered sources.\n"
            "3. **H-MEM** recalls prior notes with provenance.\n"
            "4. **Meterless Web** receives a prepared cockpit task. "
            "The Web edition has no app endpoint."
        )
        st.header("Configuration")
        memory_count = len(_memory().memories)
        st.write(
            {
                "Zetaris configured": view["zetaris_configured"],
                "Registered sources": view["registered_source_count"],
                "Meterless enabled": view["meterless_enabled"],
                "Nightshift HTTP ready": view["nightshift_configured"],
                "Configured model": view["nightshift_model"] or "not set",
                "Intended label": view["intended_model_label"],
                "NVIDIA label is proof": False,
                "H-MEM memories": memory_count,
                "Scout signing key set": view["scout_signing_key_set"],
            }
        )
        if view["registered_sources"]:
            st.caption("Registered sources")
            for name in view["registered_sources"]:
                st.code(name, language=None)
        st.caption(
            "Credentials stay in the server-side .env file. This sidebar does not show them. "
            "A cockpit paste is an AI interpretation, not a retrieved fact."
        )


def _zetaris_panel(settings) -> None:
    view = settings.public_view()
    st.markdown('<p class="section-label">Zetaris</p>', unsafe_allow_html=True)
    st.caption(
        "Queries go through the UI proxy at /api/proxy/sql-editor/sqls/run-query "
        "on the web UI origin. The login page is not that origin, and the organisation slug is not an endpoint."
    )
    st.caption(
        "NY_TAXI.taxi_trips is New York sample data. It is not evidence about Nairobi or Kilimani."
    )
    st.write(
        {
            "Configured": view["zetaris_configured"],
            "UI origin": view["zetaris_base_url"] or "not set",
            "Organisation id set": view["zetaris_org_id_set"],
            "API key set": view["zetaris_api_key_set"],
        }
    )
    left, right = st.columns(2)
    if left.button("Run SELECT 1"):
        with st.spinner("Running SELECT 1…"):
            st.session_state["zetaris_probe"] = ZetarisClient(settings).probe()
    if right.button("Read NY_TAXI.taxi_trips sample"):
        with st.spinner("Reading the supplied sample…"):
            st.session_state["zetaris_sample"] = ZetarisClient(settings).query_taxi_trips_sample()
    if "zetaris_probe" in st.session_state:
        _render_query("SELECT 1", st.session_state["zetaris_probe"])
    if "zetaris_sample" in st.session_state:
        st.caption(
            "These rows are New York sample data from NY_TAXI.taxi_trips. "
            "They are not evidence about Nairobi or Kilimani."
        )
        _render_query("NY_TAXI.taxi_trips", st.session_state["zetaris_sample"])


def _render_query(title: str, result) -> None:
    duration = "n/a" if result.duration_ms is None else f"{result.duration_ms} ms"
    st.markdown(
        f'<span class="pill"><strong>{html.escape(title)}</strong> · {html.escape(result.status)}'
        f" · {html.escape(duration)}</span>",
        unsafe_allow_html=True,
    )
    st.caption(result.detail)
    if result.rows:
        st.dataframe(result.rows, use_container_width=True, hide_index=True)


def _memory() -> Hmem:
    return Hmem(ROOT / "data" / "hmem.json")


def _hmem_panel() -> None:
    memory = _memory()
    st.markdown('<p class="section-label">H-MEM</p>', unsafe_allow_html=True)
    st.caption(
        "Local investigation memory. Retrieved evidence, AI interpretations, and notes "
        "keep separate standing labels. The embedding is the reference token hash, not a "
        "downloaded model. The upstream conformance suite has not been run."
    )
    recent = memory.recent(5)
    if not recent:
        st.write("No memories yet. Run an investigation to record a question and any retrieved rows.")
        return
    for item in recent:
        st.write(item["content"][:280])
        st.caption(
            f"{item['standing']} · {item['provenance'].get('origin')} · source {item['source']}"
        )


def _check(settings) -> dict:
    scout = ScoutIntent(settings.scout_signing_key)
    zetaris = ZetarisClient(settings).probe()
    nightshift = NightshiftClient(settings).probe()
    stage1 = scout.stage1_self_test()
    memory = _memory()
    count = len(memory.memories)
    noun = "memory" if count == 1 else "memories"
    return {
        "Zetaris": (zetaris.status, zetaris.detail),
        "Meterless Nightshift": (nightshift.state, nightshift.detail),
        "H-MEM": (
            "local_store",
            f"{count} stored {noun}. Retrieval uses the documented hybrid formula. "
            "The conformance suite has not been run.",
        ),
        "Scout Intent": (
            "local_ready" if stage1["within_16ms"] else "local_slow",
            "Stage-1 self-test %sms. Upstream eval harness has not been run."
            % stage1["latency_ms"],
        ),
    }


def _render_connections(results: dict) -> None:
    st.markdown('<p class="section-label">Connection check</p>', unsafe_allow_html=True)
    for name, (state, detail) in results.items():
        st.markdown(
            f'<span class="pill"><strong>{html.escape(name)}</strong> · {html.escape(state)}</span>',
            unsafe_allow_html=True,
        )
        st.caption(detail)


def _render_brief(brief: InvestigationBrief) -> None:
    st.markdown('<p class="section-label">Layer status</p>', unsafe_allow_html=True)
    for layer in brief.layer_status:
        st.markdown(
            f'<span class="pill"><strong>{html.escape(layer.name)}</strong> · {html.escape(layer.state)}</span>',
            unsafe_allow_html=True,
        )
        st.caption(layer.detail)

    if brief.clarification:
        st.info(brief.clarification["question"])

    st.markdown('<p class="section-label">Findings</p>', unsafe_allow_html=True)
    if not brief.findings:
        st.write("No findings. The desk does not fill this section when no cited reasoning was accepted.")
    for finding in brief.findings:
        st.write(finding.statement)
        st.caption("Cites " + ", ".join(finding.record_ids) + " · " + finding.source)

    st.markdown('<p class="section-label">Supporting records</p>', unsafe_allow_html=True)
    if not brief.supporting_records:
        st.write("No records were retrieved.")
    else:
        st.dataframe(
            [
                {
                    "record_id": record.record_id,
                    "source": record.source,
                    "kind": record.kind,
                    **record.fields,
                }
                for record in brief.supporting_records
            ],
            use_container_width=True,
            hide_index=True,
        )

    _bullets("Uncertainty", brief.uncertainty)
    _bullets("Evidence gaps", brief.evidence_gaps)
    _bullets("Recommended next steps", brief.next_steps)
    st.markdown('<p class="section-label">Prior H-MEM context</p>', unsafe_allow_html=True)
    if not brief.prior_memories:
        st.write("No prior memory scored at or above 0.35 for this question.")
    for memory in brief.prior_memories:
        st.write(memory["content"])
        st.caption(
            f"{memory['standing']} · {memory['provenance']['origin']} · source {memory['source']} · score {memory.get('score')}"
        )

    if brief.nightshift_meta:
        st.markdown('<p class="section-label">Nightshift provider metadata</p>', unsafe_allow_html=True)
        st.caption(
            "Configured model id and any response model field. "
            "A label that contains NVIDIA is not proof of NVIDIA routing."
        )
        st.json(
            {
                key: value
                for key, value in brief.nightshift_meta.items()
                if key != "provider_meta" or isinstance(value, dict)
            }
        )

    if brief.contract:
        with st.expander("Execution contract"):
            st.json(brief.contract)


def _render_handoff(brief: InvestigationBrief) -> None:
    handoff = brief.nightshift_handoff
    if not handoff:
        return
    st.markdown('<p class="section-label">Meterless Web cockpit</p>', unsafe_allow_html=True)
    st.warning(handoff["edition_note"] + " Organizers must confirm this satisfies the Nightshift requirement.")
    st.caption(handoff["url"])
    for step in handoff["steps"]:
        st.write("• " + step)
    st.code(handoff["prompt"], language=None)
    answer = st.text_area("Paste the Morning answer", height=140, key="cockpit_answer")
    if st.button("Record cockpit answer"):
        try:
            recorded = record_cockpit_answer(
                _memory(),
                question=brief.question,
                answer=answer,
                record_ids=[record.record_id for record in brief.supporting_records],
            )
        except ValueError as error:
            st.error(str(error))
        else:
            st.success("Recorded as an AI interpretation. It is not a retrieved fact and it is not a finding.")
            st.write(recorded["content"])
            st.caption(recorded["standing"] + " · " + recorded["source"])


def _bullets(title: str, items: list[str]) -> None:
    st.markdown(f'<p class="section-label">{html.escape(title)}</p>', unsafe_allow_html=True)
    if not items:
        st.write("None.")
        return
    for item in items:
        st.write("• " + item)


if __name__ == "__main__":
    main()
