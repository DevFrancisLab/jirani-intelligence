"""Zetaris UI-proxy client.

This follows scripts/query_zetaris.py and scripts/zetaris_api.py in the Zetaris
getting-started repository. ZETARIS_BASE_URL is the web UI origin with no path.
The organisation slug and a login-page URL are not the endpoint, and this client
does not call the direct REST API.

POST {ZETARIS_BASE_URL}/api/proxy/sql-editor/sqls/run-query
Headers: Authorization: Bearer <ZETARIS_API_KEY>, X-Org-ID, X-Request-ID,
Content-Type: application/json
Body: {"sql": <statement>, "limit": <n>, "engineId": <optional>}

Supplied NY Taxi rows are New York sample data. They are not evidence about
Nairobi or Kilimani.
"""

from __future__ import annotations

import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from agent.config import ORIGIN, SAMPLE_DATABASES, Settings
from integrations.http import HttpResponse, scrub, urllib_transport

QUERY_PATH = "/api/proxy/sql-editor/sqls/run-query"
SELECT_1 = "SELECT 1"
# The published SQL Workspace sample read is `SELECT * FROM NY_TAXI.taxi_zones LIMIT 5`.
# This project was asked to read the known NY_TAXI.taxi_trips source with that same
# verified LIMIT 5 shape. A live call is the only proof the table exists.
TAXI_TRIPS_SAMPLE = "SELECT * FROM NY_TAXI.taxi_trips LIMIT 5"

_COMMENT = re.compile(r"/\*.*?\*/|--[^\n]*", re.DOTALL)
_START = re.compile(r"(?is)^(SELECT|WITH|SHOW|DESCRIBE|DESC|EXPLAIN)\b")
_FORBIDDEN = re.compile(
    r"(?i)\b(CREATE|DROP|ALTER|INSERT|UPDATE|DELETE|MERGE|TRUNCATE|GRANT|REVOKE|"
    r"REPLACE|REMOVE|COMPILE|CACHE|UNCACHE|LOAD|COPY|MSCK)\b"
)
_SAMPLE_NAME = re.compile(r"^(ny_taxi|tpcds(_db)?|tpch(_db)?)$", re.IGNORECASE)


@dataclass
class QueryResult:
    status: str
    detail: str
    rows: list[dict[str, str]] = field(default_factory=list)
    excluded_rows: list[dict[str, str]] = field(default_factory=list)
    http_status: int | None = None
    statement: str = ""
    duration_ms: float | None = None

    @property
    def ok(self) -> bool:
        return self.status == "ok"


class ZetarisClient:
    def __init__(self, settings: Settings, transport=urllib_transport) -> None:
        self.settings = settings
        self.transport = transport

    def probe(self) -> QueryResult:
        """SELECT 1. Success requires the documented row [['1']]."""
        return self.query(SELECT_1, kind="probe", limit=1)

    def query_taxi_trips_sample(self) -> QueryResult:
        """Read-only sample of the supplied NY Taxi trips table. Not planning evidence."""
        result = self.query(TAXI_TRIPS_SAMPLE, kind="sample", limit=5)
        result.detail = (
            "New York sample data from NY_TAXI.taxi_trips. "
            "Not evidence about Nairobi or Kilimani. " + result.detail
        )
        return result

    def list_catalog(self) -> QueryResult:
        if not self.settings.zetaris_configured:
            return QueryResult("not_configured", self._configuration_detail())
        databases = self.query("SHOW LIGHTNING DATABASES", kind="catalog")
        datasources = self.query("SHOW DATASOURCES", kind="catalog")
        if not databases.ok and not datasources.ok:
            return QueryResult(
                databases.status,
                databases.detail or datasources.detail,
                http_status=databases.http_status,
                duration_ms=databases.duration_ms,
            )
        rows = _tag(databases.rows, "SHOW LIGHTNING DATABASES") + _tag(
            datasources.rows, "SHOW DATASOURCES"
        )
        kept, excluded = split_sample_rows(rows)
        detail = f"{len(kept)} catalog row(s)"
        if excluded:
            detail += f"; {len(excluded)} supplied sample row(s) excluded"
        if databases.ok and not datasources.ok:
            detail += f". SHOW DATASOURCES failed: {datasources.detail}"
        if datasources.ok and not databases.ok:
            detail += f". SHOW LIGHTNING DATABASES failed: {databases.detail}"
        return QueryResult(
            "ok",
            detail,
            rows=kept,
            excluded_rows=excluded,
            statement="catalog",
            duration_ms=_sum_duration(databases.duration_ms, datasources.duration_ms),
        )

    def select_registered(self) -> list[QueryResult]:
        if not self.settings.zetaris_configured:
            return [QueryResult("not_configured", self._configuration_detail())]
        if not self.settings.zetaris_sources:
            return [
                QueryResult(
                    "no_sources",
                    "No planning sources are registered in ZETARIS_SOURCES.",
                )
            ]
        results = []
        for source in self.settings.zetaris_sources:
            statement = f"SELECT * FROM {source.name} LIMIT {self.settings.zetaris_query_limit}"
            result = self.query(statement, kind="records")
            result.rows = [
                {**row, "_source": source.name, "_description": source.description}
                for row in result.rows
            ]
            results.append(result)
        return results

    def query(self, statement: str, *, kind: str = "records", limit: int | None = None) -> QueryResult:
        rejection = validate_read_only(statement)
        if rejection:
            return QueryResult("rejected", rejection, statement=statement)
        if not self.settings.zetaris_configured:
            return QueryResult("not_configured", self._configuration_detail(), statement=statement)
        row_limit = limit if limit is not None else self.settings.zetaris_query_limit
        body: dict[str, Any] = {
            "sql": statement.strip().rstrip(";"),
            "limit": row_limit,
        }
        if self.settings.zetaris_engine_id:
            body["engineId"] = self.settings.zetaris_engine_id
        started = time.perf_counter()
        response = self.transport(
            "POST",
            self.settings.zetaris_base_url + QUERY_PATH,
            {
                "Authorization": f"Bearer {self.settings.zetaris_api_key}",
                "X-Org-ID": self.settings.zetaris_org_id,
                "X-Request-ID": str(uuid.uuid4()),
                "Content-Type": "application/json",
            },
            body,
            self.settings.zetaris_timeout_seconds,
        )
        duration_ms = round((time.perf_counter() - started) * 1000, 1)
        result = _interpret(response, statement, kind)
        result.duration_ms = duration_ms
        return result

    def _configuration_detail(self) -> str:
        missing = []
        if not ORIGIN.fullmatch(self.settings.zetaris_base_url or ""):
            missing.append("ZETARIS_BASE_URL to the web UI origin with no path; a login page is not the origin")
        if not self.settings.zetaris_org_id:
            missing.append("ZETARIS_ORG_ID")
        if not self.settings.zetaris_api_key:
            missing.append("ZETARIS_API_KEY")
        detail = "Zetaris UI proxy is not configured."
        if missing:
            detail += " Set " + ", ".join(missing) + "."
        if self.settings.zetaris_org_slug:
            detail += " ZETARIS_ORG_SLUG is not an API endpoint."
        if self.settings.warnings:
            detail += " " + " ".join(self.settings.warnings)
        return detail


def validate_read_only(sql: str) -> str | None:
    """Return an error when the statement is not a single read-only command."""
    stripped = _COMMENT.sub(" ", sql or "").strip()
    if stripped.endswith(";"):
        stripped = stripped[:-1].strip()
    if not stripped:
        return "SQL is empty."
    if ";" in stripped:
        return "Only one SQL statement is allowed."
    if not _START.match(stripped):
        return "Only SELECT, WITH, SHOW, DESCRIBE, and EXPLAIN statements are allowed."
    if _FORBIDDEN.search(stripped):
        return "The statement contains a command the agent is not allowed to run."
    return None


def split_sample_rows(
    rows: list[dict[str, str]],
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    kept: list[dict[str, str]] = []
    excluded: list[dict[str, str]] = []
    for row in rows:
        if row_is_sample(row):
            excluded.append(row)
        else:
            kept.append(row)
    return kept, excluded


def row_is_sample(row: dict[str, str]) -> bool:
    keys = ("database", "name", "namespace", "datasource", "table", "tableName", "_source")
    for key in keys:
        value = row.get(key) or row.get(key.upper()) or row.get(key.lower())
        if value and _is_sample_identifier(value):
            return True
    if len(row) == 1:
        only = next(iter(row.values()))
        if _is_sample_identifier(only):
            return True
    return False


def parse_rows(payload: Any) -> list[dict[str, str]]:
    if payload is None:
        return []
    if not isinstance(payload, dict):
        raise ValueError("response was not a JSON object")
    data = payload.get("data", payload.get("rows"))
    if isinstance(data, dict):
        data = data.get("rows", data.get("data"))
    headers = payload.get("headers", payload.get("columns"))
    if data is None:
        raise ValueError("response had no data field")
    if not isinstance(data, list):
        raise ValueError("data was not a list")
    rows: list[dict[str, str]] = []
    for item in data:
        if isinstance(item, dict):
            rows.append({str(key): _cell(value) for key, value in item.items()})
            continue
        if isinstance(item, list):
            names = _header_names(headers, len(item))
            rows.append({name: _cell(value) for name, value in zip(names, item)})
            continue
        raise ValueError("row was not an object or array")
    return rows


def _header_names(headers: Any, width: int) -> list[str]:
    if isinstance(headers, list) and len(headers) == width:
        return [str(header) for header in headers]
    return [f"column_{index + 1}" for index in range(width)]


def _interpret(response: HttpResponse, statement: str, kind: str) -> QueryResult:
    if response.status == 0:
        return QueryResult(
            "unreachable",
            response.error or "Zetaris unreachable",
            statement=statement,
        )
    if response.status in (401, 403):
        return QueryResult(
            "unauthorized",
            f"Zetaris refused the query: HTTP {response.status}",
            http_status=response.status,
            statement=statement,
        )
    if response.status != 200:
        detail = f"Zetaris query failed: HTTP {response.status} {scrub(response.raw_text)}"
        if response.status == 400 and "not allowed" in (response.raw_text or "").lower():
            detail += (
                " Check that ZETARIS_ORG_ID is the numeric organisation id and that "
                "ZETARIS_API_KEY was created under Management → API Tokens."
            )
        return QueryResult(
            "error",
            detail,
            http_status=response.status,
            statement=statement,
        )
    try:
        rows = parse_rows(response.body)
    except ValueError as error:
        return QueryResult(
            "unrecognized",
            f"Zetaris returned a response this adapter does not parse: {error}",
            http_status=200,
            statement=statement,
        )
    if kind == "probe" and not _is_select_one(rows):
        return QueryResult(
            "unrecognized",
            "SELECT 1 did not return the documented row [['1']].",
            rows=rows,
            http_status=200,
            statement=statement,
        )
    return QueryResult(
        "ok",
        f"{len(rows)} row(s).",
        rows=rows,
        http_status=200,
        statement=statement,
    )


def _is_select_one(rows: list[dict[str, str]]) -> bool:
    if len(rows) != 1 or len(rows[0]) != 1:
        return False
    return next(iter(rows[0].values())) == "1"


def _is_sample_identifier(value: str) -> bool:
    token = value.strip().split(".", 1)[0]
    return token.lower() in SAMPLE_DATABASES or bool(_SAMPLE_NAME.match(token))


def _tag(rows: list[dict[str, str]], statement: str) -> list[dict[str, str]]:
    return [{**row, "_statement": statement} for row in rows]


def _cell(value: Any) -> str:
    if value is None:
        return ""
    text = str(value)
    if len(text) > 500:
        return text[:500] + "…"
    return text


def _sum_duration(left: float | None, right: float | None) -> float | None:
    if left is None and right is None:
        return None
    return round((left or 0) + (right or 0), 1)
