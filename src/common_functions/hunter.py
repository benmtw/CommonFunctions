"""Hunter.io client and cache-first helper functions.

The module provides:
- a thin Hunter HTTP client,
- cache wrappers around frequently used Hunter endpoints,
- a high-level helper that accepts either a domain or an email and returns
  normalized result payloads.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import os
from typing import Any, Protocol
from urllib import parse, request

from .cloudflare_kv import CloudflareKVConfig, CloudflareKVStore


HUNTER_BASE_URL = "https://api.hunter.io/v2"


class CacheStore(Protocol):
    """Minimal key/value cache contract used by Hunter wrappers."""

    def get(self, key: str) -> dict[str, Any] | None:
        """Return cached payload for key, or None if not found."""

    def set(self, key: str, value: dict[str, Any]) -> None:
        """Persist payload for key."""


class HunterClient:
    """Lightweight Hunter.io API client.

    The client is intentionally minimal and returns raw decoded JSON responses
    from Hunter endpoints so callers can preserve full payload fidelity.
    """

    def __init__(self, api_key: str, timeout_seconds: int = 20) -> None:
        api_key = api_key.strip()
        if not api_key:
            raise ValueError("Hunter API key is required.")
        self._api_key = api_key
        self._timeout_seconds = timeout_seconds

    @classmethod
    def from_env(cls) -> "HunterClient":
        """Build a client from ``HUNTER_API_KEY``.

        Returns:
            Configured :class:`HunterClient`.

        Raises:
            ValueError: If ``HUNTER_API_KEY`` is missing/blank.
        """
        api_key = os.getenv("HUNTER_API_KEY", "")
        if not api_key.strip():
            raise ValueError("Missing required env var: HUNTER_API_KEY")
        return cls(api_key=api_key)

    def domain_search(self, domain: str, limit: int | None = None) -> dict[str, Any]:
        """Call Hunter ``/domain-search``.

        Args:
            domain: Domain to search.
            limit: Optional result limit passed through to Hunter.

        Returns:
            Raw Hunter JSON response as a dictionary.
        """
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
        """Call Hunter ``/email-finder``.

        Args:
            domain: Company domain.
            first_name: Contact first name.
            last_name: Contact last name.
            company: Optional company name hint.

        Returns:
            Raw Hunter JSON response as a dictionary.
        """
        params: dict[str, str] = {
            "domain": domain,
            "first_name": first_name,
            "last_name": last_name,
            "api_key": self._api_key,
        }
        if company:
            params["company"] = company
        return self._get("/email-finder", params)

    def email_verifier(self, email: str) -> dict[str, Any]:
        """Call Hunter ``/email-verifier`` for a single email address.

        Args:
            email: Email address to verify.

        Returns:
            Raw Hunter JSON response containing status/result details.
        """
        params: dict[str, str] = {"email": email, "api_key": self._api_key}
        return self._get("/email-verifier", params)

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
    """Return Hunter domain-search data with optional cache lookup.

    Cache key format:
        ``hunter:domain-search:{normalized_domain}``

    Args:
        domain: Domain to search.
        hunter_client: Configured Hunter client.
        cache_store: Optional cache backend implementing :class:`CacheStore`.
        ttl_hours: Cache TTL in hours (default 30 days).

    Returns:
        Hunter domain-search response payload.
    """
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


def get_email_verification_cached(
    *,
    email: str,
    hunter_client: HunterClient,
    cache_store: CacheStore | None = None,
    ttl_hours: int = 24 * 30,
) -> dict[str, Any]:
    """Return Hunter email-verification data with optional caching.

    Cache key format:
        ``hunter:email-verifier:{normalized_email}``

    Args:
        email: Email address to verify.
        hunter_client: Configured Hunter client.
        cache_store: Optional cache backend implementing :class:`CacheStore`.
        ttl_hours: Cache TTL in hours (default 30 days).

    Returns:
        Hunter email-verifier response payload.
    """
    normalized = email.strip().lower()
    cache_key = f"hunter:email-verifier:{normalized}"
    now = datetime.now(tz=timezone.utc)

    if cache_store is not None:
        cached = cache_store.get(cache_key)
        if cached and not _is_stale(cached, now):
            return cached["result"]

    result = hunter_client.email_verifier(normalized)
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


def _normalize_domain_or_email(value: str) -> tuple[str, str]:
    normalized = value.strip().lower()
    if not normalized:
        raise ValueError("A non-empty domain or email is required.")
    if "@" in normalized:
        local, domain = normalized.split("@", 1)
        if not local or not domain or "." not in domain:
            raise ValueError("Invalid email format.")
        if domain.startswith(".") or domain.endswith("."):
            raise ValueError("Invalid email format.")
        return "email", f"{local}@{domain}"
    if "." not in normalized:
        raise ValueError("Invalid domain format.")
    if normalized.startswith(".") or normalized.endswith("."):
        raise ValueError("Invalid domain format.")
    return "domain", normalized


def _extract_first_email_from_domain_search(payload: dict[str, Any]) -> str | None:
    data = payload.get("data")
    if not isinstance(data, dict):
        return None
    emails = data.get("emails")
    if not isinstance(emails, list):
        return None
    for entry in emails:
        if not isinstance(entry, dict):
            continue
        value = entry.get("value")
        if isinstance(value, str) and value.strip():
            return value.strip().lower()
    return None


def get_domain_or_email_info_cached(
    *,
    domain_or_email: str,
    hunter_client: HunterClient,
    cache_store: CacheStore | None = None,
    ttl_hours: int = 24 * 30,
) -> dict[str, Any]:
    """Return normalized domain/email intelligence with cache support.

    Input behavior:
    - If ``domain_or_email`` is an email, verifies that exact email.
    - If ``domain_or_email`` is a domain, runs domain search and, when
      available, verifies the first discovered email value.

    The combined result is also cached under:
        ``hunter:domain-email-info:{input_type}:{normalized_value}``

    Args:
        domain_or_email: Domain (``example.com``) or email
            (``person@example.com``).
        hunter_client: Configured Hunter client.
        cache_store: Optional cache backend implementing :class:`CacheStore`.
        ttl_hours: Cache TTL in hours (default 30 days).

    Returns:
        A dictionary with normalized input metadata and nested Hunter payloads.

    Raises:
        ValueError: If input is empty or not a valid domain/email format.
    """
    input_type, normalized = _normalize_domain_or_email(domain_or_email)
    cache_key = f"hunter:domain-email-info:{input_type}:{normalized}"
    now = datetime.now(tz=timezone.utc)

    if cache_store is not None:
        cached = cache_store.get(cache_key)
        if cached and not _is_stale(cached, now):
            return cached["result"]

    if input_type == "email":
        email = normalized
        domain = email.split("@", 1)[1]
        verification = get_email_verification_cached(
            email=email,
            hunter_client=hunter_client,
            cache_store=cache_store,
            ttl_hours=ttl_hours,
        )
        result = {
            "input": domain_or_email,
            "input_type": "email",
            "domain": domain,
            "email": email,
            "email_verification": verification,
            "domain_search": None,
        }
    else:
        domain = normalized
        domain_search = get_domain_search_cached(
            domain=domain,
            hunter_client=hunter_client,
            cache_store=cache_store,
            ttl_hours=ttl_hours,
        )
        email = _extract_first_email_from_domain_search(domain_search)
        verification = None
        if email is not None:
            verification = get_email_verification_cached(
                email=email,
                hunter_client=hunter_client,
                cache_store=cache_store,
                ttl_hours=ttl_hours,
            )
        result = {
            "input": domain_or_email,
            "input_type": "domain",
            "domain": domain,
            "email": email,
            "email_verification": verification,
            "domain_search": domain_search,
        }

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
