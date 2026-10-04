"""A small JSON cache on top of Redis.

Redis is an optimisation in this project, never a requirement: if it is down, every function here
quietly does nothing (cache misses, limiter falls back to in-process), and after a failure Redis is
skipped for RETRY_AFTER_SECONDS so a dead server costs one error, not one per request.
"""
import json
import logging
import time
from typing import Any, Callable, Optional

import redis

from .config import settings

logger = logging.getLogger(__name__)

RETRY_AFTER_SECONDS = 30
UNAVAILABLE = object()      # returned by call() when it was told to, instead of None, so callers can tell "no Redis" apart

_client: Optional[redis.Redis] = None
_down_until = 0.0


def get_redis() -> Optional[redis.Redis]:
    global _client
    if time.monotonic() < _down_until:
        return None
    if _client is None:
        _client = redis.Redis.from_url(settings.redis_url, decode_responses=True,
                                       socket_connect_timeout=1, socket_timeout=1)
    return _client


def mark_down(error: Exception) -> None:
    global _down_until
    _down_until = time.monotonic() + RETRY_AFTER_SECONDS
    logger.warning("Redis is unavailable (%s); continuing without it for %s seconds", error, RETRY_AFTER_SECONDS)


def call(fn: Callable[[redis.Redis], Any], default: Any = None) -> Any:
    """Run fn(redis_client). If Redis is unavailable, return default instead of raising."""
    client = get_redis()
    if client is None:
        return default
    try:
        return fn(client)
    except redis.RedisError as e:
        mark_down(e)
        return default


def cache_get(key: str) -> Any:
    raw = call(lambda r: r.get(key))
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except ValueError:      # a damaged entry is just a miss
        return None


def cache_set(key: str, value: Any, ttl_seconds: int) -> None:
    call(lambda r: r.set(key, json.dumps(value), ex=ttl_seconds))


def cache_set_many(items: dict[str, Any], ttl_seconds: int) -> None:
    def write(r: redis.Redis) -> None:
        pipe = r.pipeline()
        for key, value in items.items():
            pipe.set(key, json.dumps(value), ex=ttl_seconds)
        pipe.execute()
    call(write)
