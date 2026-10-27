"""Live Meterless Nightshift smoke test.

Calls the configured OpenAI-compatible endpoint. Mocked unit tests do not
satisfy it. This never invents an endpoint or model id.
"""

import pytest

from agent.config import load_settings
from integrations.meterless_nightshift import NightshiftClient

pytestmark = pytest.mark.live


def test_live_nightshift_probe_when_enabled():
    settings = load_settings()
    if not settings.meterless_enabled:
        pytest.fail(
            "LIVE Nightshift smoke test did not connect. METERLESS_ENABLED is false. "
            "No chat/completions request was sent."
        )
    missing = settings.nightshift_missing
    if missing:
        pytest.fail(
            "LIVE Nightshift smoke test did not connect. Missing "
            + ", ".join(missing)
            + ". No chat/completions request was sent."
        )

    probe = NightshiftClient(settings).probe()
    assert probe.state == "online", probe.detail
    assert probe.configured_model == settings.meterless_model
