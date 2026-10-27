"""Environment configuration. Secrets stay in process memory and are omitted from repr."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*){0,2}$")
ORIGIN = re.compile(r"https?://[^/\s]+$")
REST_BASE = re.compile(r"https?://\S+/api/v1\.0$")
ORG_ID = re.compile(r"^[0-9]+$")

# Supplied Zetaris samples. They are not urban-planning evidence.
SAMPLE_DATABASES = frozenset({"ny_taxi", "tpcds", "tpcds_db", "tpch", "tpch_db"})


@dataclass(frozen=True)
class RegisteredSource:
    name: str
    description: str


@dataclass(frozen=True)
class Settings:
    zetaris_base_url: str
    zetaris_rest_url: str
    zetaris_org_id: str
    zetaris_org_slug: str
    zetaris_api_key: str
    zetaris_username: str
    zetaris_password: str
    zetaris_query_limit: int
    zetaris_timeout_seconds: float
    zetaris_engine_id: str
    zetaris_sources: tuple[RegisteredSource, ...]
    meterless_base_url: str
    meterless_runtime_token: str
    meterless_model: str
    meterless_app_id: str
    meterless_timeout_seconds: float
    scout_signing_key: str
    warnings: tuple[str, ...]

    @property
    def zetaris_configured(self) -> bool:
        """Direct REST, as in scripts/zetaris_sql.py RestChannel. The UI origin is not enough."""
        return bool(
            self.zetaris_api_key
            and ORG_ID.fullmatch(self.zetaris_org_id or "")
            and REST_BASE.fullmatch(self.zetaris_rest_url or "")
        )

    @property
    def nightshift_configured(self) -> bool:
        return bool(self.meterless_base_url and self.meterless_runtime_token)

    def public_view(self) -> dict[str, object]:
        return {
            "zetaris_configured": self.zetaris_configured,
            "zetaris_rest_url": self.zetaris_rest_url or None,
            "zetaris_base_url_set": bool(self.zetaris_base_url),
            "zetaris_org_id_set": bool(self.zetaris_org_id),
            "zetaris_org_slug_set": bool(self.zetaris_org_slug),
            "zetaris_api_key_set": bool(self.zetaris_api_key),
            "zetaris_username_set": bool(self.zetaris_username),
            "registered_source_count": len(self.zetaris_sources),
            "registered_sources": [source.name for source in self.zetaris_sources],
            "nightshift_configured": self.nightshift_configured,
            "nightshift_base_url": self.meterless_base_url or None,
            "nightshift_token_set": bool(self.meterless_runtime_token),
            "nightshift_model": self.meterless_model,
            "scout_signing_key_set": bool(self.scout_signing_key),
            "warnings": list(self.warnings),
        }

    def __repr__(self) -> str:
        view = self.public_view()
        view["zetaris_api_key_set"] = self.public_view()["zetaris_api_key_set"]
        return f"Settings({view})"


def _clean(value: str | None) -> str:
    return (value or "").strip()


def parse_sources(raw: str) -> tuple[tuple[RegisteredSource, ...], tuple[str, ...]]:
    sources: list[RegisteredSource] = []
    warnings: list[str] = []
    if not raw.strip():
        return tuple(), tuple()
    for part in raw.split(";;"):
        entry = part.strip()
        if not entry:
            continue
        name, separator, description = entry.partition("|")
        name = name.strip()
        description = description.strip()
        if not separator or not description:
            warnings.append(f"Ignored source entry without a description: {name or entry}")
            continue
        if not IDENTIFIER.fullmatch(name):
            warnings.append(f"Ignored source with an unsafe name: {name}")
            continue
        if name.lower().split(".", 1)[0] in SAMPLE_DATABASES:
            warnings.append(
                f"Ignored {name}: supplied sample data is not planning evidence."
            )
            continue
        sources.append(RegisteredSource(name=name, description=description))
    return tuple(sources), tuple(warnings)


def normalize_nightshift_base_url(raw: str) -> str:
    url = _clean(raw).rstrip("/")
    if not url:
        return ""
    for suffix in ("/chat/completions", "/models", "/healthz"):
        if url.endswith(suffix):
            url = url[: -len(suffix)]
            break
    url = url.rstrip("/")
    if url.endswith("/v1/v1"):
        url = url[: -len("/v1")]
    if not url.endswith("/v1"):
        url = url + "/v1"
    return url


def load_settings(
    environ: dict[str, str] | None = None,
    *,
    load_env_file: bool = True,
) -> Settings:
    if load_env_file:
        load_dotenv(ROOT / ".env", override=False)
    env = os.environ if environ is None else environ

    limit_raw = _clean(env.get("ZETARIS_QUERY_LIMIT")) or "25"
    timeout_raw = _clean(env.get("ZETARIS_TIMEOUT_SECONDS")) or "15"
    night_timeout_raw = _clean(env.get("METERLESS_TIMEOUT_SECONDS")) or "60"
    warnings: list[str] = []
    try:
        limit = int(limit_raw)
    except ValueError:
        limit = 25
        warnings.append("ZETARIS_QUERY_LIMIT is not an integer; using 25.")
    if limit < 1:
        limit = 25
        warnings.append("ZETARIS_QUERY_LIMIT must be positive; using 25.")
    limit = min(limit, 100)

    def _positive_float(raw: str, default: float, label: str) -> float:
        try:
            value = float(raw)
        except ValueError:
            warnings.append(f"{label} is not a number; using {default}.")
            return default
        if value <= 0:
            warnings.append(f"{label} must be positive; using {default}.")
            return default
        return value

    sources, source_warnings = parse_sources(env.get("ZETARIS_SOURCES", ""))
    warnings.extend(source_warnings)

    base_url = _clean(env.get("ZETARIS_BASE_URL")).rstrip("/")
    if base_url and not ORIGIN.fullmatch(base_url):
        warnings.append("ZETARIS_BASE_URL must be an HTTP(S) origin without a path.")
    rest_url = _clean(env.get("ZETARIS_REST_URL")).rstrip("/")
    if rest_url and not REST_BASE.fullmatch(rest_url):
        warnings.append("ZETARIS_REST_URL must be the API base ending in /api/v1.0.")
    org_id = _clean(env.get("ZETARIS_ORG_ID"))
    if org_id and not ORG_ID.fullmatch(org_id):
        warnings.append("ZETARIS_ORG_ID must be the numeric organisation id, not the login slug.")
    org_slug = _clean(env.get("ZETARIS_ORG_SLUG"))

    return Settings(
        zetaris_base_url=base_url,
        zetaris_rest_url=rest_url,
        zetaris_org_id=org_id,
        zetaris_org_slug=org_slug,
        zetaris_api_key=_clean(env.get("ZETARIS_API_KEY")),
        zetaris_username=_clean(env.get("ZETARIS_USERNAME")),
        zetaris_password=_clean(env.get("ZETARIS_PASSWORD")),
        zetaris_query_limit=limit,
        zetaris_timeout_seconds=_positive_float(timeout_raw, 15, "ZETARIS_TIMEOUT_SECONDS"),
        zetaris_engine_id=_clean(env.get("ZETARIS_ENGINE_ID")),
        zetaris_sources=sources,
        meterless_base_url=normalize_nightshift_base_url(
            env.get("METERLESS_BASE_URL", "")
        ),
        meterless_runtime_token=_clean(env.get("METERLESS_RUNTIME_TOKEN")),
        meterless_model=_clean(env.get("METERLESS_MODEL")) or "meterless/auto",
        meterless_app_id=_clean(env.get("METERLESS_APP_ID")) or "jirani-intelligence",
        meterless_timeout_seconds=_positive_float(
            night_timeout_raw, 60, "METERLESS_TIMEOUT_SECONDS"
        ),
        scout_signing_key=_clean(env.get("SCOUT_SIGNING_KEY")),
        warnings=tuple(warnings),
    )
