"""Zetaris adapter.

Zetaris is the data access and query layer. It retrieves records from registered
data sources for the agent. This module does not invent rows when a call fails,
and it does not treat supplied NY Taxi, TPCDS, or TPCH samples as planning evidence.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from typing import Any

from agent.config import SAMPLE_DATABASES, Settings
from integrations.http import HttpResponse, scrub, urllib_transport

_SAMPLE_NAME = re.compile(
    r"^(ny_taxi|tpcds(_db)?|tpch(_db)?)$",
    re.IGNORECASE,
)


@dataclass
class QueryResult:
    status: str
    detail: str
    rows: list[dict[str, str]] = field(default_factory=list)
    excluded_rows: list[dict[str, str]] = field(default_factory=list)
    http_status: int | None = None
    statement: str = ""

    @property
    def ok(self) -> bool:
        return self.status == "ok"


class ZetarisClient:
    def __init__(self, settings: Settings, transport=urllib_transport) -> None:
        self.settings = settings
        self.transport = transport

    def probe(self) -> QueryResult:
        """Run SELECT 1. Success proves the query path answered; it is not planning evidence."""
        if not self.settings.zetaris_configured:
            return QueryResult("not_configured", self._configuration_detail())
        return self._run("SELECT 1", kind="probe")

    def list_catalog(self) -> QueryResult:
        if not self.settings.zetaris_configured:
            return QueryResult("not_configured", self._configuration_detail())
        databases = self._run("SHOW LIGHTNING DATABASES", kind="catalog")
        datasources = self._run("SHOW DATASOURCES", kind="catalog")
        if not databases.ok and not datasources.ok:
            detail = databases.detail or datasources.detail
            return QueryResult(databases.status, detail, http_status=databases.http_status)
        rows = _tag(databases.rows, "SHOW LIGHTNING DATABASES") + _tag(
            datasources.rows, "SHOW DATASOURCES"
        )
        kept, excluded = split_sample_rows(rows)
        detail = f"{len(kept)} catalog row(s)"
        if excluded:
            detail += f"; {len(excluded)} supplied sample row(s) excluded"
        status = "ok" if databases.ok or datasources.ok else databases.status
        if databases.ok and not datasources.ok:
            detail += f". SHOW DATASOURCES failed: {datasources.detail}"
        if datasources.ok and not databases.ok:
            detail += f". SHOW LIGHTNING DATABASES failed: {databases.detail}"
        return QueryResult(
            status,
            detail,
            rows=kept,
            excluded_rows=excluded,
            statement="catalog",
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
        limit = self.settings.zetaris_query_limit
        for source in self.settings.zetaris_sources:
            statement = f"SELECT * FROM {source.name} LIMIT {limit}"
            result = self._run(statement, kind="records")
            result.rows = [
                {**row, "_source": source.name, "_description": source.description}
                for row in result.rows
            ]
            results.append(result)
        return results

    def _configuration_detail(self) -> str:
        missing = []
        if not self.settings.zetaris_base_url:
            missing.append("ZETARIS_BASE_URL")
        if not self.settings.zetaris_org_id:
            missing.append("ZETARIS_ORG_ID")
        if not (
            self.settings.zetaris_api_key
            or (self.settings.zetaris_username and self.settings.zetaris_password)
        ):
            missing.append("ZETARIS_API_KEY or ZETARIS_USERNAME and ZETARIS_PASSWORD")
        if self.settings.warnings:
            return "Zetaris is not configured. " + " ".join(self.settings.warnings)
        if missing:
            return "Zetaris is not configured. Set " + ", ".join(missing) + "."
        return "Zetaris is not configured."

    def _run(self, statement: str, *, kind: str) -> QueryResult:
        token, token_error = self._token()
        if token_error:
            return token_error
        body: dict[str, Any] = {"sql": statement, "limit": self.settings.zetaris_query_limit}
        if self.settings.zetaris_engine_id:
            body["engineId"] = self.settings.zetaris_engine_id
        response = self.transport(
            "POST",
            self.settings.zetaris_base_url + self.settings.zetaris_query_path,
            {
                "Authorization": f"Bearer {token}",
                "X-Org-ID": self.settings.zetaris_org_id,
                "X-Request-ID": str(uuid.uuid4()),
                "Content-Type": "application/json",
            },
            body,
            self.settings.zetaris_timeout_seconds,
        )
        return _interpret(response, statement, kind)

    def _token(self) -> tuple[str | None, QueryResult | None]:
        if self.settings.zetaris_api_key:
            return self.settings.zetaris_api_key, None
        response = self.transport(
            "POST",
            self.settings.zetaris_base_url + "/api/auth/login",
            {
                "Content-Type": "application/json",
                "X-Request-ID": str(uuid.uuid4()),
            },
            {
                "username": self.settings.zetaris_username,
                "password": self.settings.zetaris_password,
            },
            self.settings.zetaris_timeout_seconds,
        )
        if response.status == 0:
            return None, QueryResult("unreachable", response.error or "Zetaris login unreachable")
        if response.status != 200 or not isinstance(response.body, dict):
            return None, QueryResult(
                "unauthorized",
                f"Zetaris login failed: HTTP {response.status}",
                http_status=response.status or None,
            )
        token = (
            response.body.get("idToken")
            or response.body.get("token")
            or response.body.get("accessToken")
        )
        if not isinstance(token, str) or not token:
            return None, QueryResult(
                "unauthorized",
                "Zetaris login did not return an access token.",
                http_status=response.status,
            )
        return token, None


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


def _is_sample_identifier(value: str) -> bool:
    token = value.strip().split(".", 1)[0]
    return token.lower() in SAMPLE_DATABASES or bool(_SAMPLE_NAME.match(token))


def _tag(rows: list[dict[str, str]], statement: str) -> list[dict[str, str]]:
    return [{**row, "_statement": statement} for row in rows]


def _interpret(response: HttpResponse, statement: str, kind: str) -> QueryResult:
    if response.status == 0:
        return QueryResult("unreachable", response.error or "Zetaris unreachable", statement=statement)
    if response.status in (401, 403):
        return QueryResult(
            "unauthorized",
            f"Zetaris refused the query: HTTP {response.status}",
            http_status=response.status,
            statement=statement,
        )
    if response.status != 200:
        return QueryResult(
            "error",
            f"Zetaris query failed: HTTP {response.status} {scrub(response.raw_text)}",
            http_status=response.status,
            statement=statement,
        )
    if kind == "probe":
        return QueryResult("ok", "SELECT 1 returned HTTP 200.", http_status=200, statement=statement)
    try:
        rows = parse_rows(response.body)
    except ValueError as error:
        return QueryResult(
            "unrecognized",
            f"Zetaris returned a response this adapter does not parse: {error}",
            http_status=200,
            statement=statement,
        )
    return QueryResult(
        "ok",
        f"{len(rows)} row(s) from {statement}",
        rows=rows,
        http_status=200,
        statement=statement,
    )


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
        raise ValueError("response had no data or rows field")
    if not isinstance(data, list):
        raise ValueError("data was not a list")
    rows: list[dict[str, str]] = []
    for item in data:
        if isinstance(item, dict):
            rows.append({str(key): _cell(value) for key, value in item.items()})
            continue
        if isinstance(item, list):
            if not isinstance(headers, list) or len(headers) != len(item):
                raise ValueError("row width did not match headers")
            rows.append({str(header): _cell(value) for header, value in zip(headers, item)})
            continue
        raise ValueError("row was not an object or array")
    return rows


def _cell(value: Any) -> str:
    if value is None:
        return ""
    text = str(value)
    if len(text) > 500:
        return text[:500] + "…"
    return text
