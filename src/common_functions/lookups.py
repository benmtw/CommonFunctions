"""Intent-first lookup helpers.

This module is the recommended public entrypoint for lookup workflows. It
keeps call sites stable and readable by focusing on *intent* (lookup a domain
or lookup an email), while delegating provider-specific behavior to existing
lower-level helpers.

Design goals:
- Prefer one clear function per caller intent.
- Preserve backward compatibility with existing provider-specific helpers.
- Allow source selection (`ratings` vs `hunter`) without changing call shape.
"""

from __future__ import annotations

from typing import Any, Literal

from .domain_ratings import (
    CacheStore as RatingsCacheStore,
    CloudflareD1Config,
    CloudflareD1DomainRatingsStore,
    DomainRatingsStore,
    MillionVerifierClient,
    _get_domain_rating_info_cached,
)
from .hunter import (
    CacheStore as HunterCacheStore,
    HunterClient,
    get_domain_or_email_info_cached,
)


DomainLookupSource = Literal["ratings", "hunter"]
EmailLookupSource = Literal["hunter", "ratings"]


def _resolve_ratings_store(d1_store: DomainRatingsStore | None) -> DomainRatingsStore:
    """Return an explicit ratings store or build a default D1-backed store.

    If ``d1_store`` is provided, it is returned as-is. Otherwise, this helper
    attempts to construct a Cloudflare D1 store from environment variables via
    :class:`CloudflareD1Config`.
    """
    if d1_store is not None:
        return d1_store
    return CloudflareD1DomainRatingsStore(CloudflareD1Config.from_env())


def lookup_domain(
    *,
    domain: str,
    source: DomainLookupSource = "ratings",
    d1_store: DomainRatingsStore | None = None,
    kv_cache: RatingsCacheStore | None = None,
    millionverifier_client: MillionVerifierClient | None = None,
    fallback_email: str | None = None,
    hunter_client: HunterClient | None = None,
    hunter_cache_store: HunterCacheStore | None = None,
    ttl_hours: int = 24 * 30,
) -> dict[str, Any]:
    """Lookup domain intelligence using an intent-first API.

    This function wraps current domain lookup implementations behind one
    stable interface. The ``source`` parameter selects the backend strategy:

    - ``source="ratings"``:
      Uses merged domain ratings via an internal ratings helper,
      with optional KV caching and optional MillionVerifier email-driven
      fallback on domain misses.
    - ``source="hunter"``:
      Uses Hunter domain/email intelligence via
      :func:`get_domain_or_email_info_cached`.

    Args:
        domain: Domain to look up, for example ``example.com``.
        source: Backend source strategy:
            - ``"ratings"``: merged-domain records (D1/KV + optional fallback)
            - ``"hunter"``: Hunter lookup path
        d1_store: Optional ratings storage backend. If omitted for
            ``source="ratings"``, a Cloudflare D1-backed store is initialized
            from ``CF_ACCOUNT_ID``, ``CF_D1_DATABASE_ID``, and ``CF_API_TOKEN``.
        kv_cache: Optional cache backend used by ratings lookups.
        millionverifier_client: Optional client for live fallback on ratings
            misses.
        fallback_email: Optional email used only for ratings fallback. Must
            belong to the same domain.
        hunter_client: Hunter API client. Required when ``source="hunter"``.
        hunter_cache_store: Optional cache backend used by Hunter helper.
        ttl_hours: Cache TTL in hours for the selected backend helper.

    Returns:
        A dictionary payload returned by the chosen backend helper. The shape is
        backend-specific:
        - ratings source returns domain-rating fields such as ``verdict`` and
          ``naming_format``.
        - hunter source returns Hunter-oriented fields such as
          ``domain_search`` and ``email_verification``.

    Raises:
        ValueError: If required dependencies for the selected source are
            missing, if D1 env vars are missing when auto-initializing the
            ratings store, or if an unsupported source is requested.

    Example:
        Use merged ratings as the default source::

            result = lookup_domain(
                domain="example.com",
                source="ratings",
                d1_store=ratings_store,
                kv_cache=kv_cache,
            )
    """
    if source == "ratings":
        resolved_store = _resolve_ratings_store(d1_store)
        return _get_domain_rating_info_cached(
            domain=domain,
            d1_store=resolved_store,
            kv_cache=kv_cache,
            millionverifier_client=millionverifier_client,
            fallback_email=fallback_email,
            ttl_hours=ttl_hours,
        )

    if source == "hunter":
        if hunter_client is None:
            raise ValueError("hunter_client is required when source='hunter'.")
        return get_domain_or_email_info_cached(
            domain_or_email=domain,
            hunter_client=hunter_client,
            cache_store=hunter_cache_store,
            ttl_hours=ttl_hours,
        )

    raise ValueError(f"Unsupported domain lookup source: {source}")


def lookup_email(
    *,
    email: str,
    source: EmailLookupSource = "hunter",
    hunter_client: HunterClient | None = None,
    hunter_cache_store: HunterCacheStore | None = None,
    d1_store: DomainRatingsStore | None = None,
    kv_cache: RatingsCacheStore | None = None,
    millionverifier_client: MillionVerifierClient | None = None,
    ttl_hours: int = 24 * 30,
) -> dict[str, Any]:
    """Lookup email intelligence using an intent-first API.

    This function routes email lookups to one of two backends:

    - ``source="hunter"``:
      Verifies/searches using Hunter unified domain/email helper behavior.
    - ``source="ratings"``:
      Resolves the email domain and performs ratings lookup, enabling
      email-driven fallback when the domain is missing from stored ratings.

    Args:
        email: Email address to look up, for example ``person@example.com``.
        source: Backend source strategy:
            - ``"hunter"``: verify/search via Hunter helper path.
            - ``"ratings"``: domain-ratings lookup + fallback using this email.
        hunter_client: Hunter API client. Required for ``source="hunter"``.
        hunter_cache_store: Optional cache backend for Hunter lookups.
        d1_store: Optional ratings storage backend. If omitted for
            ``source="ratings"``, a Cloudflare D1-backed store is initialized
            from ``CF_ACCOUNT_ID``, ``CF_D1_DATABASE_ID``, and ``CF_API_TOKEN``.
        kv_cache: Optional cache backend for ratings lookups.
        millionverifier_client: Optional fallback client for ratings lookups.
        ttl_hours: Cache TTL in hours for the selected backend helper.

    Returns:
        A dictionary payload returned by the selected backend helper.

    Raises:
        ValueError: If required dependencies for the selected source are
            missing, if D1 env vars are missing when auto-initializing the
            ratings store, if email format is invalid for ratings lookup, or if
            an unsupported source is requested.

    Example:
        Lookup using ratings backend with email-driven fallback::

            result = lookup_email(
                email="person@example.com",
                source="ratings",
                d1_store=ratings_store,
                millionverifier_client=mv_client,
            )
    """
    if source == "hunter":
        if hunter_client is None:
            raise ValueError("hunter_client is required when source='hunter'.")
        return get_domain_or_email_info_cached(
            domain_or_email=email,
            hunter_client=hunter_client,
            cache_store=hunter_cache_store,
            ttl_hours=ttl_hours,
        )

    if source == "ratings":
        resolved_store = _resolve_ratings_store(d1_store)
        domain = email.strip().lower().split("@", 1)
        if len(domain) != 2:
            raise ValueError("Invalid email format.")
        return _get_domain_rating_info_cached(
            domain=domain[1],
            d1_store=resolved_store,
            kv_cache=kv_cache,
            millionverifier_client=millionverifier_client,
            fallback_email=email,
            ttl_hours=ttl_hours,
        )

    raise ValueError(f"Unsupported email lookup source: {source}")
