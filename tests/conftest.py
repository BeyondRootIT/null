from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _isolate_settings_cache() -> None:
    from cti.config.schema import reset_settings

    reset_settings()
    yield
    reset_settings()
