"""
openrouter_models.py

OpenRouter top-weekly / newest models dashboard for AI Report.
Caches dashboard lists daily and per-model details for 100 days in g_c.
"""

from __future__ import annotations

import os
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import requests
from flask import jsonify
from flask_restful import Resource

from request_utils import format_last_updated
from shared import (
    API,
    MODE,
    Mode,
    TZ,
    USER_AGENT,
    g_c,
    g_logger,
    get_lock,
    limiter,
    dynamic_rate_limit,
)

OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"
OPENROUTER_RANKINGS_URL = "https://openrouter.ai/api/v1/datasets/rankings-daily"
OPENROUTER_MODEL_PAGE = "https://openrouter.ai"

DASHBOARD_CACHE_KEY = "openrouter:models:dashboard"
DETAIL_CACHE_PREFIX = "openrouter:model:detail:"
LOCK_NAME = "openrouter_models_fetch"

DASHBOARD_TTL = 86400  # 1 day
DETAIL_TTL = 86400 * 100  # 100 days
LIST_LIMIT = 8
REQUEST_TIMEOUT = 30


def _detail_key(model_id: str) -> str:
    return f"{DETAIL_CACHE_PREFIX}{model_id}"


def _ranking_base(slug: str) -> str:
    """Strip :variant suffixes (e.g. :free) for ranking/family matching."""
    return slug.split(":")[0] if slug else ""


def _free_dedupe_base(model_id: str) -> str:
    """Base id for free/paid dedupe; only the trailing :free suffix is removed."""
    if model_id.endswith(":free"):
        return model_id[:-5]
    return model_id


def _dedupe_prefer_free(models: List[Dict[str, Any]], limit: int = LIST_LIMIT) -> List[Dict[str, Any]]:
    """Keep first-seen bases; replace a paid entry with :free if it appears later."""
    order: List[str] = []
    chosen: Dict[str, Dict[str, Any]] = {}
    for model in models:
        model_id = model.get("id")
        if not model_id:
            continue
        base = _free_dedupe_base(model_id)
        if base not in chosen:
            order.append(base)
            chosen[base] = model
        elif model_id.endswith(":free"):
            chosen[base] = model
    return [chosen[base] for base in order[:limit]]


def _normalize_model(model: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    model_id = model.get("id")
    if not model_id:
        return None
    pricing = model.get("pricing") or {}
    name = model.get("name") or model_id
    return {
        "id": model_id,
        "canonical_slug": model.get("canonical_slug") or model_id,
        "name": name,
        "description": model.get("description") or "",
        "context_length": model.get("context_length"),
        "pricing_prompt": pricing.get("prompt"),
        "pricing_completion": pricing.get("completion"),
        "created": model.get("created"),
        "url": f"{OPENROUTER_MODEL_PAGE}/{model_id}",
    }


def _fetch_models_sorted(sort: str) -> List[Dict[str, Any]]:
    response = requests.get(
        OPENROUTER_MODELS_URL,
        params={"sort": sort},
        headers={"User-Agent": USER_AGENT},
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    data = response.json().get("data") or []
    return [m for m in data if isinstance(m, dict)]


def _fetch_weekly_token_totals() -> Dict[str, int]:
    """Sum last-7-day token totals per model permaslug from rankings-daily."""
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        g_logger.warning("OPENROUTER_API_KEY not set; skipping rankings-daily token metrics")
        return {}

    end_date = datetime.now(timezone.utc).date() - timedelta(days=1)
    start_date = end_date - timedelta(days=6)
    response = requests.get(
        OPENROUTER_RANKINGS_URL,
        params={
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "period": "day",
        },
        headers={
            "User-Agent": USER_AGENT,
            "Authorization": f"Bearer {api_key}",
        },
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    rows = response.json().get("data") or []
    totals: Dict[str, int] = defaultdict(int)
    for row in rows:
        slug = row.get("model_permaslug")
        if not slug or slug == "other":
            continue
        try:
            totals[slug] += int(row.get("total_tokens") or 0)
        except (TypeError, ValueError):
            continue
    return dict(totals)


def _store_model_details(models: List[Dict[str, Any]]) -> None:
    for model in models:
        details = _normalize_model(model)
        if not details:
            continue
        g_c.put(_detail_key(details["id"]), details, timeout=DETAIL_TTL)


def _lookup_weekly_tokens(model: Dict[str, Any], weekly_tokens: Dict[str, int]) -> Optional[int]:
    """Sum ranking rows whose base matches this model (covers :free / paid siblings)."""
    if not weekly_tokens:
        return None

    bases = set()
    for key in (model.get("id"), model.get("canonical_slug")):
        if key:
            bases.add(_ranking_base(key))
    bases.discard("")
    if not bases:
        return None

    total = 0
    matched = False
    for slug, count in weekly_tokens.items():
        if _ranking_base(slug) in bases:
            total += count
            matched = True
    return total if matched else None


def _refresh_dashboard() -> Optional[Dict[str, Any]]:
    try:
        top_models = _fetch_models_sorted("top-weekly")
        newest_models = _fetch_models_sorted("newest")
    except requests.RequestException as exc:
        g_logger.error(f"Failed to fetch OpenRouter models: {exc}")
        return None

    _store_model_details(top_models)
    _store_model_details(newest_models)

    weekly_tokens: Dict[str, int] = {}
    try:
        weekly_tokens = _fetch_weekly_token_totals()
    except requests.RequestException as exc:
        g_logger.warning(f"Failed to fetch OpenRouter rankings-daily: {exc}")

    top_deduped = _dedupe_prefer_free(top_models, LIST_LIMIT)
    newest_deduped = _dedupe_prefer_free(newest_models, LIST_LIMIT)
    top_ids = [m["id"] for m in top_deduped if m.get("id")]
    newest_ids = [m["id"] for m in newest_deduped if m.get("id")]

    token_map: Dict[str, int] = {}
    for model in top_deduped:
        model_id = model.get("id")
        if not model_id:
            continue
        normalized = _normalize_model(model) or {"id": model_id}
        tokens = _lookup_weekly_tokens(normalized, weekly_tokens)
        if tokens is not None:
            token_map[model_id] = tokens

    dashboard = {
        "top_weekly_ids": top_ids,
        "newest_ids": newest_ids,
        "weekly_tokens": token_map,
        "last_fetch": datetime.now(TZ),
    }
    g_c.put(DASHBOARD_CACHE_KEY, dashboard, timeout=DASHBOARD_TTL)
    return dashboard


def get_dashboard() -> Optional[Dict[str, Any]]:
    """Return cached dashboard, refreshing at most once per day under lock."""
    cached = g_c.get(DASHBOARD_CACHE_KEY)
    if cached is not None:
        return cached

    with get_lock(LOCK_NAME):
        cached = g_c.get(DASHBOARD_CACHE_KEY)
        if cached is not None:
            return cached
        return _refresh_dashboard()


def _hydrate_models(model_ids: List[str], weekly_tokens: Dict[str, int]) -> List[Dict[str, Any]]:
    hydrated: List[Dict[str, Any]] = []
    for model_id in model_ids:
        details = g_c.get(_detail_key(model_id))
        if not details:
            details = {
                "id": model_id,
                "name": model_id,
                "description": "",
                "context_length": None,
                "pricing_prompt": None,
                "pricing_completion": None,
                "url": f"{OPENROUTER_MODEL_PAGE}/{model_id}",
            }
        entry = dict(details)
        tokens = weekly_tokens.get(model_id)
        if tokens is not None:
            entry["weekly_tokens"] = tokens
        hydrated.append(entry)
    return hydrated


def get_openrouter_models_payload() -> Dict[str, Any]:
    """Build API payload: lists hydrated with cached details + last_fetch."""
    dashboard = get_dashboard()
    if not dashboard:
        return {
            "top_weekly": [],
            "newest": [],
            "last_fetch": "Unknown",
            "error": "unavailable",
        }

    weekly_tokens = dashboard.get("weekly_tokens") or {}
    return {
        "top_weekly": _hydrate_models(dashboard.get("top_weekly_ids") or [], weekly_tokens),
        "newest": _hydrate_models(dashboard.get("newest_ids") or [], {}),
        "last_fetch": format_last_updated(dashboard.get("last_fetch")),
    }


def get_openrouter_models_shell_html() -> str:
    """Weather-like loading shell for AI Report only; empty string otherwise."""
    if MODE != Mode.AI_REPORT:
        return ""
    return (
        '<div class="or-models-inner">'
        '<div class="or-models-title">OpenRouter</div>'
        '<div class="or-models-loading">Loading models...</div>'
        "</div>"
    )


def init_openrouter_models_routes(app) -> None:
    """Register GET /api/openrouter/models."""

    class OpenRouterModelsResource(Resource):
        @limiter.limit(dynamic_rate_limit)
        def get(self):
            payload = get_openrouter_models_payload()
            return jsonify(payload)

    API.add_resource(OpenRouterModelsResource, "/api/openrouter/models")
