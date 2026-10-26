"""Meterless Nightshift adapter.

Nightshift is the AI provider. It is an OpenAI-compatible local API. This adapter
sends only the question and records the caller already retrieved. It does not
turn a failed or unstructured response into findings.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from agent.config import Settings
from integrations.http import scrub, urllib_transport

SYSTEM_PROMPT = (
    "You are the reasoning step for an urban-planning investigation. "
    "Use only the records in the user message. "
    "Do not invent statistics, community reports, place facts, or query results. "
    "If the records do not support a conclusion, return an empty findings array. "
    "Every finding must cite one or more record_ids from the payload. "
    'Reply with JSON only: {"findings":[{"statement":"...","record_ids":["id"]}]}'
)


@dataclass
class ProviderStatus:
    state: str
    detail: str
    model_ids: list[str] = field(default_factory=list)

    @property
    def online(self) -> bool:
        return self.state == "online"


@dataclass
class ReasoningResult:
    state: str
    detail: str
    findings: list[dict[str, Any]] = field(default_factory=list)
    discarded: int = 0


class NightshiftClient:
    def __init__(self, settings: Settings, transport=urllib_transport) -> None:
        self.settings = settings
        self.transport = transport

    def probe(self) -> ProviderStatus:
        if not self.settings.meterless_runtime_token:
            return ProviderStatus("not_configured", "Set METERLESS_RUNTIME_TOKEN.")
        if not self.settings.meterless_base_url:
            return ProviderStatus("not_configured", "Set METERLESS_BASE_URL.")
        response = self.transport(
            "GET",
            self.settings.meterless_base_url + "/models",
            self._headers(),
            None,
            min(5.0, self.settings.meterless_timeout_seconds),
        )
        if response.status == 0:
            return ProviderStatus("offline", response.error or "Nightshift unreachable")
        if response.status in (401, 403):
            return ProviderStatus(
                "unauthorized",
                "Nightshift rejected the runtime token (HTTP %s)." % response.status,
            )
        if response.status != 200 or not isinstance(response.body, dict):
            return ProviderStatus(
                "offline",
                "GET /v1/models returned HTTP %s." % response.status,
            )
        ids = _model_ids(response.body)
        meterless_ids = [model_id for model_id in ids if model_id.startswith("meterless/")]
        if not meterless_ids:
            return ProviderStatus(
                "offline",
                "Nightshift answered, but no meterless/* routing modes were listed.",
                model_ids=ids,
            )
        return ProviderStatus(
            "online",
            "Nightshift listed %s." % ", ".join(meterless_ids),
            model_ids=meterless_ids,
        )

    def reason(self, question: str, records: list[dict[str, Any]]) -> ReasoningResult:
        if not records:
            return ReasoningResult(
                "skipped",
                "Nightshift was not called because there are no retrieved records.",
            )
        if not self.settings.nightshift_configured:
            return ReasoningResult(
                "not_configured",
                "Meterless Nightshift is not configured, so no reasoning was run.",
            )
        payload = {
            "question": question,
            "records": records,
            "instruction": "Cite only record_ids included above.",
        }
        response = self.transport(
            "POST",
            self.settings.meterless_base_url + "/chat/completions",
            {**self._headers(), "Content-Type": "application/json"},
            {
                "model": self.settings.meterless_model,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
                ],
            },
            self.settings.meterless_timeout_seconds,
        )
        if response.status == 0:
            return ReasoningResult("offline", response.error or "Nightshift unreachable")
        if response.status in (401, 403):
            return ReasoningResult(
                "unauthorized",
                "Nightshift rejected the reasoning request (HTTP %s)." % response.status,
            )
        if response.status != 200:
            return ReasoningResult(
                "error",
                "Nightshift reasoning failed: HTTP %s %s"
                % (response.status, scrub(response.raw_text)),
            )
        content = _message_text(response.body)
        if content is None:
            return ReasoningResult(
                "unrecognized",
                "Nightshift returned a completion this adapter does not parse.",
            )
        return _accept_findings(content, {record["record_id"] for record in records})

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.settings.meterless_runtime_token}",
            "meterless-app": self.settings.meterless_app_id,
            "meterless-scope": "user",
        }


def _model_ids(body: dict[str, Any]) -> list[str]:
    data = body.get("data")
    if not isinstance(data, list):
        return []
    ids = []
    for item in data:
        if isinstance(item, dict) and isinstance(item.get("id"), str):
            ids.append(item["id"])
    return ids


def _message_text(body: Any) -> str | None:
    if not isinstance(body, dict):
        return None
    choices = body.get("choices")
    if not isinstance(choices, list) or not choices:
        return None
    message = choices[0].get("message") if isinstance(choices[0], dict) else None
    if not isinstance(message, dict):
        return None
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, dict) and isinstance(part.get("text"), str):
                parts.append(part["text"])
            elif isinstance(part, str):
                parts.append(part)
        return "\n".join(parts) if parts else None
    return None


def _accept_findings(content: str, allowed_ids: set[str]) -> ReasoningResult:
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        return ReasoningResult(
            "discarded",
            "Nightshift did not return JSON. The text was not accepted as findings.",
        )
    if not isinstance(parsed, dict) or not isinstance(parsed.get("findings"), list):
        return ReasoningResult(
            "discarded",
            "Nightshift JSON had no findings array. Nothing was accepted.",
        )
    accepted = []
    discarded = 0
    for item in parsed["findings"]:
        if not isinstance(item, dict):
            discarded += 1
            continue
        statement = item.get("statement")
        record_ids = item.get("record_ids")
        if not isinstance(statement, str) or not statement.strip():
            discarded += 1
            continue
        if not isinstance(record_ids, list) or not record_ids:
            discarded += 1
            continue
        if not all(isinstance(record_id, str) and record_id in allowed_ids for record_id in record_ids):
            discarded += 1
            continue
        accepted.append(
            {"statement": statement.strip(), "record_ids": list(record_ids), "source": "nightshift"}
        )
    detail = "Accepted %s cited finding(s)." % len(accepted)
    if discarded:
        detail += " Discarded %s finding(s) that did not cite retrieved records." % discarded
    return ReasoningResult("ok", detail, findings=accepted, discarded=discarded)
