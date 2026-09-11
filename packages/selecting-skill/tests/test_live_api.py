from __future__ import annotations

import pytest


@pytest.mark.live_api
def test_live_openai_classification_is_explicitly_enabled() -> None:
    pytest.skip("Live API tests require explicit REAL_LLM_ENABLED and OPENAI_API_KEY configuration.")
