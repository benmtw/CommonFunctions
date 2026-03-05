"""Email/domain classification helpers.

This module provides lightweight heuristics for:
- identifying role-based vs. person-like mailbox local parts,
- classifying addresses that use common free mailbox providers,
- classifying addresses that use disposable/temporary providers.

Data sources are package-local text files under ``common_functions/data`` plus
small built-in defaults so the helpers still work if package data is absent.
"""

from __future__ import annotations

from functools import lru_cache
from importlib import resources
import re

_ROLE_BASED_LOCAL_PARTS = {
    "admin",
    "billing",
    "careers",
    "contact",
    "enquiries",
    "finance",
    "hello",
    "help",
    "hr",
    "info",
    "jobs",
    "marketing",
    "noreply",
    "no-reply",
    "office",
    "press",
    "sales",
    "support",
    "team",
}

_DEFAULT_FREE_PROVIDER_DOMAINS = {
    "aol.com",
    "gmail.com",
    "googlemail.com",
    "hotmail.com",
    "icloud.com",
    "live.com",
    "outlook.com",
    "proton.me",
    "protonmail.com",
    "yahoo.com",
}

_DEFAULT_DISPOSABLE_DOMAINS = {
    "10minutemail.com",
    "discard.email",
    "guerrillamail.com",
    "maildrop.cc",
    "mailinator.com",
    "temp-mail.org",
    "tempmail.com",
    "yopmail.com",
}


def _split_email(email: str) -> tuple[str, str] | None:
    if not isinstance(email, str):
        return None

    normalized = email.strip().lower()
    if normalized.count("@") != 1:
        return None

    local, domain = normalized.split("@", 1)
    if not local or not domain:
        return None
    if "." not in domain:
        return None
    if domain.startswith(".") or domain.endswith("."):
        return None
    return local, domain


def _normalize_domain(domain: str) -> str | None:
    if not isinstance(domain, str):
        return None

    normalized = domain.strip().lower()
    if not normalized:
        return None
    if "@" in normalized:
        return None
    if "." not in normalized:
        return None
    if normalized.startswith(".") or normalized.endswith("."):
        return None
    if ".." in normalized:
        return None
    return normalized


def _domain_in_set(domain: str, domains: set[str]) -> bool:
    if domain in domains:
        return True
    parts = domain.split(".")
    for i in range(1, len(parts) - 1):
        candidate = ".".join(parts[i:])
        if candidate in domains:
            return True
    return False


def _read_domain_file(filename: str) -> set[str]:
    try:
        text = resources.files("common_functions").joinpath("data", filename).read_text(
            encoding="utf-8"
        )
    except FileNotFoundError:
        return set()

    parsed: set[str] = set()
    for line in text.splitlines():
        line = line.strip().lower()
        if not line or line.startswith("#"):
            continue
        parsed.add(line)
    return parsed


@lru_cache(maxsize=1)
def get_free_provider_domains() -> set[str]:
    """Return known free mailbox provider domains.

    Returns:
        A lowercased set of domains (for example ``gmail.com``), including
        built-in defaults and optional values from
        ``data/free_provider_domains.txt``.
    """
    return _DEFAULT_FREE_PROVIDER_DOMAINS | _read_domain_file("free_provider_domains.txt")


@lru_cache(maxsize=1)
def get_disposable_domains() -> set[str]:
    """Return known disposable/temporary mailbox provider domains.

    Returns:
        A lowercased set of domains, including built-in defaults and values
        loaded from ``data/disposable_domains.txt``.
    """
    return _DEFAULT_DISPOSABLE_DOMAINS | _read_domain_file("disposable_domains.txt")


def is_personalized_email(email: str) -> bool:
    """Heuristically detect whether an email looks person-specific.

    The check is intentionally simple and fast. It rejects obvious role-based
    local parts such as ``info`` and ``support``, as well as numeric-only and
    malformed values.

    Args:
        email: Email address to classify.

    Returns:
        ``True`` when the local part looks person-like, else ``False``.
    """
    parsed = _split_email(email)
    if parsed is None:
        return False

    local, _domain = parsed
    base_local = local.split("+", 1)[0]
    if not base_local:
        return False

    if base_local in _ROLE_BASED_LOCAL_PARTS:
        return False

    for role in _ROLE_BASED_LOCAL_PARTS:
        if (
            base_local.startswith(f"{role}.")
            or base_local.startswith(f"{role}_")
            or base_local.startswith(f"{role}-")
        ):
            return False

    if base_local.isdigit():
        return False
    if len(base_local) < 2:
        return False
    if re.search(r"[a-z]", base_local) is None:
        return False
    return True


def is_free_provider_domain(domain_or_email: str) -> bool:
    """Return whether a domain/email belongs to a known free provider.

    Supports subdomains through suffix matching, so
    ``user@mail.gmx.com`` can match ``gmx.com`` in the provider set.

    Args:
        domain_or_email: Domain (for example ``gmail.com``) or email address
            (for example ``person@gmail.com``) to classify.

    Returns:
        ``True`` if the domain is in the free-provider dataset, else ``False``.
    """
    parsed = _split_email(domain_or_email)
    if parsed is not None:
        _local, domain = parsed
        return _domain_in_set(domain, get_free_provider_domains())

    domain = _normalize_domain(domain_or_email)
    if domain is None:
        return False
    return _domain_in_set(domain, get_free_provider_domains())


def is_free_provider_email(email: str) -> bool:
    """Backward-compatible wrapper for free-provider classification by email.

    Prefer :func:`is_free_provider_domain` for new code.
    """
    return is_free_provider_domain(email)


def is_disposable_domain(domain_or_email: str) -> bool:
    """Return whether a domain/email belongs to a known disposable provider.

    Supports subdomain suffix matching against the disposable dataset.

    Args:
        domain_or_email: Domain (for example ``mailinator.com``) or email
            address (for example ``test@mailinator.com``) to classify.

    Returns:
        ``True`` if the domain is in the disposable-domain dataset, else
        ``False``.
    """
    parsed = _split_email(domain_or_email)
    if parsed is not None:
        _local, domain = parsed
        return _domain_in_set(domain, get_disposable_domains())

    domain = _normalize_domain(domain_or_email)
    if domain is None:
        return False
    return _domain_in_set(domain, get_disposable_domains())


def is_disposable_email(email: str) -> bool:
    """Backward-compatible wrapper for disposable-provider classification.

    Prefer :func:`is_disposable_domain` for new code.
    """
    return is_disposable_domain(email)
