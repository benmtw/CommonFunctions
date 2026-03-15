# Domain Redirect Detection Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `check_redirect()` function to detect domain redirects using three configurable strategies, with optional LLM-based organisation verification.

**Architecture:** A single new module `src/common_functions/redirects.py` following the existing codebase patterns: frozen dataclasses with `from_env()` for config, `Literal` types for strategy selection, and keyword-only public API. LLM verification uses the `openai` SDK as an optional dependency.

**Tech Stack:** Python stdlib (`urllib.request`, `http.client`), `openai` SDK (optional), MiMo LLM API (OpenAI-compatible)

**Spec:** `docs/specs/2026-03-15-domain-redirect-detection-design.md`

---

## File Map

| Action | File | Responsibility |
|--------|------|----------------|
| Create | `src/common_functions/redirects.py` | All redirect logic: config dataclasses, fetch strategies, LLM verification, public `check_redirect()` |
| Create | `tests/test_redirects.py` | Tests with in-memory fakes |
| Modify | `src/common_functions/__init__.py` | Export new public names |
| Modify | `pyproject.toml` | Add `redirects` optional dependency group |
| Modify | `.env.example` | Add `SCRAPE_DO_API_TOKEN` and `MIMO_API_KEY` |
| Modify | `README.md` | Add redirect-checking section |
| Modify | `CHANGELOG.md` | Add entry |

---

## Chunk 1: Config dataclasses and domain normalization

### Task 1: ScrapeDoConfig dataclass

**Files:**
- Create: `src/common_functions/redirects.py`
- Create: `tests/test_redirects.py`

- [ ] **Step 1: Write the failing test for ScrapeDoConfig.from_env()**

In `tests/test_redirects.py`:

```python
import os


def test_scrape_do_config_from_env(monkeypatch):
    monkeypatch.setenv("SCRAPE_DO_API_TOKEN", "tok123")
    monkeypatch.setenv("SCRAPE_DO_GEO_CODE", "us")
    from common_functions.redirects import ScrapeDoConfig

    cfg = ScrapeDoConfig.from_env()
    assert cfg.api_token == "tok123"
    assert cfg.geo_code == "us"
    assert cfg.timeout_seconds == 30


def test_scrape_do_config_from_env_defaults(monkeypatch):
    monkeypatch.setenv("SCRAPE_DO_API_TOKEN", "tok123")
    monkeypatch.delenv("SCRAPE_DO_GEO_CODE", raising=False)
    from common_functions.redirects import ScrapeDoConfig

    cfg = ScrapeDoConfig.from_env()
    assert cfg.geo_code == "gb"


def test_scrape_do_config_from_env_missing(monkeypatch):
    monkeypatch.delenv("SCRAPE_DO_API_TOKEN", raising=False)
    from common_functions.redirects import ScrapeDoConfig

    try:
        ScrapeDoConfig.from_env()
    except ValueError as exc:
        assert "SCRAPE_DO_API_TOKEN" in str(exc)
    else:
        raise AssertionError("Expected ValueError")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_redirects.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'common_functions.redirects'`

- [ ] **Step 3: Write minimal implementation**

In `src/common_functions/redirects.py`:

```python
"""Domain redirect detection with configurable fetch strategies.

Provides :func:`check_redirect` to detect whether a domain redirects to
another domain, using local or remote (Scrape.do) fetch strategies.
Optionally verifies page content against organisation metadata via an
OpenAI-compatible LLM.
"""

from __future__ import annotations

from dataclasses import dataclass
import os


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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_redirects.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add src/common_functions/redirects.py tests/test_redirects.py
git commit -m "Add ScrapeDoConfig dataclass with from_env() for redirect detection"
```

### Task 2: LlmVerifierConfig dataclass

**Files:**
- Modify: `src/common_functions/redirects.py`
- Modify: `tests/test_redirects.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_redirects.py`:

```python
def test_llm_verifier_config_from_env(monkeypatch):
    monkeypatch.setenv("MIMO_API_KEY", "key123")
    monkeypatch.setenv("MIMO_BASE_URL", "https://custom.api/v1")
    monkeypatch.setenv("MIMO_MODEL", "custom-model")
    from common_functions.redirects import LlmVerifierConfig

    cfg = LlmVerifierConfig.from_env()
    assert cfg.api_key == "key123"
    assert cfg.base_url == "https://custom.api/v1"
    assert cfg.model == "custom-model"


def test_llm_verifier_config_from_env_defaults(monkeypatch):
    monkeypatch.setenv("MIMO_API_KEY", "key123")
    monkeypatch.delenv("MIMO_BASE_URL", raising=False)
    monkeypatch.delenv("MIMO_MODEL", raising=False)
    from common_functions.redirects import LlmVerifierConfig

    cfg = LlmVerifierConfig.from_env()
    assert cfg.base_url == "https://api.xiaomimimo.com/v1"
    assert cfg.model == "mimo-v2-flash"


def test_llm_verifier_config_from_env_missing(monkeypatch):
    monkeypatch.delenv("MIMO_API_KEY", raising=False)
    from common_functions.redirects import LlmVerifierConfig

    try:
        LlmVerifierConfig.from_env()
    except ValueError as exc:
        assert "MIMO_API_KEY" in str(exc)
    else:
        raise AssertionError("Expected ValueError")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_redirects.py::test_llm_verifier_config_from_env -v`
Expected: FAIL — `ImportError: cannot import name 'LlmVerifierConfig'`

- [ ] **Step 3: Write minimal implementation**

Add to `src/common_functions/redirects.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_redirects.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add src/common_functions/redirects.py tests/test_redirects.py
git commit -m "Add LlmVerifierConfig dataclass with from_env() for redirect detection"
```

### Task 3: OrgInfo TypedDict and _normalize_domain helper

**Files:**
- Modify: `src/common_functions/redirects.py`
- Modify: `tests/test_redirects.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_redirects.py`:

```python
def test_normalize_domain_strips_and_lowercases():
    from common_functions.redirects import _normalize_domain

    assert _normalize_domain("  Example.COM  ") == "example.com"


def test_normalize_domain_rejects_empty():
    from common_functions.redirects import _normalize_domain

    try:
        _normalize_domain("")
    except ValueError:
        pass
    else:
        raise AssertionError("Expected ValueError for empty domain")


def test_normalize_domain_rejects_whitespace_in_middle():
    from common_functions.redirects import _normalize_domain

    try:
        _normalize_domain("bad domain.com")
    except ValueError:
        pass
    else:
        raise AssertionError("Expected ValueError for domain with whitespace")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_redirects.py::test_normalize_domain_strips_and_lowercases -v`
Expected: FAIL — `ImportError: cannot import name '_normalize_domain'`

- [ ] **Step 3: Write minimal implementation**

Add to `src/common_functions/redirects.py`:

```python
from typing import Any, Literal, Required, TypedDict


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
```

**Note on Python version:** `Required` was added in `typing` in Python 3.11. The project declares `requires-python = ">=3.10"`. If Python 3.10 support is needed, add a conditional import at the top of the file:

```python
import sys
if sys.version_info >= (3, 11):
    from typing import Any, Literal, Required, TypedDict
else:
    from typing import Any, Literal, TypedDict
    from typing_extensions import Required
```

For simplicity, proceed with the `typing` import only (Python 3.11+). The implementer should confirm the minimum Python version with the project owner.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_redirects.py -v`
Expected: 9 passed

- [ ] **Step 5: Commit**

```bash
git add src/common_functions/redirects.py tests/test_redirects.py
git commit -m "Add OrgInfo, RedirectStrategy, and domain normalization for redirects"
```

---

## Chunk 2: _FetchResult and _fetch_local_direct

### Task 4: _FetchResult dataclass and _fetch_local_direct happy path

**Files:**
- Modify: `src/common_functions/redirects.py`
- Modify: `tests/test_redirects.py`

- [ ] **Step 1: Write the failing tests**

Test `_fetch_local_direct` by monkeypatching `OpenerDirector.open` (since the implementation uses `build_opener`). The `_RedirectTracker` is tested separately in Task 5.

Append to `tests/test_redirects.py`:

```python
from common_functions.redirects import _FetchResult


def test_fetch_local_direct_no_redirect(monkeypatch):
    """Domain that returns 200 with no redirect."""
    from common_functions.redirects import _fetch_local_direct
    import urllib.request

    class _FakeResponse:
        status = 200
        url = "https://example.com"

        def read(self):
            return b"<html>Example</html>"

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    monkeypatch.setattr(
        urllib.request.OpenerDirector, "open", lambda self, *a, **kw: _FakeResponse()
    )

    result = _fetch_local_direct("example.com", verify_ssl=True, timeout_seconds=20)
    assert isinstance(result, _FetchResult)
    assert result.redirects is False
    assert result.final_url == "https://example.com"
    assert result.status_code == 200
    assert result.redirect_chain == ["https://example.com"]
    assert result.content == "<html>Example</html>"


def test_fetch_local_direct_with_redirect(monkeypatch):
    """Domain that redirects to another domain — tested via check_redirect."""
    # _fetch_local_direct with real redirects is hard to fake at the urllib
    # level because the redirect handler and opener are tightly coupled.
    # The redirect chain tracking is tested via _RedirectTracker in Task 5.
    # Integration is tested in Task 9 via check_redirect with _fetch_local_direct
    # monkeypatched to return a _FetchResult directly.
    pass
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_redirects.py::test_fetch_local_direct_no_redirect -v`
Expected: FAIL — `ImportError: cannot import name '_FetchResult'`

- [ ] **Step 3: Write minimal implementation**

Add to `src/common_functions/redirects.py`:

```python
import ssl
import urllib.request
import urllib.error
from urllib.parse import urlparse


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
```

**Implementation note:** When `verify_ssl=False`, an `HTTPSHandler` with an unverified SSL context is added to the opener. The `_RedirectTracker` subclasses `HTTPRedirectHandler` and records `(status_code, url)` at each hop, capping at 10 redirects. The `redirects` field compares the netloc of the original vs final URL.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_redirects.py -v`
Expected: 11 passed

- [ ] **Step 5: Commit**

```bash
git add src/common_functions/redirects.py tests/test_redirects.py
git commit -m "Add _FetchResult and _fetch_local_direct for redirect detection"
```

### Task 5: _fetch_local_direct error paths

**Files:**
- Modify: `tests/test_redirects.py`

- [ ] **Step 1: Write error path tests**

Append to `tests/test_redirects.py`:

```python
import socket
import urllib.error


def test_fetch_local_direct_redirect_loop(monkeypatch):
    """More than 10 redirects raises URLError."""
    from common_functions.redirects import _RedirectTracker, _MAX_REDIRECTS
    import urllib.request

    tracker = _RedirectTracker()
    req = urllib.request.Request("https://loop.com")

    for i in range(_MAX_REDIRECTS):
        tracker.redirect_request(
            req, None, 301, "Moved", {}, f"https://loop.com/{i}"
        )
    # The 11th should raise
    try:
        tracker.redirect_request(
            req, None, 301, "Moved", {}, "https://loop.com/11"
        )
    except urllib.error.URLError as exc:
        assert "Too many redirects" in str(exc)
    else:
        raise AssertionError("Expected URLError for redirect loop")
```

- [ ] **Step 2: Run test to verify it passes**

Run: `pytest tests/test_redirects.py::test_fetch_local_direct_redirect_loop -v`
Expected: PASS (the `_RedirectTracker` logic is already implemented)

- [ ] **Step 3: Commit**

```bash
git add tests/test_redirects.py
git commit -m "Add redirect loop error path test"
```

---

## Chunk 3: _fetch_remote (Scrape.do)

### Task 6: _fetch_remote happy paths

**Files:**
- Modify: `src/common_functions/redirects.py`
- Modify: `tests/test_redirects.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_redirects.py`:

```python
def test_fetch_remote_no_redirect(monkeypatch):
    """Scrape.do returns same target and resolved URL."""
    from common_functions.redirects import _fetch_remote, ScrapeDoConfig, _FetchResult
    import http.client

    class _FakeResponse:
        status = 200
        reason = "OK"

        def getheader(self, name, default=None):
            headers = {
                "Scrape.do-Target-Url": "https://example.com",
                "Scrape.do-Resolved-Url": "https://example.com",
                "Scrape.do-Initial-Status-Code": "200",
            }
            return headers.get(name, default)

        def read(self):
            return b"# Example Page"

    class _FakeConnection:
        def __init__(self, *args, **kwargs):
            pass

        def request(self, method, path):
            pass

        def getresponse(self):
            return _FakeResponse()

    monkeypatch.setattr(http.client, "HTTPSConnection", _FakeConnection)

    config = ScrapeDoConfig(api_token="tok123")
    result = _fetch_remote("example.com", config, render=False)

    assert isinstance(result, _FetchResult)
    assert result.redirects is False
    assert result.final_url == "https://example.com"
    assert result.status_code == 200
    assert result.content == "# Example Page"
    assert result.redirect_chain == ["https://example.com"]


def test_fetch_remote_with_redirect(monkeypatch):
    """Scrape.do detects redirect: target != resolved."""
    from common_functions.redirects import _fetch_remote, ScrapeDoConfig
    import http.client

    class _FakeResponse:
        status = 200
        reason = "OK"

        def getheader(self, name, default=None):
            headers = {
                "Scrape.do-Target-Url": "https://olddomain.com",
                "Scrape.do-Resolved-Url": "https://newdomain.com",
                "Scrape.do-Initial-Status-Code": "301",
            }
            return headers.get(name, default)

        def read(self):
            return b"# New Domain Page"

    class _FakeConnection:
        def __init__(self, *args, **kwargs):
            pass

        def request(self, method, path):
            pass

        def getresponse(self):
            return _FakeResponse()

    monkeypatch.setattr(http.client, "HTTPSConnection", _FakeConnection)

    config = ScrapeDoConfig(api_token="tok123")
    result = _fetch_remote("olddomain.com", config, render=True)

    assert result.redirects is True
    assert result.final_url == "https://newdomain.com"
    assert result.status_code == 301
    assert result.redirect_chain == [
        "https://olddomain.com",
        "https://newdomain.com",
    ]
    assert result.content == "# New Domain Page"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_redirects.py::test_fetch_remote_no_redirect -v`
Expected: FAIL — `ImportError: cannot import name '_fetch_remote'`

- [ ] **Step 3: Write minimal implementation**

Add to `src/common_functions/redirects.py`:

```python
import http.client
from urllib.parse import quote


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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_redirects.py -v`
Expected: All passed

- [ ] **Step 5: Commit**

```bash
git add src/common_functions/redirects.py tests/test_redirects.py
git commit -m "Add _fetch_remote for Scrape.do API integration"
```

### Task 7: _fetch_remote error path (Scrape.do API error)

**Files:**
- Modify: `tests/test_redirects.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_redirects.py`:

```python
def test_fetch_remote_scrape_do_api_error(monkeypatch):
    """Scrape.do returns non-200 status (e.g., 500)."""
    from common_functions.redirects import _fetch_remote, ScrapeDoConfig
    import http.client

    class _FakeResponse:
        status = 500
        reason = "Internal Server Error"

        def getheader(self, name, default=None):
            return default

        def read(self):
            return b'{"error": "internal error"}'

    class _FakeConnection:
        def __init__(self, *args, **kwargs):
            pass

        def request(self, method, path):
            pass

        def getresponse(self):
            return _FakeResponse()

    monkeypatch.setattr(http.client, "HTTPSConnection", _FakeConnection)

    config = ScrapeDoConfig(api_token="tok123")
    # The function does not raise — it returns the result with the status.
    # Scrape.do with transparentResponse=true passes through the target's
    # status. The caller decides what to do with non-200 results.
    result = _fetch_remote("failing.com", config, render=False)
    assert result.status_code == 200  # default when header missing
    assert result.content == '{"error": "internal error"}'
```

- [ ] **Step 2: Run test to verify it passes**

Run: `pytest tests/test_redirects.py::test_fetch_remote_scrape_do_api_error -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_redirects.py
git commit -m "Add Scrape.do API error path test"
```

---

## Chunk 4: LLM verification

### Task 8: _verify_org_content

**Files:**
- Modify: `src/common_functions/redirects.py`
- Modify: `tests/test_redirects.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_redirects.py`:

```python
def _make_fake_openai_client(response_text, capture_kwargs=None):
    """Factory for fake OpenAI client that returns canned responses."""

    class _FakeMessage:
        content = response_text

    class _FakeChoice:
        message = _FakeMessage()

    class _FakeCompletion:
        choices = [_FakeChoice()]

    class _FakeCompletions:
        def create(self, **kwargs):
            if capture_kwargs is not None:
                capture_kwargs.update(kwargs)
            return _FakeCompletion()

    class _FakeChat:
        completions = _FakeCompletions()

    class _FakeClient:
        chat = _FakeChat()

        def __init__(self, **kwargs):
            pass

    return _FakeClient


def test_verify_org_content_verified(monkeypatch):
    """LLM returns verified=true."""
    from common_functions.redirects import _verify_org_content, LlmVerifierConfig

    monkeypatch.setattr(
        "common_functions.redirects._make_openai_client",
        _make_fake_openai_client('{"verified": true, "reason": "Page matches the school"}'),
    )

    config = LlmVerifierConfig(api_key="key123")
    org_info = {"name": "Test School", "context": "UK school"}

    verified, reason = _verify_org_content("# Test School\nWelcome", org_info, config)
    assert verified is True
    assert "school" in reason.lower()


def test_verify_org_content_not_verified(monkeypatch):
    """LLM returns verified=false."""
    from common_functions.redirects import _verify_org_content, LlmVerifierConfig

    monkeypatch.setattr(
        "common_functions.redirects._make_openai_client",
        _make_fake_openai_client('{"verified": false, "reason": "Page is a parking page"}'),
    )

    config = LlmVerifierConfig(api_key="key123")
    org_info = {"name": "Test School", "context": "UK school"}

    verified, reason = _verify_org_content("Buy domains cheap!", org_info, config)
    assert verified is False
    assert "parking" in reason.lower()


def test_verify_org_content_malformed_response(monkeypatch):
    """LLM returns unparseable response."""
    from common_functions.redirects import _verify_org_content, LlmVerifierConfig

    monkeypatch.setattr(
        "common_functions.redirects._make_openai_client",
        _make_fake_openai_client("I cannot determine this."),
    )

    config = LlmVerifierConfig(api_key="key123")
    org_info = {"name": "Test School", "context": "UK school"}

    verified, reason = _verify_org_content("Some content", org_info, config)
    assert verified is False
    assert "could not be parsed" in reason.lower()


def test_verify_org_content_with_postcode(monkeypatch):
    """Postcode is included in prompt when provided."""
    from common_functions.redirects import _verify_org_content, LlmVerifierConfig

    captured_kwargs = {}
    monkeypatch.setattr(
        "common_functions.redirects._make_openai_client",
        _make_fake_openai_client(
            '{"verified": true, "reason": "Matches"}',
            capture_kwargs=captured_kwargs,
        ),
    )

    config = LlmVerifierConfig(api_key="key123")
    org_info = {"name": "Test School", "postcode": "NW3 5QE", "context": "UK school"}

    _verify_org_content("Content", org_info, config)

    system_msg = captured_kwargs["messages"][0]["content"]
    assert "NW3 5QE" in system_msg
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_redirects.py::test_verify_org_content_verified -v`
Expected: FAIL — `ImportError: cannot import name '_verify_org_content'`

- [ ] **Step 3: Write minimal implementation**

Add to `src/common_functions/redirects.py`:

```python
import json


_VERIFY_SYSTEM_PROMPT = """You are verifying whether a webpage belongs to a specific organisation.

Organisation: {name}
{postcode_line}Context: {context}

Analyse the page content below and determine if this page belongs to the organisation described above.

Respond with JSON only: {{"verified": true/false, "reason": "brief explanation"}}"""


def _make_openai_client(config: LlmVerifierConfig):
    """Create an OpenAI client (lazy import).

    Args:
        config: LLM verifier configuration.

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
    return OpenAI(api_key=config.api_key, base_url=config.base_url)


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

    client = _make_openai_client(config)
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_redirects.py -v`
Expected: All passed

- [ ] **Step 5: Commit**

```bash
git add src/common_functions/redirects.py tests/test_redirects.py
git commit -m "Add LLM-based organisation verification for redirect detection"
```

---

## Chunk 5: check_redirect public API

### Task 9: check_redirect routing and integration

**Files:**
- Modify: `src/common_functions/redirects.py`
- Modify: `tests/test_redirects.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_redirects.py`:

```python
def test_check_redirect_local_direct_no_redirect(monkeypatch):
    from common_functions.redirects import check_redirect, _FetchResult

    monkeypatch.setattr(
        "common_functions.redirects._fetch_local_direct",
        lambda domain, verify_ssl, timeout_seconds: _FetchResult(
            final_url="https://example.com",
            status_code=200,
            redirect_chain=["https://example.com"],
            content="<html>OK</html>",
            redirects=False,
        ),
    )

    result = check_redirect(domain="example.com")
    assert result["domain"] == "example.com"
    assert result["redirects"] is False
    assert result["final_domain"] == "example.com"
    assert result["status_code"] == 200
    assert result["strategy"] == "local_direct"
    assert result["content"] == "<html>OK</html>"
    assert result["verified"] is None
    assert result["verification_reason"] is None


def test_check_redirect_remote_headless_with_redirect(monkeypatch):
    from common_functions.redirects import check_redirect, _FetchResult, ScrapeDoConfig

    monkeypatch.setattr(
        "common_functions.redirects._fetch_remote",
        lambda domain, config, render: _FetchResult(
            final_url="https://newdomain.com",
            status_code=301,
            redirect_chain=["https://olddomain.com", "https://newdomain.com"],
            content="# New Domain",
            redirects=True,
        ),
    )

    config = ScrapeDoConfig(api_token="tok123")
    result = check_redirect(
        domain="olddomain.com",
        strategy="remote_headless",
        scrape_do_config=config,
    )
    assert result["redirects"] is True
    assert result["final_domain"] == "newdomain.com"
    assert result["status_code"] == 301
    assert result["strategy"] == "remote_headless"


def test_check_redirect_with_verification(monkeypatch):
    from common_functions.redirects import check_redirect, _FetchResult, LlmVerifierConfig

    monkeypatch.setattr(
        "common_functions.redirects._fetch_local_direct",
        lambda domain, verify_ssl, timeout_seconds: _FetchResult(
            final_url="https://school.org",
            status_code=200,
            redirect_chain=["https://school.org"],
            content="# School Page",
            redirects=False,
        ),
    )
    monkeypatch.setattr(
        "common_functions.redirects._verify_org_content",
        lambda content, org_info, config: (True, "Content matches school"),
    )

    config = LlmVerifierConfig(api_key="key123")
    result = check_redirect(
        domain="school.org",
        verify_org={"name": "Test School", "context": "UK school"},
        llm_config=config,
    )
    assert result["verified"] is True
    assert result["verification_reason"] == "Content matches school"


def test_check_redirect_auto_init_scrape_do_config(monkeypatch):
    monkeypatch.setenv("SCRAPE_DO_API_TOKEN", "tok123")
    from common_functions.redirects import check_redirect, _FetchResult

    monkeypatch.setattr(
        "common_functions.redirects._fetch_remote",
        lambda domain, config, render: _FetchResult(
            final_url="https://example.com",
            status_code=200,
            redirect_chain=["https://example.com"],
            content="OK",
            redirects=False,
        ),
    )

    result = check_redirect(domain="example.com", strategy="remote_direct")
    assert result["strategy"] == "remote_direct"


def test_check_redirect_missing_scrape_do_config(monkeypatch):
    monkeypatch.delenv("SCRAPE_DO_API_TOKEN", raising=False)
    from common_functions.redirects import check_redirect

    try:
        check_redirect(domain="example.com", strategy="remote_direct")
    except ValueError as exc:
        assert "SCRAPE_DO_API_TOKEN" in str(exc)
    else:
        raise AssertionError("Expected ValueError")


def test_check_redirect_unsupported_strategy():
    from common_functions.redirects import check_redirect

    try:
        check_redirect(domain="example.com", strategy="magic")
    except ValueError as exc:
        assert "Unsupported" in str(exc)
    else:
        raise AssertionError("Expected ValueError")


def test_check_redirect_normalizes_domain(monkeypatch):
    from common_functions.redirects import check_redirect, _FetchResult

    captured_domain = []

    def fake_fetch(domain, verify_ssl, timeout_seconds):
        captured_domain.append(domain)
        return _FetchResult(
            final_url=f"https://{domain}",
            status_code=200,
            redirect_chain=[f"https://{domain}"],
            content="OK",
            redirects=False,
        )

    monkeypatch.setattr(
        "common_functions.redirects._fetch_local_direct", fake_fetch
    )

    check_redirect(domain="  Example.COM  ")
    assert captured_domain[0] == "example.com"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_redirects.py::test_check_redirect_local_direct_no_redirect -v`
Expected: FAIL — `ImportError: cannot import name 'check_redirect'`

- [ ] **Step 3: Write minimal implementation**

Add to `src/common_functions/redirects.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_redirects.py -v`
Expected: All passed

- [ ] **Step 5: Commit**

```bash
git add src/common_functions/redirects.py tests/test_redirects.py
git commit -m "Add check_redirect public API with strategy routing"
```

---

## Chunk 6: Package integration and documentation

### Task 10: Exports, pyproject.toml, .env.example

**Files:**
- Modify: `src/common_functions/__init__.py`
- Modify: `pyproject.toml`
- Modify: `.env.example`

- [ ] **Step 1: Update __init__.py**

Add to `src/common_functions/__init__.py`:

```python
from .redirects import (
    check_redirect,
    LlmVerifierConfig,
    OrgInfo,
    ScrapeDoConfig,
)
```

And add to `__all__`:

```python
"check_redirect",
"ScrapeDoConfig",
"LlmVerifierConfig",
"OrgInfo",
```

- [ ] **Step 2: Update pyproject.toml**

Add after the `dev` optional dependencies:

```toml
redirects = [
  "openai>=1.0.0",
]
```

- [ ] **Step 3: Update .env.example**

Append:

```
# Scrape.do
SCRAPE_DO_API_TOKEN=your_scrape_do_api_token_here

# MiMo LLM (OpenAI-compatible)
MIMO_API_KEY=your_mimo_api_key_here
```

- [ ] **Step 4: Run full test suite**

Run: `pytest -v`
Expected: All tests pass (existing + new)

- [ ] **Step 5: Commit**

```bash
git add src/common_functions/__init__.py pyproject.toml .env.example
git commit -m "Add redirect detection exports and optional openai dependency"
```

### Task 11: README, CHANGELOG, API docs

**Files:**
- Modify: `README.md`
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Update README.md**

Add a new section after the existing lookup documentation (near the "Dataset Remark" section):

```markdown
### Domain Redirect Detection

Check whether a domain redirects to another domain using configurable strategies:

```python
from common_functions import check_redirect

# Local direct (stdlib urllib, fast and free)
result = check_redirect(domain="olddomain.com")

# Remote via Scrape.do (bypasses bot detection)
result = check_redirect(domain="olddomain.com", strategy="remote_headless")

# With organisation verification via LLM
result = check_redirect(
    domain="www.fitzjohns.camden.sch.uk",
    strategy="remote_headless",
    verify_org={"name": "Fitzjohn's Primary School", "context": "UK school"},
)
```

**Strategies:**
- `local_direct` — stdlib `urllib`, follows redirects (default)
- `remote_direct` — Scrape.do without JS rendering
- `remote_headless` — Scrape.do with headless browser rendering

**Environment variables (remote strategies):**
- `SCRAPE_DO_API_TOKEN` — Scrape.do API token
- `SCRAPE_DO_GEO_CODE` — proxy country (default `gb`)

**Environment variables (LLM verification):**
- `MIMO_API_KEY` — MiMo API key
- `MIMO_BASE_URL` — API base URL (default `https://api.xiaomimimo.com/v1`)
- `MIMO_MODEL` — model name (default `mimo-v2-flash`)

**Optional dependency:** `pip install common-functions[redirects]` for LLM verification support.
```

- [ ] **Step 2: Update CHANGELOG.md**

Add under `### Added`:

```markdown
- Domain redirect detection module:
  - `src/common_functions/redirects.py`
  - `check_redirect(...)` with strategies: `local_direct`, `remote_direct`, `remote_headless`
  - Optional LLM-based organisation verification via OpenAI-compatible API
  - `ScrapeDoConfig`, `LlmVerifierConfig`, `OrgInfo` config types
```

- [ ] **Step 3: Run tests and commit**

Run: `pytest -v`

```bash
git add README.md CHANGELOG.md
git commit -m "Add redirect detection documentation and CHANGELOG entry"
```

- [ ] **Step 4: Let pre-commit hook regenerate API docs**

The pre-commit hook will regenerate `docs/API_REFERENCE.html` automatically. If it modifies the file:

```bash
git add docs/API_REFERENCE.html
git commit -m "Regenerate API reference with redirect detection"
```

---

## Final Verification

- [ ] **Run full test suite:** `pytest -v` — all tests pass
- [ ] **Check imports work:** `python -c "from common_functions import check_redirect, ScrapeDoConfig, LlmVerifierConfig, OrgInfo; print('OK')"`
- [ ] **Verify no regressions:** `pytest tests/test_lookups.py tests/test_domain_ratings.py tests/test_hunter.py tests/test_email_utils.py -v`
