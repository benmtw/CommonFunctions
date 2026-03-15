"""Domain redirect detection with configurable fetch strategies.

Provides :func:`check_redirect` to detect whether a domain redirects to
another domain, using local or remote (Scrape.do) fetch strategies.
Optionally verifies page content against organisation metadata via an
OpenAI-compatible LLM.
"""

from __future__ import annotations

from dataclasses import dataclass
import http.client
import json
import os
import ssl
import urllib.request
import urllib.error
from typing import Any, Literal, Required, TypedDict
from urllib.parse import quote, urlparse


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


def _fetch_remote(
    domain: str, config: ScrapeDoConfig, render: bool
) -> _FetchResult:
    """Fetch a domain via the Scrape.do API.

    Args:
        domain: Normalized domain name (no scheme).
        config: Scrape.do API configuration.
        render: If True, use headless browser rendering.

    Returns:
        :class:`_FetchResult` with markdown content.

    Raises:
        http.client.HTTPException: On connection or protocol errors.
        socket.timeout: On connection timeout.
    """
    url = f"https://{domain}"
    encoded_url = quote(url, safe="")
    render_val = "true" if render else "false"
    path = (
        f"/?token={config.api_token}"
        f"&url={encoded_url}"
        f"&geoCode={config.geo_code}"
        f"&render={render_val}"
        f"&output=markdown"
        f"&transparentResponse=true"
    )

    conn = http.client.HTTPSConnection(
        "api.scrape.do", timeout=config.timeout_seconds
    )
    try:
        conn.request("GET", path)
        resp = conn.getresponse()
        body = resp.read().decode("utf-8", errors="replace")
    finally:
        conn.close()

    target_url = resp.getheader("Scrape.do-Target-Url", url)
    resolved_url = resp.getheader("Scrape.do-Resolved-Url", url)
    initial_status_str = resp.getheader("Scrape.do-Initial-Status-Code", "200")
    initial_status = int(initial_status_str) if initial_status_str.isdigit() else 200

    redirects = target_url != resolved_url

    if redirects:
        chain = [target_url, resolved_url]
    else:
        chain = [target_url]

    return _FetchResult(
        final_url=resolved_url,
        status_code=initial_status,
        redirect_chain=chain,
        content=body,
        redirects=redirects,
    )


_VERIFY_SYSTEM_PROMPT = """You are verifying whether a webpage belongs to a specific organisation.

Organisation: {name}
{postcode_line}Context: {context}

Analyse the page content below and determine if this page belongs to the organisation described above.

Respond with JSON only: {{"verified": true/false, "reason": "brief explanation"}}"""


def _make_openai_client(api_key: str, base_url: str):
    """Create an OpenAI client (lazy import).

    Args:
        api_key: API key for the LLM service.
        base_url: Base URL for the OpenAI-compatible API.

    Returns:
        An ``openai.OpenAI`` client instance.

    Raises:
        ImportError: If the ``openai`` package is not installed.
    """
    try:
        from openai import OpenAI
    except ImportError:
        raise ImportError(
            "The 'openai' package is required for organisation verification. "
            "Install it with: pip install common-functions[redirects]"
        )
    return OpenAI(api_key=api_key, base_url=base_url)


def _verify_org_content(
    content: str, org_info: OrgInfo, config: LlmVerifierConfig
) -> tuple[bool, str]:
    """Verify page content belongs to the expected organisation via LLM.

    Args:
        content: Page content (HTML or markdown).
        org_info: Organisation metadata for verification.
        config: LLM API configuration.

    Returns:
        Tuple of (verified, reason). If the LLM response cannot be parsed,
        returns ``(False, "LLM response could not be parsed")``.
    """
    postcode = org_info.get("postcode", "")
    postcode_line = f"Postcode: {postcode}\n" if postcode else ""

    system_prompt = _VERIFY_SYSTEM_PROMPT.format(
        name=org_info["name"],
        postcode_line=postcode_line,
        context=org_info["context"],
    )

    truncated_content = content[:4000]

    client = _make_openai_client(api_key=config.api_key, base_url=config.base_url)
    completion = client.chat.completions.create(
        model=config.model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": truncated_content},
        ],
        temperature=0.1,
        max_completion_tokens=256,
        response_format={"type": "json_object"},
    )

    raw = completion.choices[0].message.content
    try:
        data = json.loads(raw)
        return bool(data["verified"]), str(data["reason"])
    except (json.JSONDecodeError, KeyError, TypeError):
        return False, "LLM response could not be parsed"


def check_redirect(
    *,
    domain: str,
    strategy: RedirectStrategy = "local_direct",
    scrape_do_config: ScrapeDoConfig | None = None,
    verify_org: OrgInfo | None = None,
    llm_config: LlmVerifierConfig | None = None,
    verify_ssl: bool = True,
    timeout_seconds: int = 20,
) -> dict[str, Any]:
    """Check whether a domain redirects to another domain.

    Fetches the domain using the specified strategy and optionally verifies
    that the page content belongs to a given organisation using an LLM.

    Args:
        domain: The domain to check (e.g. ``"www.example.com"``).
        strategy: Fetch strategy — ``"local_direct"``, ``"remote_direct"``,
            or ``"remote_headless"``.
        scrape_do_config: Configuration for Scrape.do API. Auto-initialized
            from env vars if omitted for a remote strategy.
        verify_org: Optional organisation metadata for LLM content
            verification. Pass ``None`` to skip verification.
        llm_config: Configuration for the LLM verifier. Auto-initialized
            from env vars if omitted when ``verify_org`` is provided.
        verify_ssl: Whether to verify SSL certificates (``local_direct`` only).
        timeout_seconds: Connection timeout in seconds (``local_direct`` only).
            Remote strategies use ``ScrapeDoConfig.timeout_seconds``.

    Returns:
        Dict with keys: ``domain``, ``redirects``, ``final_domain``,
        ``redirect_chain``, ``status_code``, ``strategy``, ``content``,
        ``verified``, ``verification_reason``.

    Raises:
        ValueError: If required config is missing or strategy is unsupported.
        ImportError: If ``verify_org`` is provided but ``openai`` is not installed.
        urllib.error.URLError: On network errors (``local_direct``).
        http.client.HTTPException: On network errors (remote strategies).
        socket.timeout: On connection timeout.
    """
    domain = _normalize_domain(domain)

    if strategy == "local_direct":
        result = _fetch_local_direct(domain, verify_ssl, timeout_seconds)
    elif strategy in ("remote_direct", "remote_headless"):
        if scrape_do_config is None:
            scrape_do_config = ScrapeDoConfig.from_env()
        render = strategy == "remote_headless"
        result = _fetch_remote(domain, scrape_do_config, render)
    else:
        raise ValueError(f"Unsupported redirect strategy: {strategy!r}")

    final_domain = urlparse(result.final_url).netloc

    verified = None
    verification_reason = None
    if verify_org is not None:
        if llm_config is None:
            llm_config = LlmVerifierConfig.from_env()
        verified, verification_reason = _verify_org_content(
            result.content, verify_org, llm_config
        )

    return {
        "domain": domain,
        "redirects": result.redirects,
        "final_domain": final_domain,
        "redirect_chain": result.redirect_chain,
        "status_code": result.status_code,
        "strategy": strategy,
        "content": result.content,
        "verified": verified,
        "verification_reason": verification_reason,
    }
