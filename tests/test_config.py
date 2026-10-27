"""Configuration tests."""

import json
from pathlib import Path

from agent.config import load_settings, normalize_nightshift_base_url, parse_sources

ROOT = Path(__file__).resolve().parents[1]


def test_parse_sources_and_reject_samples_and_unsafe_names():
    sources, warnings = parse_sources(
        "planning.permits|Permit rows;;NY_TAXI.trips|Taxi trips;;bad name|Nope;;lonely"
    )
    assert [source.name for source in sources] == ["planning.permits"]
    assert any("sample" in warning for warning in warnings)
    assert any("unsafe" in warning for warning in warnings)
    assert any("without a description" in warning for warning in warnings)


def test_settings_hide_secrets():
    settings = load_settings(
        {
            "ZETARIS_REST_URL": "http://localhost:8888/api/v1.0",
            "ZETARIS_ORG_ID": "7",
            "ZETARIS_ORG_SLUG": "example-org-slug",
            "ZETARIS_API_KEY": "super-secret-key",
            "ZETARIS_PASSWORD": "super-secret-password",
            "METERLESS_BASE_URL": "http://127.0.0.1:8088/v1/chat/completions",
            "METERLESS_RUNTIME_TOKEN": "super-secret-token",
            "SCOUT_SIGNING_KEY": "signing-secret",
            "ZETARIS_SOURCES": "planning.permits|Permit rows",
            "ZETARIS_QUERY_LIMIT": "500",
        },
        load_env_file=False,
    )
    assert settings.zetaris_configured
    assert settings.zetaris_rest_url == "http://localhost:8888/api/v1.0"
    assert "example-org-slug" not in json.dumps(settings.public_view())
    assert settings.nightshift_configured
    assert settings.meterless_base_url == "http://127.0.0.1:8088/v1"
    assert settings.zetaris_query_limit == 100
    view = settings.public_view()
    blob = json.dumps(view) + repr(settings)
    assert "super-secret-key" not in blob
    assert "super-secret-password" not in blob
    assert "super-secret-token" not in blob
    assert "signing-secret" not in blob
    assert view["registered_sources"] == ["planning.permits"]


def test_incomplete_zetaris_is_not_configured():
    settings = load_settings(
        {
            "ZETARIS_REST_URL": "http://localhost:3000",
            "ZETARIS_ORG_ID": "abc",
            "ZETARIS_ORG_SLUG": "example-org-slug",
        },
        load_env_file=False,
    )
    assert not settings.zetaris_configured
    assert settings.warnings


def test_nightshift_url_normalization():
    assert normalize_nightshift_base_url("http://127.0.0.1:8088") == "http://127.0.0.1:8088/v1"
    assert (
        normalize_nightshift_base_url("http://127.0.0.1:8088/v1/models")
        == "http://127.0.0.1:8088/v1"
    )
    assert normalize_nightshift_base_url("") == ""


def test_env_example_has_no_secret_values():
    allowed = {
        "ZETARIS_QUERY_LIMIT": "25",
        "ZETARIS_TIMEOUT_SECONDS": "30",
        "METERLESS_BASE_URL": "http://127.0.0.1:8088/v1",
        "METERLESS_MODEL": "meterless/auto",
        "METERLESS_APP_ID": "jirani-intelligence",
        "METERLESS_TIMEOUT_SECONDS": "60",
    }
    for line in (ROOT / ".env.example").read_text().splitlines():
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        assert value == allowed.get(key, "")


def test_metadata_records_sponsor_roles():
    metadata = json.loads((ROOT / "metadata.json").read_text())
    readme = (ROOT / "README.md").read_text()
    role = (
        "Zetaris is the data access and query layer that retrieves records "
        "from registered data sources for the agent."
    )
    assert metadata["architecture"]["zetaris"]["role"] == role
    assert role in readme
    assert metadata["architecture"]["meterless_nightshift"]["role"] == "AI provider"
    assert metadata["architecture"]["meterless_engine"]["name"] == "Scout Intent"
    assert metadata["metadata_schema"]["official_json_schema_published"] is False
    assert metadata["nvidia"]["integrated"] is False
    assert "not_verified" in metadata["architecture"]["zetaris"]["integration_status"]
