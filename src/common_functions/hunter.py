"""Hunter.io helpers with optional Cloudflare KV caching."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import os
from typing import Any, Protocol
from urllib import error, parse, request


HUNTER_BASE_URL = "https://api.hunter.io/v2"


class CacheStore(Protocol):
    """Minimal key/value cache contract used by Hunter helpers."""

    def get(self, key: str) -> dict[str, Any] | None:
        """Return cached payload for key, or None if not found."""

    def set(self, key: str, value: dict[str, Any]) -> None:
        """Persist payload for key."""


@dataclass(frozen=True)
class CloudflareKVConfig:
    """Configuration required for Cloudflare KV REST operations."""

    account_id: str
    namespace_id: str
    api_token: str

    @classmethod
    def from_env(cls) -> "CloudflareKVConfig":
        account_id = os.getenv("CF_ACCOUNT_ID", "").strip()
        namespace_id = os.getenv("CF_KV_NAMESPACE_ID", "").strip()
        api_token = os.getenv("CF_API_TOKEN", "").strip()
        missing = [
            name
            for name, value in (
                ("CF_ACCOUNT_ID", account_id),
                ("CF_KV_NAMESPACE_ID", namespace_id),
                ("CF_API_TOKEN", api_token),
            )
            if not value
        ]
        if missing:
            raise ValueError(f"Missing required Cloudflare env vars: {', '.join(missing)}")
        return cls(
            account_id=account_id,
            namespace_id=namespace_id,
            api_token=api_token,
        )


class CloudflareKVStore:
    """Cloudflare KV-backed cache implementation."""

    def __init__(self, config: CloudflareKVConfig, timeout_seconds: int = 15) -> None:
        self._config = config
        self._timeout_seconds = timeout_seconds

    def _key_url(self, key: str) -> str:
        encoded_key = parse.quote(key, safe="")
        return (
            "https://api.cloudflare.com/client/v4/accounts/"
            f"{self._config.account_id}/storage/kv/namespaces/"
            f"{self._config.namespace_id}/values/{encoded_key}"
        )

    def get(self, key: str) -> dict[str, Any] | None:
        req = request.Request(
            self._key_url(key),
            method="GET",
            headers={
                "Authorization": f"Bearer {self._config.api_token}",
            },
        )
        try:
            with request.urlopen(req, timeout=self._timeout_seconds) as resp:
                payload = resp.read().decode("utf-8")
        except error.HTTPError as exc:
            if exc.code == 404:
                return None
            raise
        if not payload:
            return None
        return json.loads(payload)

    def set(self, key: str, value: dict[str, Any]) -> None:
        body = json.dumps(value, separators=(",", ":")).encode("utf-8")
        req = request.Request(
            self._key_url(key),
            method="PUT",
            data=body,
            headers={
                "Authorization": f"Bearer {self._config.api_token}",
                "Content-Type": "application/json",
            },
        )
        with request.urlopen(req, timeout=self._timeout_seconds):
            return


class HunterClient:
    """Lightweight Hunter.io API client."""

    def __init__(self, api_key: str, timeout_seconds: int = 20) -> None:
        api_key = api_key.strip()
        if not api_key:
            raise ValueError("Hunter API key is required.")
        self._api_key = api_key
        self._timeout_seconds = timeout_seconds

    @classmethod
    def from_env(cls) -> "HunterClient":
        api_key = os.getenv("HUNTER_API_KEY", "")
        if not api_key.strip():
            raise ValueError("Missing required env var: HUNTER_API_KEY")
        return cls(api_key=api_key)

    def domain_search(self, domain: str, limit: int | None = None) -> dict[str, Any]:
        params: dict[str, str] = {"domain": domain, "api_key": self._api_key}
        if limit is not None:
            params["limit"] = str(limit)
        return self._get("/domain-search", params)

    def email_finder(
        self,
        *,
        domain: str,
        first_name: str,
        last_name: str,
        company: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, str] = {
            "domain": domain,
            "first_name": first_name,
            "last_name": last_name,
            "api_key": self._api_key,
        }
        if company:
            params["company"] = company
        return self._get("/email-finder", params)

    def _get(self, path: str, params: dict[str, str]) -> dict[str, Any]:
        query = parse.urlencode(params)
        url = f"{HUNTER_BASE_URL}{path}?{query}"
        req = request.Request(url, method="GET")
        with request.urlopen(req, timeout=self._timeout_seconds) as resp:
            payload = resp.read().decode("utf-8")
        return json.loads(payload)


def _is_stale(record: dict[str, Any], now: datetime) -> bool:
    expires_at = record.get("expires_at")
    if not isinstance(expires_at, str):
        return True
    try:
        expiry = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
    except ValueError:
        return True
    return now >= expiry


def get_domain_search_cached(
    *,
    domain: str,
    hunter_client: HunterClient,
    cache_store: CacheStore | None = None,
    ttl_hours: int = 24 * 30,
) -> dict[str, Any]:
    """Cache-first wrapper for Hunter domain search results."""
    normalized = domain.strip().lower()
    cache_key = f"hunter:domain-search:{normalized}"
    now = datetime.now(tz=timezone.utc)

    if cache_store is not None:
        cached = cache_store.get(cache_key)
        if cached and not _is_stale(cached, now):
            return cached["result"]

    result = hunter_client.domain_search(normalized)
    expires = now + timedelta(hours=ttl_hours)
    to_store = {
        "source": "hunter.io",
        "retrieved_at": now.isoformat().replace("+00:00", "Z"),
        "expires_at": expires.isoformat().replace("+00:00", "Z"),
        "result": result,
    }
    if cache_store is not None:
        cache_store.set(cache_key, to_store)
    return result
