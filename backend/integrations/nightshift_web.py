"""Meterless Web cockpit handoff.

The Help documentation says the Web edition has no daemon and no endpoint for
other apps. Port 8088 is not present. This module prepares a Queue task and
records an answer the user pastes back from the cockpit. It does not call
Nightshift over HTTP.
"""

from __future__ import annotations

import json
from typing import Any

from integrations.hmem import Hmem

WEB_COCKPIT_URL = "https://meterless.ai/Nightshift/WEB"

COCKPIT_STEPS = (
    "Open https://meterless.ai/Nightshift/WEB in desktop Chrome or Edge. No account is required.",
    "Pass the Turnstile check, then open the cockpit.",
    "Open Night, then Queue. Leave Auto on.",
    "Paste the prepared task. Press Begin right now.",
    "When the job finishes, open Morning and choose Read the answer.",
    "Paste that answer below. This desk stores it as an AI interpretation, not as a retrieved fact.",
)


def prepare_task(question: str, records: list[dict[str, Any]], memory_context: str) -> dict[str, Any]:
    evidence = records or []
    evidence_block = (
        json.dumps(evidence, ensure_ascii=False)
        if evidence
        else "None. No planning records were retrieved. Do not invent any."
    )
    prompt = "\n".join(
        [
            "Urban-planning investigation. Use only the retrieved records in this task.",
            "Do not invent statistics, community reports, place facts, or query results.",
            "New York taxi sample rows are not evidence about Nairobi or Kilimani.",
            "If the records do not support a conclusion, say that the evidence is missing.",
            "Label every conclusion as an interpretation.",
            "Cite record_id values only when they appear in the retrieved records.",
            "",
            "Question:",
            question.strip(),
            "",
            "Retrieved records:",
            evidence_block,
            "",
            "Prior investigation memory:",
            memory_context or "None.",
        ]
    )
    return {
        "method": "meterless_web_cockpit",
        "automated": False,
        "api_call": False,
        "url": WEB_COCKPIT_URL,
        "organizer_confirmation_required": True,
        "edition_note": (
            "Meterless Help says the Web edition has no hotspot and no endpoint for other apps. "
            "The footer may print RUNTIME :8088, but there is no runtime port. "
            "This task is for the browser cockpit. It is not an API request."
        ),
        "steps": list(COCKPIT_STEPS),
        "prompt": prompt,
    }


def record_cockpit_answer(
    hmem: Hmem,
    *,
    question: str,
    answer: str,
    record_ids: list[str],
) -> dict[str, Any]:
    text = (answer or "").strip()
    if not text:
        raise ValueError("Paste the Nightshift answer before recording it.")
    return hmem.remember(
        content=text,
        source="meterless-web-cockpit",
        origin="model_response",
        memory_type="general",
        layer="working",
        refs=record_ids,
        confidence=0.55,
        tags=["project:planning", "ai-interpretation"],
        label="Pasted from the Meterless Web cockpit for: " + question.strip()[:180],
    )
