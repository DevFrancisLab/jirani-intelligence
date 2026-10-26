"""Scout Intent adapter.

Scout Intent is the Meterless engine that runs before any query. It senses an
intent, binds the question, guards the request, routes to tools, and signs an
execution contract. This is an in-process Stage-1 implementation of that
pipeline. It is not a pass of the upstream eval harness.

Spec: https://github.com/Meterless/Meterless/blob/main/engines/scout-intent/AGENTS.md
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

REGISTRY_VERSION = 1
POLICY_PACK = "jirani-default"
CONTRACT_TTL = timedelta(minutes=5)
_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"

# activation is the matched-trigger weight that normalizes lexical score to 1.
REGISTRY: list[dict[str, Any]] = [
    {
        "id": "planning.discover",
        "category": "planning",
        "description": "List data sources registered in Zetaris before drawing a planning conclusion.",
        "triggers": (
            ("what sources", 3),
            ("which sources", 3),
            ("data sources", 3),
            ("what data", 3),
            ("available data", 3),
            ("catalog", 2),
            ("show databases", 2),
        ),
        "activation": 3,
        "capabilities": ({"id": "catalog.list", "required": True},),
        "risk_class": "low",
        "surfaces": ("investigation",),
        "roles": ("planner",),
        "examples": ("What sources are registered?", "Show the data catalog"),
        "version": 1,
    },
    {
        "id": "planning.investigate",
        "category": "planning",
        "description": "Retrieve registered planning records for one investigation question.",
        "triggers": (
            ("land use", 3),
            ("land-use", 3),
            ("zoning", 3),
            ("housing", 2),
            ("permit", 2),
            ("parcel", 2),
            ("transport", 2),
            ("infrastructure", 2),
            ("neighbourhood", 2),
            ("neighborhood", 2),
            ("water", 2),
            ("sewer", 2),
            ("urban", 1),
            ("planning", 1),
        ),
        "activation": 3,
        "capabilities": (
            {"id": "records.query", "required": True},
            {"id": "evidence.reason", "required": False},
        ),
        "risk_class": "medium",
        "surfaces": ("investigation",),
        "roles": ("planner",),
        "examples": (
            "Which housing permits are in the registered records?",
            "Investigate zoning for this question.",
        ),
        "version": 1,
    },
]

TOOLS = {
    "catalog.list": {"tool": "zetaris.list_sources", "requires": "zetaris"},
    "records.query": {"tool": "zetaris.select_registered", "requires": "sources"},
    "evidence.reason": {"tool": "nightshift.reason_over_records", "requires": "nightshift"},
}

INJECTION_PATTERNS = (
    "ignore previous instructions",
    "ignore all previous",
    "[inst]",
    "<|im_start|>",
    "reveal the api key",
    "reveal the token",
    "print the secret",
    "system prompt",
)


@dataclass
class Candidate:
    intent_id: str
    lexical: float
    span: tuple[int, int]


@dataclass
class Decision:
    blocked: bool
    reason: str
    candidates: list[Candidate]
    clarification: dict[str, Any] | None
    contract: dict[str, Any] | None
    telemetry: list[dict[str, Any]] = field(default_factory=list)
    band_source: str = "stage1_confidence_because_stage2_unavailable"

    def as_public_dict(self) -> dict[str, Any]:
        contract = None
        if self.contract:
            contract = {
                "contract_id": self.contract["contractId"],
                "trace_id": self.contract["traceId"],
                "intent": self.contract["intent"]["primary"],
                "confidence": self.contract["intent"]["confidence"],
                "band": self.contract["intent"]["band"],
                "alternates": self.contract["intent"]["alternates"],
                "risk": self.contract["risk"]["level"],
                "tool_plan": [step["tool"] for step in self.contract["toolPlan"]],
                "routing_failures": list(self.contract["routingFailures"]),
                "signed": bool(self.contract.get("signature")),
                "expires_at": self.contract["expiresAt"],
                "stage2": "skipped",
                "band_source": self.band_source,
            }
        return {
            "blocked": self.blocked,
            "reason": self.reason,
            "clarification": self.clarification,
            "contract": contract,
            "telemetry": self.telemetry,
        }


class ScoutIntent:
    """Stage-1 Scout pipeline. Stage-2 semantic rescoring is intentionally absent."""

    def __init__(self, signing_key: str = "", clock: Callable[[], datetime] | None = None) -> None:
        self.signing_key = signing_key or hashlib.sha256(os.urandom(32)).hexdigest()
        self.signing_key_source = "configured" if signing_key else "ephemeral"
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self._last_intent: str | None = None

    def decide(
        self,
        prompt: str,
        *,
        surface: str = "investigation",
        role: str = "planner",
        availability: dict[str, bool] | None = None,
        randomness: bytes | None = None,
    ) -> Decision:
        started = time.perf_counter()
        availability = availability or {}
        text = prompt or ""
        lowered = text.lower()
        injection = _injection(lowered)
        if injection:
            elapsed = round((time.perf_counter() - started) * 1000, 3)
            return Decision(
                blocked=True,
                reason=injection,
                candidates=[],
                clarification=None,
                contract=None,
                telemetry=[
                    {
                        "event": "scout.decision",
                        "band": "block",
                        "latency_ms": elapsed,
                        "stage2": "skipped",
                    }
                ],
            )

        policy = _policy(surface, role)
        if policy:
            return Decision(
                blocked=True,
                reason=policy,
                candidates=[],
                clarification=None,
                contract=None,
                telemetry=[{"event": "scout.decision", "band": "block", "stage2": "skipped"}],
            )

        candidates = _score(lowered)
        ranked = sorted(candidates, key=lambda item: (-item.lexical, item.intent_id))
        winner = ranked[0]
        band = _band(winner.lexical)
        primary_id = winner.intent_id
        clarification = None
        selected = [winner]
        if band == "reject":
            primary_id = "general.clarify"
            selected = []
            clarification = {
                "trigger": "reject",
                "question": "The question did not match a planning intent.",
                "options": [item.intent_id for item in ranked],
            }
        elif band == "low":
            clarification = {
                "trigger": "low-band",
                "question": "Scout Intent is not confident enough to query.",
                "options": [item.intent_id for item in ranked],
            }
        elif (
            len(ranked) > 1
            and band == "medium"
            and abs(ranked[0].lexical - ranked[1].lexical) <= 0.05
        ):
            clarification = {
                "trigger": "tie",
                "question": "Two intents are too close to route automatically.",
                "options": [ranked[0].intent_id, ranked[1].intent_id],
            }
        elif (
            len(ranked) > 1
            and _band(ranked[1].lexical) == "high"
            and _spans_disjoint(ranked[0].span, ranked[1].span)
        ):
            selected = ranked[:2]

        if clarification:
            tool_plan: list[dict[str, str]] = []
            routing_failures: list[str] = []
        else:
            tool_plan, routing_failures = _route(selected, availability)

        recency = 1.0 if self._last_intent == primary_id else 0.0
        formula_score = round(0.40 * winner.lexical + 0.05 * recency, 4)
        now = self.clock()
        if randomness is None:
            randomness = os.urandom(10)
        contract = {
            "contractId": _ulid(int(now.timestamp() * 1000), randomness),
            "traceId": str(uuid.uuid4()),
            "intent": {
                "primary": primary_id,
                "parameters": {"question": text},
                "references": [],
                "confidence": round(winner.lexical, 4),
                "band": band if primary_id != "general.clarify" else "reject",
                "formulaScore": formula_score,
                "alternates": [
                    {"intent": item.intent_id, "confidence": round(item.lexical, 4)}
                    for item in ranked
                    if item.intent_id != primary_id
                ],
            },
            "risk": {
                "level": "low" if primary_id != "planning.investigate" else "medium",
                "flags": ["rate_limit_not_enforced", "stage2_skipped"],
                "redactions": [],
                "approvals": [],
            },
            "toolPlan": tool_plan,
            "routingFailures": routing_failures,
            "modelProfile": {
                "provider": "meterless-nightshift",
                "model": "meterless/auto",
                "dataClass": "planning-records",
            },
            "scope": {
                "user": role,
                "surface": surface,
                "capabilities": [step["capability"] for step in tool_plan],
            },
            "issuedAt": _iso(now),
            "expiresAt": _iso(now + CONTRACT_TTL),
            "registryVersion": REGISTRY_VERSION,
            "policyPackVersion": POLICY_PACK,
            "signedBy": "scout",
        }
        contract["signature"] = sign_contract(contract, self.signing_key)
        self._last_intent = primary_id
        elapsed = round((time.perf_counter() - started) * 1000, 3)
        telemetry = [
            {
                "event": "scout.decision",
                "intent": primary_id,
                "band": contract["intent"]["band"],
                "latency_ms": elapsed,
                "stage2": "skipped",
            },
            {"event": "contract.issued", "contractId": contract["contractId"]},
        ]
        if clarification:
            telemetry.append(
                {"event": "scout.clarification", "trigger": clarification["trigger"]}
            )
        reason = "Contract issued."
        if routing_failures:
            reason = "Contract issued with routing failures: " + "; ".join(routing_failures)
        if clarification:
            reason = clarification["question"]
        return Decision(
            blocked=False,
            reason=reason,
            candidates=ranked,
            clarification=clarification,
            contract=contract,
            telemetry=telemetry,
        )

    def verify(self, contract: dict[str, Any], *, now: datetime | None = None) -> str | None:
        if not contract or not contract.get("signature"):
            return "unsigned"
        signature = contract["signature"]
        if not hmac.compare_digest(signature, sign_contract(contract, self.signing_key)):
            return "tampered"
        if contract.get("signedBy") != "scout":
            return "signer"
        expires = datetime.fromisoformat(contract["expiresAt"].replace("Z", "+00:00"))
        current = now or self.clock()
        if current >= expires:
            return "expired"
        return None

    def stage1_self_test(self) -> dict[str, Any]:
        probes = (
            "What data sources are registered?",
            "Investigate housing permits in the planning records.",
            "hello",
            "Show the catalog",
        )
        started = time.perf_counter()
        for probe in probes:
            _score(probe.lower())
        elapsed_ms = (time.perf_counter() - started) * 1000
        return {
            "probes": len(probes),
            "latency_ms": round(elapsed_ms, 3),
            "within_16ms": elapsed_ms < 16,
        }


def sign_contract(contract: dict[str, Any], key: str) -> str:
    payload = {name: value for name, value in contract.items() if name != "signature"}
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hmac.new(key.encode("utf-8"), canonical.encode("utf-8"), hashlib.sha256).hexdigest()


def _score(lowered: str) -> list[Candidate]:
    candidates = []
    for intent in REGISTRY:
        matched = 0
        span = (0, 0)
        for phrase, weight in intent["triggers"]:
            index = lowered.find(phrase)
            if index >= 0:
                matched += weight
                if span == (0, 0):
                    span = (index, index + len(phrase))
        lexical = min(1.0, matched / intent["activation"]) if matched else 0.0
        candidates.append(Candidate(intent["id"], round(lexical, 4), span))
    return candidates


def _band(score: float) -> str:
    if score >= 0.80:
        return "high"
    if score >= 0.55:
        return "medium"
    if score >= 0.40:
        return "low"
    return "reject"


def _spans_disjoint(left: tuple[int, int], right: tuple[int, int]) -> bool:
    if left == (0, 0) or right == (0, 0):
        return False
    return left[1] <= right[0] or right[1] <= left[0]


def _route(
    selected: list[Candidate],
    availability: dict[str, bool],
) -> tuple[list[dict[str, str]], list[str]]:
    plan: list[dict[str, str]] = []
    failures: list[str] = []
    seen = set()
    by_id = {intent["id"]: intent for intent in REGISTRY}
    for candidate in selected:
        if candidate.lexical < 0.55:
            continue
        for capability in by_id[candidate.intent_id]["capabilities"]:
            if capability["id"] in seen:
                continue
            seen.add(capability["id"])
            spec = TOOLS[capability["id"]]
            if not availability.get(spec["requires"], False):
                message = f"{capability['id']} unavailable ({spec['requires']})"
                if capability["required"]:
                    failures.append(message)
                continue
            plan.append({"capability": capability["id"], "tool": spec["tool"]})
    return plan, failures


def _injection(lowered: str) -> str:
    for pattern in INJECTION_PATTERNS:
        if pattern in lowered:
            return "Blocked by the injection guard. The prompt was not sent to a tool."
    return ""


def _policy(surface: str, role: str) -> str:
    if surface != "investigation":
        return f"Surface {surface!r} is outside the planning registry."
    if role != "planner":
        return f"Role {role!r} cannot run a planning investigation."
    return ""


def _iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _ulid(now_ms: int, randomness: bytes) -> str:
    if len(randomness) != 10:
        raise ValueError("ULID randomness must be 10 bytes")
    value = (now_ms << 80) | int.from_bytes(randomness, "big")
    chars = []
    for _ in range(26):
        chars.append(_CROCKFORD[value & 31])
        value >>= 5
    return "".join(reversed(chars))
