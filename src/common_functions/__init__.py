"""Public API for the common_functions package."""

from .email_utils import (
    get_disposable_domains,
    get_free_provider_domains,
    is_disposable_email,
    is_free_provider_email,
    is_personalized_email,
)

__all__ = [
    "get_free_provider_domains",
    "get_disposable_domains",
    "is_personalized_email",
    "is_disposable_email",
    "is_free_provider_email",
]
