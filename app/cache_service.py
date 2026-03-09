from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from collections import defaultdict
from functools import lru_cache
from typing import Any

import redis

logger = logging.getLogger(__name__)


class CacheUnavailableError(RuntimeError):
    pass


def _to_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _domain_env_key(domain: str) -> str:
    clean = "".join(ch if ch.isalnum() else "_" for ch in (domain or "").strip().upper())
    return clean


class RedisCacheService:
    DEFAULT_TTLS: dict[str, int] = {
        "safety": 600,
        "rag_retrieval": 60,
        "guest_summary": 60,
        "partner_normalize": 180,
        "mongo_generate": 120,
        "mongo_improve": 120,
        "mongo_guard": 120,
        "formatting_output": 45,
        "admin_mongo_generate": 120,
    }

    def __init__(self) -> None:
        self.enabled = _to_bool(os.getenv("REDIS_CACHE_ENABLED"), default=True)
        self.log_hits = _to_bool(os.getenv("CACHE_LOG_HITS"), default=True)
        self.schema_version = (os.getenv("CACHE_SCHEMA_VERSION") or "v1").strip() or "v1"
        self.redis_url = (os.getenv("REDIS_URL") or "redis://localhost:6379").strip()

        raw_fail_closed = os.getenv(
            "CACHE_FAIL_CLOSED_DOMAINS_ADMIN",
            "safety,mongo_generate,mongo_improve,mongo_guard,admin_mongo_generate",
        )
        self.fail_closed_domains_admin = {
            d.strip() for d in (raw_fail_closed or "").split(",") if d.strip()
        }

        self.failure_threshold = max(int(os.getenv("CACHE_FAILURE_THRESHOLD", "3")), 1)
        self.cooldown_sec = max(int(os.getenv("CACHE_COOLDOWN_SEC", "15")), 1)
        self._failure_count = 0
        self._cooldown_until = 0.0
        self._metrics: dict[str, int] = defaultdict(int)
        self._client: redis.Redis | None = None

        if not self.enabled:
            logger.info("Redis cache disabled via REDIS_CACHE_ENABLED")
            return

        try:
            self._client = redis.from_url(self.redis_url, decode_responses=True)
            self._client.ping()
            logger.info("Redis cache connected")
        except Exception:
            logger.exception("Redis cache unavailable at init; cache will fallback")
            self._client = None

    def _metric(self, metric: str, role: str, domain: str) -> None:
        self._metrics[f"{metric}:{role}:{domain}"] += 1

    def _is_admin_fail_closed(self, role: str, domain: str) -> bool:
        return role == "admin" and domain in self.fail_closed_domains_admin

    def _on_cache_error(self, role: str, domain: str, message: str) -> None:
        self._failure_count += 1
        self._metric("error", role, domain)
        logger.warning("Cache error role=%s domain=%s err=%s", role, domain, message)
        if self._failure_count >= self.failure_threshold:
            self._cooldown_until = time.time() + self.cooldown_sec
            self._failure_count = 0
            logger.warning("Cache cooldown enabled for %ss", self.cooldown_sec)

    def _ensure_available(self, role: str, domain: str) -> bool:
        if not self.enabled or self._client is None:
            if self._is_admin_fail_closed(role, domain):
                raise CacheUnavailableError("Cache unavailable for admin-sensitive domain")
            return False

        if time.time() < self._cooldown_until:
            if self._is_admin_fail_closed(role, domain):
                raise CacheUnavailableError("Cache cooldown active for admin-sensitive domain")
            return False

        return True

    def domain_enabled(self, domain: str) -> bool:
        domain = (domain or "").strip()
        if not domain:
            return False
        env_key = f"CACHE_DOMAIN_ENABLED_{_domain_env_key(domain)}"
        return _to_bool(os.getenv(env_key), default=True)

    def get_ttl(self, domain: str) -> int:
        domain = (domain or "").strip()
        env_key = f"CACHE_TTL_{_domain_env_key(domain)}_SEC"
        raw = os.getenv(env_key)
        if raw:
            try:
                return max(int(raw), 1)
            except Exception:
                logger.warning("Invalid %s=%r; using default", env_key, raw)
        return self.DEFAULT_TTLS.get(domain, 60)

    @staticmethod
    def canonical_payload(payload: Any) -> str:
        return json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))

    def make_key(self, role: str, domain: str, payload: Any) -> str:
        role_norm = (role or "unknown").strip().lower()
        domain_norm = (domain or "unknown").strip().lower()
        canonical = self.canonical_payload(payload)
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        return f"{self.schema_version}:{role_norm}:{domain_norm}:{digest}"

    def get_json(self, key: str, *, role: str, domain: str) -> Any | None:
        role_norm = (role or "").strip().lower() or "unknown"
        domain_norm = (domain or "").strip().lower()

        if not self.domain_enabled(domain_norm):
            self._metric("disabled", role_norm, domain_norm)
            return None

        if not self._ensure_available(role_norm, domain_norm):
            self._metric("bypass", role_norm, domain_norm)
            return None

        try:
            raw = self._client.get(key) if self._client is not None else None
            if raw is None:
                self._metric("miss", role_norm, domain_norm)
                return None
            self._metric("hit", role_norm, domain_norm)
            if self.log_hits:
                logger.info("Redis cache hit role=%s domain=%s key=%s", role_norm, domain_norm, key)
                print(f"Redis cache hit | role={role_norm} domain={domain_norm} key={key}")
            return json.loads(raw)
        except Exception as exc:
            self._on_cache_error(role_norm, domain_norm, str(exc))
            if self._is_admin_fail_closed(role_norm, domain_norm):
                raise CacheUnavailableError("Cache read failed for admin-sensitive domain") from exc
            return None

    def set_json(self, key: str, value: Any, ttl_sec: int, *, role: str, domain: str) -> bool:
        role_norm = (role or "").strip().lower() or "unknown"
        domain_norm = (domain or "").strip().lower()

        if not self.domain_enabled(domain_norm):
            self._metric("disabled", role_norm, domain_norm)
            return False

        if not self._ensure_available(role_norm, domain_norm):
            self._metric("bypass", role_norm, domain_norm)
            return False

        ttl = max(int(ttl_sec), 1)
        try:
            if self._client is None:
                return False
            self._client.setex(key, ttl, json.dumps(value, ensure_ascii=True, separators=(",", ":")))
            self._metric("set", role_norm, domain_norm)
            return True
        except Exception as exc:
            self._on_cache_error(role_norm, domain_norm, str(exc))
            if self._is_admin_fail_closed(role_norm, domain_norm):
                raise CacheUnavailableError("Cache write failed for admin-sensitive domain") from exc
            return False

    def delete_pattern(self, pattern: str, *, role: str = "admin", domain: str = "cache_admin") -> int:
        role_norm = (role or "").strip().lower() or "unknown"
        domain_norm = (domain or "").strip().lower()
        if not self._ensure_available(role_norm, domain_norm):
            return 0

        deleted = 0
        try:
            if self._client is None:
                return 0
            for key in self._client.scan_iter(match=pattern, count=500):
                deleted += int(self._client.delete(key))
            self._metric("delete", role_norm, domain_norm)
            return deleted
        except Exception as exc:
            self._on_cache_error(role_norm, domain_norm, str(exc))
            if self._is_admin_fail_closed(role_norm, domain_norm):
                raise CacheUnavailableError("Cache delete failed for admin-sensitive domain") from exc
            return deleted

    def metrics_snapshot(self) -> dict[str, int]:
        return dict(self._metrics)


@lru_cache(maxsize=1)
def get_cache_service() -> RedisCacheService:
    return RedisCacheService()
