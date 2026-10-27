"""Configuration tests."""

import json
from pathlib import Path

from agent.config import load_settings, normalize_nightshift_base_url, parse_sources

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent


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
            "ZETARIS_BASE_URL": "https://zetaris.example",
            "ZETARIS_ORG_ID": "7",
            "ZETARIS_ORG_SLUG": "example-org-slug",
            "ZETARIS_API_KEY": "super-secret-key",
            "ZETARIS_PASSWORD": "super-secret-password",
            "METERLESS_ENABLED": "true",
            "METERLESS_BASE_URL": "http://127.0.0.1:8088/v1/chat/completions",
            "METERLESS_API_KEY": "super-secret-token",
            "METERLESS_MODEL": "gpt-oss-20b-nvidia-test",
            "SCOUT_SIGNING_KEY": "signing-secret",
            "ZETARIS_SOURCES": "planning.permits|Permit rows",
            "ZETARIS_QUERY_LIMIT": "500",
        },
        load_env_file=False,
    )
    assert settings.zetaris_configured
    assert settings.public_view()["zetaris_base_url"] == "https://zetaris.example"
    assert "example-org-slug" not in json.dumps(settings.public_view())
    assert settings.nightshift_configured
    assert settings.meterless_base_url == "http://127.0.0.1:8088/v1"
    assert settings.public_view()["nvidia_label_is_not_proof"] is True
    assert settings.public_view()["nightshift_api_key_set"] is True
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
            "ZETARIS_BASE_URL": "https://zetaris.example/org/login",
            "ZETARIS_ORG_ID": "abc",
            "ZETARIS_API_KEY": "present",
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
        "DJANGO_DEBUG": "true",
        "DJANGO_ALLOWED_HOSTS": "127.0.0.1,localhost",
        "CORS_ALLOWED_ORIGINS": "http://127.0.0.1:5173,http://localhost:5173",
        "ZETARIS_QUERY_LIMIT": "25",
        "ZETARIS_TIMEOUT_SECONDS": "30",
        "METERLESS_ENABLED": "false",
        "METERLESS_APP_ID": "jirani-intelligence",
        "METERLESS_TIMEOUT_SECONDS": "60",
    }
    for line in (BACKEND_ROOT / ".env.example").read_text().splitlines():
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        assert value == allowed.get(key, "")


def test_metadata_records_sponsor_roles():
    metadata = json.loads((REPO_ROOT / "metadata.json").read_text())
    readme = (REPO_ROOT / "README.md").read_text()
    role = (
        "Zetaris is the data access and query layer that retrieves records "
        "from registered data sources for the agent."
    )
    assert metadata["architecture"]["zetaris"]["role"] == role
    assert role in readme
    assert metadata["architecture"]["meterless_nightshift"]["role"] == "AI provider"
    assert metadata["architecture"]["meterless_nightshift"]["programmatic_api_on_web"] is False
    assert metadata["architecture"]["meterless_nightshift"]["intended_model_label"] == (
        "GPT-OSS 20B (NVIDIA cloud)"
    )
    assert metadata["architecture"]["meterless_nightshift"]["live_inference_verified"] is False
    assert metadata["architecture"]["meterless_engine"]["name"] == "H-MEM"
    assert metadata["architecture"]["scout_intent"]["name"] == "Scout Intent"
    assert metadata["metadata_schema"]["official_json_schema_published"] is False
    assert metadata["nvidia"]["integrated"] is False
    zetaris = metadata["architecture"]["zetaris"]
    assert zetaris["route"] == "POST {ZETARIS_BASE_URL}/api/proxy/sql-editor/sqls/run-query"
    assert zetaris["direct_rest_used"] is False
    assert zetaris["verified"]["select_1"] is True
    assert zetaris["verified"]["ny_taxi_taxi_trips"] is True
