"""
NEXUS Metrics Agent — Pulls real engagement data from Meta Graph API.

Available now (instagram_basic):
  - likes, comments per post

Available after token rotation with instagram_manage_insights:
  - reach, impressions, saves, profile_visits
"""
import os
import json
import requests
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv

load_dotenv()

TOKEN   = os.getenv("META_PAGE_ACCESS_TOKEN")
IG_ID   = os.getenv("META_IG_USER_ID")
BASE    = os.path.dirname(os.path.abspath(__file__))
LOG     = os.path.join(BASE, "posts_log.json")
CACHE   = os.path.join(BASE, "metrics_cache.json")


def _fetch_ig_post(ig_id: str) -> dict:
    """Returns basic engagement metrics for one IG post."""
    r = requests.get(
        f"https://graph.facebook.com/v19.0/{ig_id}",
        params={
            "fields": "like_count,comments_count,timestamp,media_type",
            "access_token": TOKEN,
        },
        timeout=10,
    )
    if r.status_code == 200:
        return r.json()
    return {}


def _fetch_ig_insights(ig_id: str) -> dict:
    """
    Returns advanced insights (reach, impressions, saves).
    Requires instagram_manage_insights — returns empty dict if not available yet.
    """
    r = requests.get(
        f"https://graph.facebook.com/v19.0/{ig_id}/insights",
        params={
            "metric": "impressions,reach,saved",
            "access_token": TOKEN,
        },
        timeout=10,
    )
    if r.status_code != 200:
        return {}
    out = {}
    for item in r.json().get("data", []):
        vals = item.get("values", [])
        out[item["name"]] = vals[0]["value"] if vals else 0
    return out


def refresh_metrics() -> dict:
    """Fetch fresh metrics for all logged posts. Saves to metrics_cache.json."""
    try:
        with open(LOG, encoding="utf-8") as f:
            posts = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        posts = []

    def _fetch_post(post: dict) -> dict:
        ig_id = post.get("ig_id", "")
        if not ig_id:
            return {**post, "likes": None, "comments": None,
                    "reach": None, "impressions": None, "saves": None}
        basic    = _fetch_ig_post(ig_id)
        advanced = _fetch_ig_insights(ig_id)
        return {
            "datetime":    post.get("datetime", ""),
            "post_type":   post.get("post_type", ""),
            "model":       post.get("model", ""),
            "ig_id":       ig_id,
            "fb_id":       post.get("fb_id", ""),
            "likes":       basic.get("like_count"),
            "comments":    basic.get("comments_count"),
            "media_type":  basic.get("media_type", "IMAGE"),
            "reach":       advanced.get("reach"),
            "impressions": advanced.get("impressions"),
            "saves":       advanced.get("saved"),
        }

    # Fetch all posts in parallel (15 sequential → 15 concurrent)
    results = [None] * len(posts)
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(_fetch_post, p): i for i, p in enumerate(posts)}
        for future in as_completed(futures):
            results[futures[future]] = future.result()

    cache = {
        "updated":          datetime.now().strftime("%Y-%m-%d %H:%M"),
        "has_insights":     any(r.get("reach") is not None for r in results),
        "posts":            results,
    }

    with open(CACHE, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)

    return cache


def get_cached() -> dict:
    try:
        with open(CACHE, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"updated": None, "has_insights": False, "posts": []}


def get_summary(posts: list) -> dict:
    """Compute per-type engagement averages from a list of post dicts."""
    from collections import defaultdict
    by_type = defaultdict(list)
    for p in posts:
        if p.get("likes") is not None:
            eng = (p.get("likes") or 0) + (p.get("comments") or 0)
            by_type[p["post_type"]].append(eng)

    summary = {}
    for t, vals in by_type.items():
        summary[t] = {
            "count":      len(vals),
            "avg_eng":    round(sum(vals) / len(vals), 1),
            "total_eng":  sum(vals),
            "max_eng":    max(vals),
        }
    return summary


if __name__ == "__main__":
    print("Actualizando métricas desde Meta...")
    data = refresh_metrics()
    print(f"Posts procesados: {len(data['posts'])}")
    print(f"Insights avanzados: {'Sí' if data['has_insights'] else 'No (falta instagram_manage_insights)'}")
    print(f"Cache guardado: {CACHE}")
