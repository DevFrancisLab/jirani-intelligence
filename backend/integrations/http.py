"""Small HTTP helper. Callers scrub secrets before any text reaches the UI."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

_SECRET_PATTERNS = (
    re.compile(r"Bearer\s+\S+", re.IGNORECASE),
    re.compile(r"(?i)(api[_-]?key|token|password|secret|authorization)\s*[:=]\s*\S+"),
)


@dataclass
class HttpResponse:
    status: int
    body: Any
    raw_text: str
    error: str = ""


Transport = Callable[..., HttpResponse]


def scrub(text: str, limit: int = 400) -> str:
    cleaned = text or ""
    for pattern in _SECRET_PATTERNS:
        cleaned = pattern.sub("[redacted]", cleaned)
    cleaned = cleaned.replace("\n", " ").strip()
    if len(cleaned) > limit:
        return cleaned[:limit] + "…"
    return cleaned


def urllib_transport(
    method: str,
    url: str,
    headers: dict[str, str],
    body: dict[str, Any] | None,
    timeout: float,
) -> HttpResponse:
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
    # Some Meterless hotspot proxies (Cloudflare) reject empty/python-urllib agents.
    merged = {
        "User-Agent": "jirani-intelligence/1.0",
        "Accept": "application/json",
        **(headers or {}),
    }
    request = Request(url, data=data, headers=merged, method=method)
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
            parsed: Any = None
            if raw:
                try:
                    parsed = json.loads(raw)
                except json.JSONDecodeError:
                    parsed = None
            return HttpResponse(status=response.status, body=parsed, raw_text=raw)
    except HTTPError as error:
        raw = error.read().decode("utf-8", errors="replace")
        parsed = None
        try:
            parsed = json.loads(raw) if raw else None
        except json.JSONDecodeError:
            parsed = None
        return HttpResponse(
            status=error.code,
            body=parsed,
            raw_text=raw,
            error=f"HTTP {error.code}",
        )
    except (TimeoutError, URLError, OSError) as error:
        reason = getattr(error, "reason", error)
        return HttpResponse(
            status=0,
            body=None,
            raw_text="",
            error=scrub(f"unreachable: {reason}"),
        )
