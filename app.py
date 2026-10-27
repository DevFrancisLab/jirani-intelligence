"""Jirani Intelligence investigation dashboard."""

from __future__ import annotations

import html

import streamlit as st

from agent.config import load_settings
from agent.models import InvestigationBrief
from agent.orchestrator import investigate
from integrations.meterless_engine import ScoutIntent
from integrations.meterless_nightshift import NightshiftClient
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
        "registered sources are in scope, Zetaris retrieves those records, and "
        "Meterless Nightshift reasons only over what came back.</p>",
        unsafe_allow_html=True,
    )
    if settings.warnings:
        for warning in settings.warnings:
            st.warning(warning)

    _zetaris_panel(settings)

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
            st.session_state["brief"] = investigate(question, settings)

    brief = st.session_state.get("brief")
    if isinstance(brief, InvestigationBrief):
        _render_brief(brief)
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
            "2. **Zetaris** is the data access and query layer that retrieves "
            "records from registered data sources.\n"
            "3. **Meterless Nightshift** is the AI provider. It sees those records, not a hidden corpus."
        )
        st.header("Configuration")
        st.write(
            {
                "Zetaris configured": view["zetaris_configured"],
                "Registered sources": view["registered_source_count"],
                "Nightshift configured": view["nightshift_configured"],
                "Nightshift model": view["nightshift_model"],
                "Scout signing key set": view["scout_signing_key_set"],
            }
        )
        if view["registered_sources"]:
            st.caption("Registered sources")
            for name in view["registered_sources"]:
                st.code(name, language=None)
        st.caption(
            "Credentials stay in the server-side .env file. This sidebar does not show them. "
            "External integrations are not marked working until a live call succeeds."
        )


def _zetaris_panel(settings) -> None:
    view = settings.public_view()
    st.markdown('<p class="section-label">Zetaris direct REST</p>', unsafe_allow_html=True)
    st.caption(
        "The query client uses ZETARIS_REST_URL, the API base ending in /api/v1.0. "
        "The sign-in URL and organisation slug are not the API endpoint."
    )
    st.write(
        {
            "Configured": view["zetaris_configured"],
            "REST URL": view["zetaris_rest_url"] or "not set",
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
        st.caption("These rows are the supplied NY Taxi sample. They are not planning evidence.")
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


def _check(settings) -> dict:
    scout = ScoutIntent(settings.scout_signing_key)
    zetaris = ZetarisClient(settings).probe()
    nightshift = NightshiftClient(settings).probe()
    stage1 = scout.stage1_self_test()
    return {
        "Zetaris": (zetaris.status, zetaris.detail),
        "Meterless Nightshift": (nightshift.state, nightshift.detail),
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

    if brief.contract:
        with st.expander("Execution contract"):
            st.json(brief.contract)


def _bullets(title: str, items: list[str]) -> None:
    st.markdown(f'<p class="section-label">{html.escape(title)}</p>', unsafe_allow_html=True)
    if not items:
        st.write("None.")
        return
    for item in items:
        st.write("• " + item)


if __name__ == "__main__":
    main()
