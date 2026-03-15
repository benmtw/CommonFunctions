"""Domain redirect detection with configurable fetch strategies.

Provides :func:`check_redirect` to detect whether a domain redirects to
another domain, using local or remote (Scrape.do) fetch strategies.
Optionally verifies page content against organisation metadata via an
OpenAI-compatible LLM.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Any, Literal, Required, TypedDict


@dataclass(frozen=True)
class ScrapeDoConfig:
    """Configuration for the Scrape.do scraping API.

    Attributes:
        api_token: Scrape.do API token.
        geo_code: ISO country code for proxy geolocation.
        timeout_seconds: HTTP connection timeout in seconds.
    """

    api_token: str
    geo_code: str = "gb"
    timeout_seconds: int = 30

    @classmethod
    def from_env(cls) -> ScrapeDoConfig:
        """Load Scrape.do config from environment variables.

        Required variables:
            - ``SCRAPE_DO_API_TOKEN``

        Optional variables:
            - ``SCRAPE_DO_GEO_CODE`` (default ``"gb"``)

        Returns:
            Populated :class:`ScrapeDoConfig`.

        Raises:
            ValueError: If ``SCRAPE_DO_API_TOKEN`` is missing or empty.
        """
        api_token = os.getenv("SCRAPE_DO_API_TOKEN", "").strip()
        if not api_token:
            raise ValueError(
                "Missing required env var: SCRAPE_DO_API_TOKEN"
            )
        geo_code = os.getenv("SCRAPE_DO_GEO_CODE", "gb").strip()
        return cls(api_token=api_token, geo_code=geo_code)


@dataclass(frozen=True)
class LlmVerifierConfig:
    """Configuration for the OpenAI-compatible LLM verifier.

    Attributes:
        api_key: API key for the LLM service.
        base_url: Base URL for the OpenAI-compatible API.
        model: Model identifier to use for verification.
    """

    api_key: str
    base_url: str = "https://api.xiaomimimo.com/v1"
    model: str = "mimo-v2-flash"

    @classmethod
    def from_env(cls) -> LlmVerifierConfig:
        """Load LLM verifier config from environment variables.

        Required variables:
            - ``MIMO_API_KEY``

        Optional variables:
            - ``MIMO_BASE_URL`` (default ``"https://api.xiaomimimo.com/v1"``)
            - ``MIMO_MODEL`` (default ``"mimo-v2-flash"``)

        Returns:
            Populated :class:`LlmVerifierConfig`.

        Raises:
            ValueError: If ``MIMO_API_KEY`` is missing or empty.
        """
        api_key = os.getenv("MIMO_API_KEY", "").strip()
        if not api_key:
            raise ValueError("Missing required env var: MIMO_API_KEY")
        base_url = os.getenv(
            "MIMO_BASE_URL", "https://api.xiaomimimo.com/v1"
        ).strip()
        model = os.getenv("MIMO_MODEL", "mimo-v2-flash").strip()
        return cls(api_key=api_key, base_url=base_url, model=model)
