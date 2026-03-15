"""Domain redirect detection with configurable fetch strategies.

Provides :func:`check_redirect` to detect whether a domain redirects to
another domain, using local or remote (Scrape.do) fetch strategies.
Optionally verifies page content against organisation metadata via a
DSPy-powered LLM verifier with prompt-optimisation support.
"""

from __future__ import annotations

from dataclasses import dataclass
import http.client
import os
import ssl
import urllib.request
import urllib.error
import logging
from typing import Any, Literal, Required, Sequence, TypedDict
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
            - ``SCRAPE_DO_API_KEY``

        Optional variables:
            - ``SCRAPE_DO_GEO_CODE`` (default ``"gb"``)

        Returns:
            Populated :class:`ScrapeDoConfig`.

        Raises:
            ValueError: If ``SCRAPE_DO_API_KEY`` is missing or empty.
        """
        api_token = os.getenv("SCRAPE_DO_API_KEY", "").strip()
        if not api_token:
            raise ValueError(
                "Missing required env var: SCRAPE_DO_API_KEY"
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
            - ``XIAOMI_API_KEY``

        Optional variables:
            - ``XIAOMI_BASE_URL`` (default ``"https://api.xiaomimimo.com/v1"``)
            - ``XIAOMI_MODEL`` (default ``"mimo-v2-flash"``)

        Returns:
            Populated :class:`LlmVerifierConfig`.

        Raises:
            ValueError: If ``XIAOMI_API_KEY`` is missing or empty.
        """
        api_key = os.getenv("XIAOMI_API_KEY", "").strip()
        if not api_key:
            raise ValueError("Missing required env var: XIAOMI_API_KEY")
        base_url = os.getenv(
            "XIAOMI_BASE_URL", "https://api.xiaomimimo.com/v1"
        ).strip()
        model = os.getenv("XIAOMI_MODEL", "mimo-v2-flash").strip()
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
    for prefix in ("https://", "http://"):
        if domain.startswith(prefix):
            domain = domain[len(prefix):]
            break
    domain = domain.rstrip("/")
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


def _get_dspy():
    """Lazy-import dspy.

    Returns:
        The ``dspy`` module.

    Raises:
        ImportError: If the ``dspy`` package is not installed.
    """
    try:
        import dspy
    except ImportError:
        raise ImportError(
            "The 'dspy' package is required for organisation verification. "
            "Install it with: pip install common-functions[redirects]"
        )
    return dspy


def _build_org_verification_signature(org_info: OrgInfo):
    """Build a DSPy Signature class for organisation verification.

    The signature's docstring is dynamically set from *org_info* so that
    the LLM receives organisation context as task instructions.

    Args:
        org_info: Organisation metadata for verification.

    Returns:
        A ``dspy.Signature`` subclass tailored to the organisation.
    """
    dspy = _get_dspy()

    postcode = org_info.get("postcode", "")
    postcode_line = f"Postcode: {postcode}\n" if postcode else ""

    instructions = (
        f"You are verifying whether a webpage belongs to a specific organisation.\n\n"
        f"Organisation: {org_info['name']}\n"
        f"{postcode_line}"
        f"Context: {org_info['context']}\n\n"
        f"Analyse the page content and determine if it belongs to this organisation."
    )

    class OrgVerification(dspy.Signature):
        __doc__ = instructions

        page_content: str = dspy.InputField(desc="webpage content (HTML or markdown)")
        verified: bool = dspy.OutputField(desc="whether the page belongs to the organisation")
        reason: str = dspy.OutputField(desc="brief explanation for the verdict")

    return OrgVerification


def _verify_org_content(
    content: str, org_info: OrgInfo, config: LlmVerifierConfig
) -> tuple[bool, str]:
    """Verify page content belongs to the expected organisation via DSPy.

    Uses a typed DSPy :class:`~dspy.Signature` with ``bool`` and ``str``
    output fields so the LLM response is automatically parsed and
    validated.  The configured LM is scoped via :func:`dspy.context` to
    avoid mutating global state.

    Args:
        content: Page content (HTML or markdown).
        org_info: Organisation metadata for verification.
        config: LLM API configuration.

    Returns:
        Tuple of (verified, reason).
    """
    dspy = _get_dspy()

    lm = dspy.LM(
        f"openai/{config.model}",
        api_key=config.api_key,
        api_base=config.base_url,
        temperature=0.1,
        max_tokens=256,
        cache=False,
    )

    signature = _build_org_verification_signature(org_info)
    predictor = dspy.Predict(signature)

    truncated_content = content[:4000]

    with dspy.context(lm=lm):
        result = predictor(page_content=truncated_content)

    return bool(result.verified), str(result.reason)


def verify_domain_belongs_to_org(
    *,
    content: str,
    org_info: OrgInfo,
    llm_config: LlmVerifierConfig | None = None,
) -> dict[str, Any]:
    """Verify whether page content belongs to a specific organisation.

    Delegates to the internal DSPy-powered verifier without requiring a
    redirect check.  Useful when you already have the HTML/markdown from
    another source (e.g. a crawl pipeline or cached fetch).

    Examples:
        **Minimal — env-var config** (requires ``XIAOMI_API_KEY``):

        >>> result = verify_domain_belongs_to_org(
        ...     content="<html><title>Fitzjohn's Primary</title></html>",
        ...     org_info={
        ...         "name": "Fitzjohn's Primary School",
        ...         "context": "UK primary school in Camden, London",
        ...     },
        ... )
        >>> result["verified"]
        True

        **With explicit** :class:`LlmVerifierConfig`:

        >>> from common_functions import LlmVerifierConfig
        >>> result = verify_domain_belongs_to_org(
        ...     content="# School Page",
        ...     org_info={
        ...         "name": "Fitzjohn's Primary School",
        ...         "context": "UK primary school in Camden, London",
        ...     },
        ...     llm_config=LlmVerifierConfig(
        ...         api_key="sk-xxx",
        ...         base_url="https://api.openai.com/v1",
        ...         model="gpt-4o-mini",
        ...     ),
        ... )

        **With postcode in** ``org_info``:

        >>> result = verify_domain_belongs_to_org(
        ...     content="# School Page",
        ...     org_info={
        ...         "name": "Fitzjohn's Primary School",
        ...         "postcode": "NW3 5QE",
        ...         "context": "UK primary school in Camden, London",
        ...     },
        ... )

    Args:
        content: Page content (HTML or markdown).
        org_info: Organisation metadata for verification.
        llm_config: LLM verifier configuration.  Auto-initialized from
            environment variables when ``None``.

    Returns:
        Dict with keys ``verified`` (bool) and ``reason`` (str).

    Raises:
        ValueError: If ``llm_config`` is ``None`` and required env vars
            are missing.
        ImportError: If ``dspy`` is not installed.
    """
    if llm_config is None:
        llm_config = LlmVerifierConfig.from_env()
    verified, reason = _verify_org_content(content, org_info, llm_config)
    return {"verified": verified, "reason": reason}


_log = logging.getLogger(__name__)


def _execute_strategy(
    strategy: RedirectStrategy,
    domain: str,
    scrape_do_config: ScrapeDoConfig | None,
    verify_ssl: bool,
    timeout_seconds: int,
) -> _FetchResult:
    """Run a single fetch strategy and return the result.

    Args:
        strategy: Which strategy to execute.
        domain: Normalized domain name.
        scrape_do_config: Scrape.do config (required for remote strategies).
        verify_ssl: SSL verification flag (local only).
        timeout_seconds: Connection timeout (local only).

    Returns:
        :class:`_FetchResult` from the strategy.

    Raises:
        ValueError: If the strategy name is not recognised.
    """
    if strategy == "local_direct":
        return _fetch_local_direct(domain, verify_ssl, timeout_seconds)
    if strategy in ("remote_direct", "remote_headless"):
        if scrape_do_config is None:
            scrape_do_config = ScrapeDoConfig.from_env()
        render = strategy == "remote_headless"
        return _fetch_remote(domain, scrape_do_config, render)
    raise ValueError(f"Unsupported redirect strategy: {strategy!r}")


def check_redirect(
    *,
    domain: str,
    strategy: RedirectStrategy | Sequence[RedirectStrategy] = "local_direct",
    scrape_do_config: ScrapeDoConfig | None = None,
    verify_org: OrgInfo | None = None,
    llm_config: LlmVerifierConfig | None = None,
    verify_ssl: bool = False,
    timeout_seconds: int = 20,
) -> dict[str, Any]:
    """Check whether a domain redirects to another domain.

    Fetches the domain using the specified strategy and optionally verifies
    that the page content belongs to a given organisation using a DSPy-powered
    LLM verifier.

    When *strategy* is a sequence, strategies are tried in order.  If a
    strategy raises a network or timeout error the next one is attempted.
    The result from the first successful strategy is returned.  If every
    strategy fails, the last exception is re-raised.

    The two remote strategy names control headless rendering:

    * ``"remote_direct"`` — Scrape.do fetches the page **without** a
      browser (fast, low cost).
    * ``"remote_headless"`` — Scrape.do renders the page in a **headless
      browser** (handles JS-heavy sites, higher cost).

    Examples:
        **Minimal — local redirect check (no API keys needed):**

        >>> result = check_redirect(domain="olddomain.com")
        >>> result["redirects"]
        True
        >>> result["final_domain"]
        'newdomain.com'

        **Fallback chain — try local first, then remote headless:**

        >>> result = check_redirect(
        ...     domain="www.sns.hackney.sch.uk",
        ...     strategy=["local_direct", "remote_headless"],
        ... )

        **Remote without headless rendering** (fast, no JS):

        >>> result = check_redirect(
        ...     domain="olddomain.com",
        ...     strategy="remote_direct",
        ... )

        **Remote with headless rendering** (JS-heavy sites):

        >>> result = check_redirect(
        ...     domain="olddomain.com",
        ...     strategy="remote_headless",
        ... )

        **Remote with explicit** :class:`ScrapeDoConfig` **and custom
        timeout:**

        >>> from common_functions import ScrapeDoConfig
        >>> config = ScrapeDoConfig(
        ...     api_token="tok_xxx",
        ...     geo_code="us",
        ...     timeout_seconds=60,
        ... )
        >>> result = check_redirect(
        ...     domain="olddomain.com",
        ...     strategy="remote_headless",
        ...     scrape_do_config=config,
        ... )

        **Full fallback chain with explicit Scrape.do config:**

        >>> result = check_redirect(
        ...     domain="www.sns.hackney.sch.uk",
        ...     strategy=["local_direct", "remote_headless"],
        ...     scrape_do_config=ScrapeDoConfig(
        ...         api_token="tok_xxx",
        ...         timeout_seconds=60,
        ...     ),
        ... )

        **With LLM organisation verification — auto-configured from env
        vars** (requires ``XIAOMI_API_KEY``):

        >>> result = check_redirect(
        ...     domain="www.sns.hackney.sch.uk",
        ...     verify_org={
        ...         "name": "Stoke Newington School",
        ...         "context": "UK secondary school in Hackney, London",
        ...     },
        ... )
        >>> result["verified"]
        True
        >>> result["verification_reason"]
        'Page title and meta tags match the school...'

        **With explicit** :class:`LlmVerifierConfig` **(e.g. different
        model or provider):**

        >>> from common_functions import LlmVerifierConfig
        >>> llm_cfg = LlmVerifierConfig(
        ...     api_key="sk-xxx",
        ...     base_url="https://api.openai.com/v1",
        ...     model="gpt-4o-mini",
        ... )
        >>> result = check_redirect(
        ...     domain="www.sns.hackney.sch.uk",
        ...     strategy=["local_direct", "remote_headless"],
        ...     scrape_do_config=ScrapeDoConfig(api_token="tok_xxx"),
        ...     verify_org={
        ...         "name": "Stoke Newington School",
        ...         "context": "UK secondary school in Hackney, London",
        ...     },
        ...     llm_config=llm_cfg,
        ... )

        **Full result dict structure:**

        >>> sorted(result.keys())
        ['content', 'domain', 'final_domain', 'redirect_chain',
         'redirects', 'status_code', 'strategy', 'verification_reason',
         'verified']

    Args:
        domain: The domain to check (e.g. ``"www.example.com"``).
        strategy: Fetch strategy or ordered sequence of strategies to try.
            A single string or a list/tuple of:
            ``"local_direct"`` — stdlib urllib, follows redirects;
            ``"remote_direct"`` — Scrape.do **without** JS rendering;
            ``"remote_headless"`` — Scrape.do **with** headless browser.
        scrape_do_config: Configuration for Scrape.do API. Auto-initialized
            from env vars if omitted for a remote strategy.
        verify_org: Optional organisation metadata for LLM content
            verification. Pass ``None`` to skip verification.
        llm_config: Configuration for the LLM verifier. Auto-initialized
            from env vars if omitted when ``verify_org`` is provided.
        verify_ssl: Whether to verify SSL certificates (``local_direct``
            only). Defaults to ``False``.
        timeout_seconds: Connection timeout in seconds (``local_direct`` only).
            Remote strategies use ``ScrapeDoConfig.timeout_seconds``.

    Returns:
        Dict with keys: ``domain``, ``redirects``, ``final_domain``,
        ``redirect_chain``, ``status_code``, ``strategy``, ``content``,
        ``verified``, ``verification_reason``.

    Raises:
        ValueError: If required config is missing or strategy is unsupported.
        ImportError: If ``verify_org`` is provided but ``dspy`` is not
            installed.
        urllib.error.URLError: On network errors (``local_direct``).
        http.client.HTTPException: On network errors (remote strategies).
        socket.timeout: On connection timeout.
    """
    domain = _normalize_domain(domain)

    # Normalise strategy to a list for uniform handling.
    strategies: Sequence[RedirectStrategy]
    if isinstance(strategy, str):
        strategies = [strategy]  # type: ignore[list-item]
    else:
        strategies = strategy

    if not strategies:
        raise ValueError("At least one strategy must be provided.")

    # Try each strategy in order; fall back on network/timeout errors.
    result: _FetchResult | None = None
    used_strategy: RedirectStrategy | None = None
    last_exc: Exception | None = None

    for strat in strategies:
        try:
            result = _execute_strategy(
                strat, domain, scrape_do_config, verify_ssl, timeout_seconds,
            )
            used_strategy = strat
            break
        except (
            urllib.error.URLError,
            http.client.HTTPException,
            OSError,
            TimeoutError,
        ) as exc:
            last_exc = exc
            _log.debug(
                "Strategy %r failed for %s: %s — trying next",
                strat, domain, exc,
            )

    if result is None:
        raise last_exc  # type: ignore[misc]

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
        "strategy": used_strategy,
        "content": result.content,
        "verified": verified,
        "verification_reason": verification_reason,
    }
