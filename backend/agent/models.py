"""Structured investigation objects. These hold only values the workflow produced."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


def _jsonable(value: Any) -> Any:
    if hasattr(value, "as_dict"):
        return value.as_dict()
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    return value


@dataclass
class SupportingRecord:
    record_id: str
    source: str
    kind: str
    fields: dict[str, str]
    statement: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Finding:
    statement: str
    record_ids: list[str]
    source: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class LayerStatus:
    name: str
    state: str
    detail: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class InvestigationBrief:
    question: str
    findings: list[Finding] = field(default_factory=list)
    supporting_records: list[SupportingRecord] = field(default_factory=list)
    uncertainty: list[str] = field(default_factory=list)
    evidence_gaps: list[str] = field(default_factory=list)
    next_steps: list[str] = field(default_factory=list)
    layer_status: list[LayerStatus] = field(default_factory=list)
    contract: dict[str, Any] | None = None
    clarification: dict[str, Any] | None = None
    prior_memories: list[dict[str, Any]] = field(default_factory=list)
    nightshift_handoff: dict[str, Any] | None = None
    nightshift_meta: dict[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        return _jsonable(asdict(self))
