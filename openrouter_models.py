"""
openrouter_models.py

OpenRouter top-weekly / newest models dashboard for AI Report.
One dashboard blob in g_c: newest refreshes on a 2h/6h Eastern schedule,
top-weekly on EXPIRE_DAY. Per-model details last 100 days.
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
    EXPIRE_DAY,
    EXPIRE_HOUR,
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

DETAIL_TTL = 86400 * 100  # 100 days
LIST_LIMIT = 8
REQUEST_TIMEOUT = 30
BUSINESS_HOUR_START = 8
BUSINESS_HOUR_END = 17


def _detail_key(model_id: str) -> str:
    return f"{DETAIL_CACHE_PREFIX}{model_id}"


def _newest_cache_ttl(now=None) -> int:
    """Return newest-list TTL: 2h during Eastern 8-5, else 6h."""
    local = (now or datetime.now(TZ)).astimezone(TZ)
    if BUSINESS_HOUR_START <= local.hour < BUSINESS_HOUR_END:
        return 2 * EXPIRE_HOUR
    return 6 * EXPIRE_HOUR


def _is_stale(last_fetch, ttl_seconds: int, now=None) -> bool:
    if last_fetch is None:
        return True
    now = now or datetime.now(TZ)
    if getattr(last_fetch, "tzinfo", None) is None:
        last_fetch = last_fetch.replace(tzinfo=TZ)
    return (now - last_fetch).total_seconds() >= ttl_seconds


def _normalize_dashboard(blob) -> Optional[Dict[str, Any]]:
    """Ignore old/partial blobs; require the one-key refresh fields."""
    if not isinstance(blob, dict):
        return None
    required = ("newest_ids", "newest_last_fetch", "top_weekly_ids", "top_last_fetch")
    if any(key not in blob for key in required):
        return None
    return blob


def _empty_dashboard() -> Dict[str, Any]:
    return {
        "newest_ids": [],
        "newest_last_fetch": None,
        "top_weekly_ids": [],
        "weekly_tokens": {},
        "top_last_fetch": None,
    }


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
        params={"sort": sort, "output_modalities": "text"},
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


def _refresh_list(sort: str) -> List[Dict[str, Any]]:
    models = _fetch_models_sorted(sort)
    _store_model_details(models)
    return _dedupe_prefer_free(models, LIST_LIMIT)


def _apply_newest(dashboard: Dict[str, Any]) -> Dict[str, Any]:
    try:
        models = _refresh_list("newest")
    except requests.RequestException as exc:
        g_logger.error(f"Failed to fetch OpenRouter newest models: {exc}")
        return dashboard
    dashboard["newest_ids"] = [m["id"] for m in models if m.get("id")]
    dashboard["newest_last_fetch"] = datetime.now(TZ)
    return dashboard


def _apply_top_weekly(dashboard: Dict[str, Any]) -> Dict[str, Any]:
    try:
        models = _refresh_list("top-weekly")
    except requests.RequestException as exc:
        g_logger.error(f"Failed to fetch OpenRouter top-weekly models: {exc}")
        return dashboard

    weekly_tokens: Dict[str, int] = {}
    try:
        weekly_tokens = _fetch_weekly_token_totals()
    except requests.RequestException as exc:
        g_logger.warning(f"Failed to fetch OpenRouter rankings-daily: {exc}")

    token_map: Dict[str, int] = {}
    for model in models:
        model_id = model.get("id")
        if not model_id:
            continue
        normalized = _normalize_model(model) or {"id": model_id}
        tokens = _lookup_weekly_tokens(normalized, weekly_tokens)
        if tokens is not None:
            token_map[model_id] = tokens

    dashboard["top_weekly_ids"] = [m["id"] for m in models if m.get("id")]
    dashboard["weekly_tokens"] = token_map
    dashboard["top_last_fetch"] = datetime.now(TZ)
    return dashboard


def get_dashboard() -> Optional[Dict[str, Any]]:
    """Return dashboard, refreshing only the stale list(s) under one lock."""
    cached = _normalize_dashboard(g_c.get(DASHBOARD_CACHE_KEY))
    now = datetime.now(TZ)
    newest_stale = cached is None or _is_stale(cached.get("newest_last_fetch"), _newest_cache_ttl(now), now)
    top_stale = cached is None or _is_stale(cached.get("top_last_fetch"), EXPIRE_DAY, now)
    if cached is not None and not newest_stale and not top_stale:
        return cached

    with get_lock(LOCK_NAME):
        cached = _normalize_dashboard(g_c.get(DASHBOARD_CACHE_KEY)) or _empty_dashboard()
        now = datetime.now(TZ)
        changed = False
        if _is_stale(cached.get("newest_last_fetch"), _newest_cache_ttl(now), now):
            cached = _apply_newest(cached)
            changed = True
        if _is_stale(cached.get("top_last_fetch"), EXPIRE_DAY, now):
            cached = _apply_top_weekly(cached)
            changed = True
        if changed:
            g_c.put(DASHBOARD_CACHE_KEY, cached, timeout=EXPIRE_DAY)
        return cached


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
        "last_fetch": format_last_updated(dashboard.get("newest_last_fetch")),
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
            response = jsonify(payload)
            response.headers['Cache-Control'] = f'public, max-age={EXPIRE_HOUR}'
            return response

    API.add_resource(OpenRouterModelsResource, "/api/openrouter/models")
