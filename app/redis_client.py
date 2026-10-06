"""
Shared Redis connection and small cache helpers.

Env var:  REDIS_URL  (default redis://localhost:6379/0)

Every helper fails open: if Redis is down, the app keeps working and just
skips the cache (the glossary reads from the database, translations call the LLM).
"""
import json
import logging
import os
from typing import Any, Optional

import redis

logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

_client = redis.Redis.from_url(
    REDIS_URL,
    decode_responses=True,
    socket_connect_timeout=1,
    socket_timeout=1,
    protocol=2,
)


def cache_get_json(key: str) -> Optional[Any]:
    try:
        raw = _client.get(key)
        return json.loads(raw) if raw is not None else None
    except (redis.RedisError, ValueError) as exc:
        logger.warning("redis get failed for %s: %s", key, exc)
        return None


def cache_set_json(key: str, value: Any, ttl_seconds: int) -> None:
    try:
        _client.set(key, json.dumps(value, ensure_ascii=False), ex=ttl_seconds)
    except redis.RedisError as exc:
        logger.warning("redis set failed for %s: %s", key, exc)


def cache_delete(*keys: str) -> None:
    try:
        _client.delete(*keys)
    except redis.RedisError as exc:
        logger.warning("redis delete failed: %s", exc)


def get_version(name: str) -> int:
    """Version counter used inside cache keys. Bumping it retires old entries."""
    try:
        return int(_client.get(f"version:{name}") or 0)
    except (redis.RedisError, ValueError):
        return 0


def bump_version(name: str) -> None:
    try:
        _client.incr(f"version:{name}")
    except redis.RedisError as exc:
        logger.warning("redis incr failed for %s: %s", name, exc)
