"""Live Zetaris smoke test.

This file calls the configured direct REST API. Mocked unit tests do not
satisfy it. A skip or a failure here means the live connection was not verified.
"""

import pytest

from agent.config import load_settings
from integrations.zetaris import SELECT_1, TAXI_TRIPS_SAMPLE, ZetarisClient

pytestmark = pytest.mark.live


def test_live_select_1_and_ny_taxi_trips():
    settings = load_settings()
    missing = []
    if not settings.zetaris_api_key:
        missing.append("ZETARIS_API_KEY is empty")
    if not settings.zetaris_rest_url:
        missing.append(
            "ZETARIS_REST_URL is unset. The organisation slug is not an API endpoint"
        )
    if missing:
        pytest.fail(
            "LIVE Zetaris smoke test did not connect. "
            + "; ".join(missing)
            + f". SELECT 1 and {TAXI_TRIPS_SAMPLE} were not sent."
        )

    client = ZetarisClient(settings)
    probe = client.probe()
    assert probe.status == "ok", probe.detail
    assert probe.statement == SELECT_1
    assert probe.rows and "1" in probe.rows[0].values()

    sample = client.query_taxi_trips_sample()
    assert sample.status == "ok", sample.detail
    assert sample.statement == TAXI_TRIPS_SAMPLE
    assert sample.rows, "The live taxi_trips query returned no rows."
