"""Live Meta tests are opt-in and are the only tests allowed to leave the machine.

They never run in the normal suite: ``pyproject.toml`` deselects the ``live_meta`` marker, and
every test here is additionally skipped unless ``WAZI_LIVE_META=1`` and the credentials exist.
"""

from __future__ import annotations

import os

import pytest


@pytest.fixture(autouse=True)
def _offline_guard():
    """Override the offline guard from tests/conftest.py: live tests need the network."""
    yield


def require_env(*names: str) -> dict[str, str]:
    if os.environ.get("WAZI_LIVE_META") != "1":
        pytest.skip("live Meta tests are opt-in: set WAZI_LIVE_META=1")
    values = {name: os.environ.get(name, "").strip() for name in names}
    missing = [name for name, value in values.items() if not value]
    if missing:
        pytest.skip(f"missing environment variables: {', '.join(missing)}")
    return values
