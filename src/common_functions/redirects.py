"""Domain redirect detection with configurable fetch strategies.

Provides :func:`check_redirect` to detect whether a domain redirects to
another domain, using local or remote (Scrape.do) fetch strategies.
Optionally verifies page content against organisation metadata via an
OpenAI-compatible LLM.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
import ssl
import urllib.request
import urllib.error
from typing import Any, Literal, Required, TypedDict
from urllib.parse import urlparse


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


class OrgInfo(TypedDict, total=False):
    """Organisation metadata for content verification.

    Attributes:
        name: Organisation name (required).
        postcode: Organisation postcode (optional).
        context: Description of what the organisation is (required).
    """

    name: Required[str]
    postcode: str
    context: Required[str]


RedirectStrategy = Literal["local_direct", "remote_direct", "remote_headless"]


@dataclass
class _FetchResult:
    """Internal container for fetch strategy results.

    Attributes:
        final_url: The URL after all redirects resolved.
        status_code: The initial HTTP status code (before redirects).
        redirect_chain: Ordered list of URLs visited (original through final).
        content: Page content (HTML for local, markdown for remote).
        redirects: Whether the domain redirected to a different URL.
    """

    final_url: str
    status_code: int
    redirect_chain: list[str]
    content: str
    redirects: bool


_MAX_REDIRECTS = 10


class _RedirectTracker(urllib.request.HTTPRedirectHandler):
    """Custom redirect handler that records each hop."""

    def __init__(self) -> None:
        self.history: list[tuple[int, str]] = []

    def redirect_request(
        self, req, fp, code, msg, headers, newurl
    ) -> urllib.request.Request | None:
        if len(self.history) >= _MAX_REDIRECTS:
            raise urllib.error.URLError(
                f"Too many redirects (>{_MAX_REDIRECTS})"
            )
        self.history.append((code, newurl))
        return urllib.request.Request(newurl)


def _fetch_local_direct(
    domain: str, verify_ssl: bool, timeout_seconds: int
) -> _FetchResult:
    """Fetch a domain using stdlib urllib, tracking redirects.

    Args:
        domain: Normalized domain name (no scheme).
        verify_ssl: Whether to verify SSL certificates.
        timeout_seconds: Connection timeout in seconds.

    Returns:
        :class:`_FetchResult` with HTML content.

    Raises:
        urllib.error.URLError: On DNS, connection, or SSL errors.
        socket.timeout: On connection timeout.
    """
    url = f"https://{domain}"
    tracker = _RedirectTracker()

    if not verify_ssl:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        https_handler = urllib.request.HTTPSHandler(context=ctx)
        opener = urllib.request.build_opener(tracker, https_handler)
    else:
        opener = urllib.request.build_opener(tracker)

    req = urllib.request.Request(url)

    with opener.open(req, timeout=timeout_seconds) as resp:
        content = resp.read().decode("utf-8", errors="replace")
        final_url = resp.url

    chain = [url] + [u for _, u in tracker.history]
    first_status = tracker.history[0][0] if tracker.history else 200
    redirects = urlparse(url).netloc != urlparse(final_url).netloc

    return _FetchResult(
        final_url=final_url,
        status_code=first_status,
        redirect_chain=chain,
        content=content,
        redirects=redirects,
    )


def _normalize_domain(domain: str) -> str:
    """Strip, lowercase, and validate a domain string.

    Args:
        domain: Raw domain input.

    Returns:
        Cleaned domain string.

    Raises:
        ValueError: If domain is empty or contains whitespace.
    """
    domain = domain.strip().lower()
    if not domain:
        raise ValueError("Domain must not be empty.")
    if any(c.isspace() for c in domain):
        raise ValueError(f"Invalid domain (contains whitespace): {domain!r}")
    return domain
