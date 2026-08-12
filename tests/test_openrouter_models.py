"""
tests/test_openrouter_models.py

Tests for OpenRouter models dashboard caching and AI-only shell.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import openrouter_models as orm
from shared import Mode


def _model(model_id, name=None, prompt="0.000001", completion="0.000002"):
    return {
        "id": model_id,
        "canonical_slug": model_id,
        "name": name or model_id,
        "description": f"Summary for {model_id}",
        "context_length": 128000,
        "pricing": {"prompt": prompt, "completion": completion},
        "created": 1700000000,
    }


_TEST_MODEL_IDS = (
    "a/model-1", "a/model-2", "b/new-1", "b/new-2",
    "openai/gpt-x", "openai/gpt-x:free", "google/gemma", "google/gemma:free",
    "meta/llama", "anthropic/claude",
)


@pytest.fixture
def clean_cache_keys():
    """Remove dashboard/detail keys used by these tests."""
    g_c = orm.g_c
    g_c.delete(orm.DASHBOARD_CACHE_KEY)
    for mid in _TEST_MODEL_IDS:
        g_c.delete(orm._detail_key(mid))
    yield
    g_c.delete(orm.DASHBOARD_CACHE_KEY)
    for mid in _TEST_MODEL_IDS:
        g_c.delete(orm._detail_key(mid))


def test_shell_empty_when_not_ai_report():
    with patch.object(orm, "MODE", Mode.LINUX_REPORT):
        assert orm.get_openrouter_models_shell_html() == ""


def test_shell_present_for_ai_report():
    with patch.object(orm, "MODE", Mode.AI_REPORT):
        html = orm.get_openrouter_models_shell_html()
        assert "or-models-inner" in html
        assert "Loading models" in html


def test_refresh_caches_details_and_dashboard(clean_cache_keys):
    top = [_model("a/model-1", "Model One"), _model("a/model-2", "Model Two")]
    newest = [_model("b/new-1", "New One"), _model("b/new-2", "New Two")]

    def fake_sorted(sort):
        return top if sort == "top-weekly" else newest

    rankings = {
        "a/model-1": 5_000_000_000,
        "a/model-2": 1_000_000_000,
    }

    with patch.object(orm, "_fetch_models_sorted", side_effect=fake_sorted) as fetch_models, \
         patch.object(orm, "_fetch_weekly_token_totals", return_value=rankings) as fetch_rank, \
         patch.object(orm, "get_lock") as get_lock:
        lock = MagicMock()
        lock.__enter__ = MagicMock(return_value=lock)
        lock.__exit__ = MagicMock(return_value=False)
        get_lock.return_value = lock

        payload1 = orm.get_openrouter_models_payload()
        assert fetch_models.call_count == 2
        assert fetch_rank.call_count == 1
        assert len(payload1["top_weekly"]) == 2
        assert payload1["top_weekly"][0]["name"] == "Model One"
        assert payload1["top_weekly"][0]["weekly_tokens"] == 5_000_000_000
        assert payload1["top_weekly"][0]["pricing_prompt"] == "0.000001"
        assert payload1["newest"][0]["id"] == "b/new-1"
        assert payload1["last_fetch"] != "Unknown"

        # Second call should use dashboard cache (no network)
        payload2 = orm.get_openrouter_models_payload()
        assert fetch_models.call_count == 2
        assert fetch_rank.call_count == 1
        assert payload2["top_weekly"][0]["id"] == "a/model-1"

        # Detail key survives independently
        detail = orm.g_c.get(orm._detail_key("a/model-1"))
        assert detail is not None
        assert detail["description"].startswith("Summary")


def test_dashboard_miss_refreshes_once(clean_cache_keys):
    top = [_model(f"a/model-{i}") for i in range(10)]
    newest = [_model(f"b/new-{i}") for i in range(10)]

    with patch.object(orm, "_fetch_models_sorted", side_effect=lambda sort: top if sort == "top-weekly" else newest), \
         patch.object(orm, "_fetch_weekly_token_totals", return_value={}), \
         patch.object(orm, "get_lock") as get_lock:
        lock = MagicMock()
        lock.__enter__ = MagicMock(return_value=lock)
        lock.__exit__ = MagicMock(return_value=False)
        get_lock.return_value = lock

        payload = orm.get_openrouter_models_payload()
        assert len(payload["top_weekly"]) == orm.LIST_LIMIT
        assert len(payload["newest"]) == orm.LIST_LIMIT


def test_normalize_model_requires_id():
    assert orm._normalize_model({"name": "x"}) is None
    norm = orm._normalize_model(_model("x/y", "XY"))
    assert norm["url"] == "https://openrouter.ai/x/y"
    assert norm["context_length"] == 128000


def test_dedupe_prefer_free_replaces_paid_keeps_order():
    models = [
        _model("openai/gpt-x", "GPT X"),
        _model("google/gemma", "Gemma"),
        _model("openai/gpt-x:free", "GPT X Free"),
        _model("meta/llama", "Llama"),
        _model("google/gemma:free", "Gemma Free"),
    ]
    result = orm._dedupe_prefer_free(models, limit=8)
    ids = [m["id"] for m in result]
    assert ids == ["openai/gpt-x:free", "google/gemma:free", "meta/llama"]


def test_dedupe_prefer_free_respects_limit():
    models = [_model(f"a/model-{i}") for i in range(10)]
    result = orm._dedupe_prefer_free(models, limit=3)
    assert [m["id"] for m in result] == ["a/model-0", "a/model-1", "a/model-2"]


def test_tokens_match_paid_rankings_to_free_list_entry(clean_cache_keys):
    top = [
        _model("openai/gpt-x", "GPT X"),
        _model("openai/gpt-x:free", "GPT X Free"),
        _model("anthropic/claude", "Claude"),
    ]
    newest = [_model("b/new-1", "New One")]
    rankings = {
        "openai/gpt-x": 4_000_000_000,
        "openai/gpt-x:free": 1_000_000_000,
        "anthropic/claude": 500_000_000,
    }

    with patch.object(orm, "_fetch_models_sorted", side_effect=lambda sort: top if sort == "top-weekly" else newest), \
         patch.object(orm, "_fetch_weekly_token_totals", return_value=rankings), \
         patch.object(orm, "get_lock") as get_lock:
        lock = MagicMock()
        lock.__enter__ = MagicMock(return_value=lock)
        lock.__exit__ = MagicMock(return_value=False)
        get_lock.return_value = lock

        payload = orm.get_openrouter_models_payload()
        top_ids = [m["id"] for m in payload["top_weekly"]]
        assert top_ids == ["openai/gpt-x:free", "anthropic/claude"]
        assert payload["top_weekly"][0]["weekly_tokens"] == 5_000_000_000
        assert payload["top_weekly"][1]["weekly_tokens"] == 500_000_000


def test_lookup_weekly_tokens_sums_family_variants():
    model = {"id": "openai/gpt-x:free", "canonical_slug": "openai/gpt-x"}
    weekly = {"openai/gpt-x": 100, "openai/gpt-x:free": 50, "other/model": 9}
    assert orm._lookup_weekly_tokens(model, weekly) == 150
    assert orm._lookup_weekly_tokens({"id": "missing/model"}, weekly) is None
