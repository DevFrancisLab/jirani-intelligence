"""Meterless Nightshift OpenAI-compatible client.

Documented protocol (Help → Connect your apps), for editions that expose a
hotspot: POST {METERLESS_BASE_URL}/chat/completions with Bearer auth.

Meterless Web has no app endpoint. Leave METERLESS_ENABLED=false and use the
cockpit handoff in integrations/nightshift_web.py.

This client sends the exact METERLESS_MODEL string from configuration. It does
not substitute Llama, OpenAI, or another model when the requested id is absent.
A label that contains “NVIDIA” is not proof of NVIDIA routing; response metadata
is reported separately.
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
    "New York taxi sample rows are not evidence about Nairobi or Kilimani. "
    "If the records do not support a conclusion, return an empty findings array. "
    "Every finding must cite one or more record_ids from the payload. "
    'Reply with JSON only: {"findings":[{"statement":"...","record_ids":["id"]}]}'
)


@dataclass
class ProviderStatus:
    state: str
    detail: str
    model_ids: list[str] = field(default_factory=list)
    configured_model: str = ""
    enabled: bool = False

    @property
    def online(self) -> bool:
        return self.state == "online"


@dataclass
class ReasoningResult:
    state: str
    detail: str
    findings: list[dict[str, Any]] = field(default_factory=list)
    discarded: int = 0
    response_text: str = ""
    configured_model: str = ""
    response_model: str | None = None
    http_status: int | None = None
    provider_meta: dict[str, Any] = field(default_factory=dict)


class NightshiftClient:
    def __init__(self, settings: Settings, transport=urllib_transport) -> None:
        self.settings = settings
        self.transport = transport

    def probe(self) -> ProviderStatus:
        configured = self.settings.meterless_model
        if not self.settings.meterless_enabled:
            return ProviderStatus(
                "disabled",
                "METERLESS_ENABLED is false. Set it to true after you have a "
                "documented hotspot or inference base URL, API key, and exact model id. "
                "Meterless Web has no app endpoint.",
                configured_model=configured,
                enabled=False,
            )
        missing = self.settings.nightshift_missing
        if missing:
            return ProviderStatus(
                "not_configured",
                "Meterless Nightshift is enabled but incomplete. Set " + ", ".join(missing) + ".",
                configured_model=configured,
                enabled=True,
            )
        response = self.transport(
            "GET",
            self.settings.meterless_base_url + "/models",
            self._headers(),
            None,
            min(5.0, self.settings.meterless_timeout_seconds),
        )
        if response.status == 0:
            return ProviderStatus(
                "offline",
                response.error or "Nightshift unreachable",
                configured_model=configured,
                enabled=True,
            )
        if response.status in (401, 403):
            return ProviderStatus(
                "unauthorized",
                "Nightshift rejected the API key (HTTP %s)." % response.status,
                configured_model=configured,
                enabled=True,
            )
        if response.status == 429:
            return ProviderStatus(
                "rate_limited",
                "Nightshift rate-limited the models probe (HTTP 429).",
                configured_model=configured,
                enabled=True,
            )
        if response.status == 503:
            return ProviderStatus(
                "hotspot_offline",
                _hotspot_detail(response.body, response.raw_text),
                configured_model=configured,
                enabled=True,
            )
        if response.status != 200 or not isinstance(response.body, dict):
            return ProviderStatus(
                "offline",
                "GET /v1/models returned HTTP %s %s"
                % (response.status, scrub(response.raw_text)),
                configured_model=configured,
                enabled=True,
            )
        ids = _model_ids(response.body)
        if ids and configured not in ids:
            return ProviderStatus(
                "model_unavailable",
                (
                    "Configured model %r is not listed by the endpoint. "
                    "Available: %s. No substitute model was used."
                    % (configured, ", ".join(ids[:12]) or "(none)")
                ),
                model_ids=ids,
                configured_model=configured,
                enabled=True,
            )
        detail = "Endpoint reachable. Configured model %r." % configured
        if ids:
            detail += " Listed %s model id(s)." % len(ids)
        else:
            detail += " The models list was empty; the chat request will still send the configured id only."
        return ProviderStatus(
            "online",
            detail,
            model_ids=ids,
            configured_model=configured,
            enabled=True,
        )

    def reason(
        self,
        question: str,
        records: list[dict[str, Any]],
        *,
        memory_context: str = "",
    ) -> ReasoningResult:
        configured = self.settings.meterless_model
        if not records:
            return ReasoningResult(
                "skipped",
                "Nightshift was not called because there are no retrieved records.",
                configured_model=configured,
            )
        if not self.settings.nightshift_configured:
            missing = self.settings.nightshift_missing
            detail = "Meterless Nightshift is not configured, so no reasoning was run."
            if not self.settings.meterless_enabled:
                detail = "METERLESS_ENABLED is false, so no reasoning was run."
            elif missing:
                detail = "Incomplete Meterless settings: " + ", ".join(missing) + "."
            return ReasoningResult("not_configured", detail, configured_model=configured)

        payload = {
            "question": question,
            "records": records,
            "prior_memory": memory_context or None,
            "instruction": (
                "Cite only record_ids included above. "
                "Do not invent Nairobi or Kilimani facts. "
                "Prior memory is context, not new evidence."
            ),
        }
        response = self.transport(
            "POST",
            self.settings.meterless_base_url + "/chat/completions",
            {**self._headers(), "Content-Type": "application/json"},
            {
                "model": configured,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
                ],
            },
            self.settings.meterless_timeout_seconds,
        )
        meta = {
            "configured_model": configured,
            "endpoint_path": "/chat/completions",
            "nvidia_label_is_not_proof": True,
        }
        if response.status == 0:
            return ReasoningResult(
                "offline",
                response.error or "Nightshift unreachable",
                configured_model=configured,
                http_status=0,
                provider_meta=meta,
            )
        if response.status in (401, 403):
            return ReasoningResult(
                "unauthorized",
                "Nightshift rejected the reasoning request (HTTP %s)." % response.status,
                configured_model=configured,
                http_status=response.status,
                provider_meta=meta,
            )
        if response.status == 429:
            return ReasoningResult(
                "rate_limited",
                "Nightshift rate-limited the reasoning request (HTTP 429).",
                configured_model=configured,
                http_status=429,
                provider_meta=meta,
            )
        if response.status == 503:
            return ReasoningResult(
                "hotspot_offline",
                _hotspot_detail(response.body, response.raw_text),
                configured_model=configured,
                http_status=503,
                provider_meta=meta,
            )
        if response.status != 200:
            return ReasoningResult(
                "error",
                "Nightshift reasoning failed: HTTP %s %s"
                % (response.status, scrub(response.raw_text)),
                configured_model=configured,
                http_status=response.status,
                provider_meta=meta,
            )

        response_model = _response_model(response.body)
        meta["response_model"] = response_model
        if response_model and response_model != configured:
            return ReasoningResult(
                "model_mismatch",
                (
                    "The endpoint answered with model %r, not the configured %r. "
                    "Findings were not accepted. No silent fallback."
                    % (response_model, configured)
                ),
                response_text=_message_text(response.body) or "",
                configured_model=configured,
                response_model=response_model,
                http_status=200,
                provider_meta=meta,
            )

        content = _message_text(response.body)
        if content is None:
            return ReasoningResult(
                "unrecognized",
                "Nightshift returned a completion this adapter does not parse.",
                configured_model=configured,
                response_model=response_model,
                http_status=200,
                provider_meta=meta,
            )
        result = _accept_findings(content, {record["record_id"] for record in records})
        result.response_text = content
        result.configured_model = configured
        result.response_model = response_model or configured
        result.http_status = 200
        result.provider_meta = meta
        if result.state == "ok":
            result.detail += " Configured model %r." % configured
            if response_model:
                result.detail += " Response model %r." % response_model
        return result

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.settings.meterless_api_key}",
            "meterless-app": self.settings.meterless_app_id,
            "meterless-scope": "user",
        }


def _hotspot_detail(body: Any, raw_text: str) -> str:
    message = ""
    code = ""
    if isinstance(body, dict):
        error = body.get("error")
        if isinstance(error, dict):
            message = str(error.get("message") or "")
            code = str(error.get("code") or "")
        elif isinstance(body.get("message"), str):
            message = body["message"]
    detail = "Nightshift hotspot is offline (HTTP 503)."
    if code:
        detail += " code=%s." % code
    if message:
        detail += " " + scrub(message)
    else:
        detail += " " + scrub(raw_text)
    detail += (
        " Keep the Meterless Web session tab open (Session Hotspot) or the companion "
        "running, then retry. No other model was substituted."
    )
    return detail.strip()


def _model_ids(body: dict[str, Any]) -> list[str]:
    data = body.get("data")
    if not isinstance(data, list):
        return []
    ids = []
    for item in data:
        if isinstance(item, dict) and isinstance(item.get("id"), str):
            ids.append(item["id"])
    return ids


def _response_model(body: Any) -> str | None:
    if isinstance(body, dict) and isinstance(body.get("model"), str) and body["model"].strip():
        return body["model"].strip()
    return None


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
            "Nightshift did not return JSON. The text was kept as an interpretation only, not as findings.",
            response_text=content,
        )
    if not isinstance(parsed, dict) or not isinstance(parsed.get("findings"), list):
        return ReasoningResult(
            "discarded",
            "Nightshift JSON had no findings array. Nothing was accepted as a finding.",
            response_text=content,
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
            {
                "statement": statement.strip(),
                "record_ids": list(record_ids),
                "source": "nightshift_ai_interpretation",
            }
        )
    detail = "Accepted %s cited finding(s)." % len(accepted)
    if discarded:
        detail += " Discarded %s finding(s) that did not cite retrieved records." % discarded
    return ReasoningResult("ok", detail, findings=accepted, discarded=discarded)
