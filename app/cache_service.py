"""
cache_service.py
----------------
Unified cache layer: Redis when available, in-memory dict as fallback.

Usage:
    from cache_service import cache
    cache.set("key", value, ttl=5)
    value = cache.get("key")
    cache.delete("key")
    cache.flush()
    stats = cache.stats()
"""

import os
import json
import time
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ── Try to connect Redis ───────────────────────────────────────────────────────
try:
    import redis as redis_lib
    _redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    _redis = redis_lib.from_url(_redis_url, decode_responses=True, socket_connect_timeout=2)
    _redis.ping()
    _USE_REDIS = True
    logger.info(f"Redis cache connected: {_redis_url}")
except Exception as exc:
    _redis = None
    _USE_REDIS = False
    logger.warning(f"Redis unavailable ({exc}) — using in-memory cache fallback")


# ── In-memory fallback ─────────────────────────────────────────────────────────
import threading
_mem_store: dict = {}
_mem_lock  = threading.Lock()
_hits   = 0
_misses = 0


class CacheService:
    """
    Thin wrapper: Redis if available, in-memory dict otherwise.
    Values are JSON-serialized so they survive Redis round-trips.
    """

    def get(self, key: str) -> Optional[Any]:
        global _hits, _misses
        if _USE_REDIS:
            try:
                raw = _redis.get(key)
                if raw is not None:
                    _hits += 1
                    return json.loads(raw)
                _misses += 1
                return None
            except Exception as exc:
                logger.warning(f"Redis GET failed for '{key}': {exc}")

        # in-memory fallback
        with _mem_lock:
            entry = _mem_store.get(key)
            if entry and time.time() < entry["exp"]:
                _hits += 1
                return entry["val"]
            if entry:
                del _mem_store[key]
            _misses += 1
            return None

    def set(self, key: str, value: Any, ttl: int = 5) -> bool:
        if _USE_REDIS:
            try:
                _redis.setex(key, ttl, json.dumps(value))
                return True
            except Exception as exc:
                logger.warning(f"Redis SET failed for '{key}': {exc}")

        with _mem_lock:
            _mem_store[key] = {"val": value, "exp": time.time() + ttl}
        return True

    def delete(self, key: str) -> bool:
        if _USE_REDIS:
            try:
                _redis.delete(key)
                return True
            except Exception as exc:
                logger.warning(f"Redis DEL failed for '{key}': {exc}")

        with _mem_lock:
            _mem_store.pop(key, None)
        return True

    def flush(self) -> bool:
        """Clear all cache entries."""
        if _USE_REDIS:
            try:
                _redis.flushdb()
                return True
            except Exception as exc:
                logger.warning(f"Redis FLUSH failed: {exc}")

        with _mem_lock:
            _mem_store.clear()
        return True

    def stats(self) -> dict:
        total = _hits + _misses
        hit_rate = round(_hits / total * 100, 1) if total else 0
        base = {
            "backend":  "redis" if _USE_REDIS else "memory",
            "hits":     _hits,
            "misses":   _misses,
            "hit_rate": hit_rate,
        }
        if _USE_REDIS:
            try:
                info = _redis.info("memory")
                base["redis_used_memory"] = info.get("used_memory_human", "?")
                base["redis_keys"]        = _redis.dbsize()
            except Exception:
                pass
        else:
            with _mem_lock:
                live = sum(1 for v in _mem_store.values() if time.time() < v["exp"])
            base["mem_keys_total"] = len(_mem_store)
            base["mem_keys_live"]  = live
        return base


# Singleton
cache = CacheService()
