"""Local H-MEM subset for investigation memory.

This follows the canonical record, the no-model capture fallback, and the hybrid
retrieval formula in engines/hmem/AGENTS.md and the reference embedder. The
embedding is the reference's deterministic 64-dimensional token hash, not a
downloaded model. Dreaming, sleep, and conflict resolution are not implemented.
The upstream conformance suite has not been run.
"""

from __future__ import annotations

import json
import math
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

DAY_MS = 24 * 60 * 60 * 1000
TOP_N = 5
THRESHOLD = 0.35
RECENCY_DAYS = 14
DIM = 64
LAYER_WEIGHT = {"long_term": 1.0, "working": 0.8, "short_term": 0.6}
ORIGINS = {
    "chat_message",
    "user_correction",
    "file_save",
    "file_open",
    "file_edit",
    "model_response",
    "plan_completion",
    "document",
    "manual",
    "dream",
    "sleep_synthesis",
}
PLANNING_TOKENS = {
    "permit",
    "permits",
    "housing",
    "plan",
    "planning",
    "zoning",
    "land",
    "record",
    "records",
    "source",
    "sources",
}


def tokenize(text: str) -> list[str]:
    cleaned = "".join(ch.lower() if ch.isalnum() else " " for ch in text or "")
    return [token for token in cleaned.split() if len(token) > 1]


def _fnv1a(token: str) -> int:
    hash_value = 0x811C9DC5
    for character in token:
        hash_value ^= ord(character)
        hash_value = (hash_value * 0x01000193) & 0xFFFFFFFF
    return hash_value


def embed(text: str) -> list[float]:
    vector = [0.0] * DIM
    for token in tokenize(text):
        hashed = _fnv1a(token)
        index = hashed % DIM
        sign = 1.0 if ((hashed >> 8) % 2) == 0 else -1.0
        magnitude = 1 + ((hashed >> 16) % 8) / 8
        vector[index] += sign * magnitude
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        return vector
    return [value / norm for value in vector]


def _cosine(left: list[float], right: list[float]) -> float:
    return sum(a * b for a, b in zip(left, right))


def _jaccard(left: list[str], right: list[str]) -> float:
    a = set(left)
    b = set(right)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def classify_domain(text: str, tags: list[str]) -> str:
    if set(tokenize(text)) & PLANNING_TOKENS or any(tag.startswith("project:") for tag in tags):
        return "planning"
    return "general"


@dataclass
class Memory:
    id: str
    content: str
    type: str
    layer: str
    timestamp: int
    lastAccessed: int
    accessCount: int
    tags: list[str]
    embedding: list[float]
    confidence: float
    source: str
    provenance: dict[str, Any]
    domain: str
    namespace: str
    entities: list[str] = field(default_factory=list)
    relatedTo: list[str] = field(default_factory=list)
    supersededBy: str | None = None

    def public(self, score: float | None = None) -> dict[str, Any]:
        view = {
            "id": self.id,
            "content": self.content,
            "type": self.type,
            "layer": self.layer,
            "source": self.source,
            "confidence": round(self.confidence, 4),
            "domain": self.domain,
            "provenance": {
                "origin": self.provenance.get("origin"),
                "label": self.provenance.get("label"),
                "refs": list(self.provenance.get("refs") or []),
            },
            "standing": _standing(self),
        }
        if score is not None:
            view["score"] = round(score, 4)
        return view


def _standing(memory: Memory) -> str:
    origin = memory.provenance.get("origin")
    if origin == "model_response":
        return "ai_interpretation"
    if memory.type == "factual" and origin == "document":
        return "retrieved_evidence"
    return "unverified_note"


class Hmem:
    def __init__(self, path: Path | None = None, *, clock_ms: Any | None = None) -> None:
        self.path = path
        self.clock_ms = clock_ms or (lambda: int(__import__("time").time() * 1000))
        self.memories: list[Memory] = []
        self.ledger: list[dict[str, Any]] = []
        if path and path.exists():
            self._load()

    def remember(
        self,
        *,
        content: str,
        source: str,
        origin: str,
        memory_type: str = "general",
        layer: str = "working",
        refs: list[str] | None = None,
        confidence: float = 0.8,
        tags: list[str] | None = None,
        label: str = "",
    ) -> dict[str, Any]:
        text = (content or "").strip()
        cited = (source or "").strip()
        if not cited:
            raise ValueError("H-MEM rejects a record with no source.")
        if not text:
            raise ValueError("H-MEM rejects empty content.")
        if origin not in ORIGINS:
            raise ValueError("H-MEM origin is not one of the documented event origins.")
        existing = next(
            (item for item in self.memories if item.content == text and item.source == cited),
            None,
        )
        if existing:
            return existing.public()
        now = int(self.clock_ms())
        tag_list = list(tags or [])
        memory = Memory(
            id=uuid.uuid4().hex[:16],
            content=text,
            type=memory_type,
            layer=layer,
            timestamp=now,
            lastAccessed=now,
            accessCount=0,
            tags=tag_list[:12],
            embedding=embed(text),
            confidence=_clamp01(confidence),
            source=cited,
            provenance={
                "origin": origin,
                "learnedAt": now,
                "label": label or origin,
                "refs": list(refs or [])[:12],
            },
            domain=classify_domain(text, tag_list),
            namespace="investigation",
            entities=_entities(text),
        )
        self.memories.append(memory)
        self._log(memory.id, "create", {"source": cited, "origin": origin})
        self._save()
        return memory.public()

    def query(self, text: str) -> dict[str, Any]:
        query_embed = embed(text)
        query_tokens = tokenize(text)[:8]
        query_domain = classify_domain(text, [])
        now = int(self.clock_ms())
        scored: list[tuple[float, Memory]] = []
        for memory in self.memories:
            score = _score(memory, query_embed, query_tokens, query_domain, now)
            if score >= THRESHOLD:
                scored.append((score, memory))
        scored.sort(key=lambda item: (-item[0], item[1].id))
        chosen = scored[:TOP_N]
        for _, memory in chosen:
            memory.lastAccessed = now
            memory.accessCount += 1
            self._log(memory.id, "read", {"query": text[:200]})
        if chosen:
            self._save()
        strategy = "minimal" if len(chosen) <= 1 else "comprehensive"
        return {
            "memories": [memory.public(score) for score, memory in chosen],
            "context": _reinjection(chosen),
            "trace": {
                "retrievalReason": "hybrid ranking; semantic term uses the reference token-hash embedding",
                "strategy": strategy,
                "threshold": THRESHOLD,
                "conformance_suite": "not_run",
            },
        }

    def recent(self, limit: int = 8) -> list[dict[str, Any]]:
        ordered = sorted(self.memories, key=lambda item: item.timestamp, reverse=True)
        return [item.public() for item in ordered[:limit]]

    def audit(self, limit: int = 8) -> list[dict[str, Any]]:
        return [
            {"action": entry["action"], "memoryId": entry["memoryId"], "timestamp": entry["timestamp"]}
            for entry in self.ledger[-limit:]
        ]

    def _log(self, memory_id: str, action: str, details: dict[str, Any]) -> None:
        self.ledger.append(
            {
                "memoryId": memory_id,
                "action": action,
                "actor": "jirani",
                "timestamp": int(self.clock_ms()),
                "details": details,
            }
        )

    def _load(self) -> None:
        payload = json.loads(self.path.read_text(encoding="utf-8")) if self.path else {}
        self.memories = [_memory_from(item) for item in payload.get("memories", [])]
        self.ledger = list(payload.get("ledger", []))

    def _save(self) -> None:
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "memories": [asdict(item) for item in self.memories],
            "ledger": self.ledger,
        }
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload), encoding="utf-8")
        temporary.replace(self.path)


def _memory_from(raw: dict[str, Any]) -> Memory:
    return Memory(
        id=raw["id"],
        content=raw["content"],
        type=raw["type"],
        layer=raw["layer"],
        timestamp=raw["timestamp"],
        lastAccessed=raw["lastAccessed"],
        accessCount=raw["accessCount"],
        tags=list(raw.get("tags") or []),
        embedding=list(raw.get("embedding") or embed(raw["content"])),
        confidence=float(raw["confidence"]),
        source=raw["source"],
        provenance=dict(raw.get("provenance") or {}),
        domain=raw.get("domain") or "general",
        namespace=raw.get("namespace") or "investigation",
        entities=list(raw.get("entities") or []),
        relatedTo=list(raw.get("relatedTo") or []),
        supersededBy=raw.get("supersededBy"),
    )


def _score(
    memory: Memory,
    query_embed: list[float],
    query_tokens: list[str],
    query_domain: str,
    now: int,
) -> float:
    semantic = _clamp01(_cosine(query_embed, memory.embedding or embed(memory.content)))
    keyword = _jaccard(query_tokens, tokenize(memory.content))
    tag = _jaccard(query_tokens, [item.lower() for item in memory.tags])
    domain = 1.0 if memory.domain == query_domain else 0.0
    entity = _jaccard(query_tokens, [item.lower() for item in memory.entities])
    layer = LAYER_WEIGHT.get(memory.layer, 0.6)
    age_days = max(0.0, (now - memory.lastAccessed) / DAY_MS)
    recency = math.exp(-age_days / RECENCY_DAYS)
    superseded = 1.0 if memory.supersededBy else 0.0
    raw = (
        0.35 * semantic
        + 0.20 * keyword
        + 0.10 * tag
        + 0.10 * domain
        + 0.15 * entity
        + 0.05 * layer
        + 0.05 * recency
        - 0.20 * superseded
    )
    return _clamp01(raw) * memory.confidence


def _entities(text: str) -> list[str]:
    found: list[str] = []
    for token in (text or "").replace(",", " ").split():
        if "." in token and token.replace(".", "").replace("_", "").isalnum():
            found.append(token.strip("."))
        if len(found) == 10:
            break
    return found


def _reinjection(chosen: list[tuple[float, Memory]]) -> str:
    if not chosen:
        return ""
    lines = ["[MEMORY CONTEXT]"]
    for _, memory in chosen:
        marker = {"long_term": "LT", "working": "WK"}.get(memory.layer, "ST")
        lines.append(f"- [{marker}] {memory.content} <{memory.id}>")
    lines.append("[/MEMORY CONTEXT]")
    return "\n".join(lines)
