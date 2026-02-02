import json
import os
import time
from typing import Any, Dict, Optional


CACHE_DIR = ".cache_upas"
CACHE_FILE = os.path.join(CACHE_DIR, "upas_cache.json")


def _now() -> float:
    return time.time()


def load_cache() -> Dict[str, Any]:
    if not os.path.exists(CACHE_FILE):
        return {}
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_cache(cache: Dict[str, Any]) -> None:
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


def get_cached(url: str, ttl_seconds: int = 120) -> Optional[Dict[str, Any]]:
    cache = load_cache()
    item = cache.get(url)
    if not item:
        return None
    ts = item.get("_ts", 0)
    if (_now() - ts) > ttl_seconds:
        return None
    return item.get("data")


def set_cached(url: str, data: Dict[str, Any]) -> None:
    cache = load_cache()
    cache[url] = {"_ts": _now(), "data": data}
    save_cache(cache)
