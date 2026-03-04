"""Email helper utilities used across projects."""

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
    """Load known free mailbox provider domains from package data."""
    return _DEFAULT_FREE_PROVIDER_DOMAINS | _read_domain_file("free_provider_domains.txt")


@lru_cache(maxsize=1)
def get_disposable_domains() -> set[str]:
    """Load known disposable mailbox provider domains from package data."""
    return _DEFAULT_DISPOSABLE_DOMAINS | _read_domain_file("disposable_domains.txt")


def is_personalized_email(email: str) -> bool:
    """Return True when the local-part appears to represent a person."""
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


def is_free_provider_email(email: str) -> bool:
    """Return True for common personal/free mailbox providers."""
    parsed = _split_email(email)
    if parsed is None:
        return False
    _local, domain = parsed
    return _domain_in_set(domain, get_free_provider_domains())


def is_disposable_email(email: str) -> bool:
    """Return True for known disposable/temporary email providers."""
    parsed = _split_email(email)
    if parsed is None:
        return False
    _local, domain = parsed
    return _domain_in_set(domain, get_disposable_domains())
