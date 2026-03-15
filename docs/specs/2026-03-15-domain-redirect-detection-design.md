# Domain Redirect Detection — Design Spec

**Date:** 2026-03-15
**Module:** `src/common_functions/redirects.py`
**Status:** Approved

## Summary

A standalone `check_redirect()` function that detects whether a domain redirects to another domain, using configurable fetch strategies. Optionally verifies that the page content belongs to a given organisation via an OpenAI-compatible LLM.

## Motivation

Some domains redirect to a different domain (e.g., vanity URLs, expired domains, rebrands). We need to:
1. Detect redirects and capture the final canonical domain.
2. Verify that the destination page actually belongs to the expected organisation (not parked, sold, or hijacked).

Some domains block automated HTTP requests with 403/bot-detection, so multiple fetch strategies are needed.

## Strategies

Three fetch strategies, selected via a string literal:

| Strategy | Implementation | When to use |
|---|---|---|
| `local_direct` | stdlib `urllib` with redirect tracking | Fast, free, works for simple domains |
| `remote_direct` | Scrape.do API, `render=false` | Domains that block direct requests |
| `remote_headless` | Scrape.do API, `render=true` | Domains with JS redirects or bot detection |

## Data Types

### `RedirectStrategy`

```python
RedirectStrategy = Literal["local_direct", "remote_direct", "remote_headless"]
```

### `ScrapeDoConfig`

Frozen dataclass with `from_env()` factory.

| Field | Env var | Default | Required |
|---|---|---|---|
| `api_token` | `SCRAPE_DO_API_TOKEN` | — | Yes (for remote strategies) |
| `geo_code` | `SCRAPE_DO_GEO_CODE` | `"gb"` | No |
| `timeout_seconds` | — | `30` | No |

### `LlmVerifierConfig`

Frozen dataclass with `from_env()` factory.

| Field | Env var | Default | Required |
|---|---|---|---|
| `api_key` | `MIMO_API_KEY` | — | Yes (when verify_org provided) |
| `base_url` | `MIMO_BASE_URL` | `"https://api.xiaomimimo.com/v1"` | No |
| `model` | `MIMO_MODEL` | `"mimo-v2-flash"` | No |

### `OrgInfo`

TypedDict for optional organisation verification. `name` and `context` are required; `postcode` is optional.

```python
from typing import Required, TypedDict  # Python 3.11+

class OrgInfo(TypedDict, total=False):
    name: Required[str]
    postcode: str
    context: Required[str]
```

### Return dict

```python
{
    "domain": "www.fitzjohns.camden.sch.uk",
    "redirects": True,
    "final_domain": "fitzjohns.school",
    "redirect_chain": ["www.fitzjohns.camden.sch.uk", "fitzjohns.school"],
    "status_code": 301,              # initial HTTP status (before redirects)
    "strategy": "remote_headless",
    "content": "# Fitzjohn's ...",   # HTML for local, markdown for remote
    "verified": True,                # None if verify_org not provided
    "verification_reason": "Page title and content reference Fitzjohn's Primary School in NW3",
}
```

**Field semantics:**
- `status_code`: The HTTP status of the **initial** response (before any redirects are followed). For `local_direct`, this is the first hop's status code. For remote strategies, this is `Scrape.do-Initial-Status-Code`. When no redirect occurs, this is typically `200`.
- `redirect_chain`: The sequence of URLs from original to final. For `local_direct`, this captures every intermediate hop. For remote strategies, Scrape.do only exposes the original and final URL — intermediate hops are not available.
- `content`: The page content fetched from the **final** URL. HTML for `local_direct`, markdown for remote strategies.
- `verified` / `verification_reason`: Both `None` when `verify_org` is not provided.

## Public API

### `check_redirect()`

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
```

**Routing:**
- `local_direct` -> `_fetch_local_direct(domain, verify_ssl, timeout_seconds)`
- `remote_direct` -> `_fetch_remote(domain, config, render=False)`
- `remote_headless` -> `_fetch_remote(domain, config, render=True)`

**Timeout:** The top-level `timeout_seconds` parameter applies only to `local_direct`. For remote strategies, the timeout is controlled by `ScrapeDoConfig.timeout_seconds` (default 30). This separation exists because the remote service has its own timeout semantics and the caller may want different values for local vs remote.

**Domain normalization:** Input domain is stripped, lowercased, and validated before use (consistent with `_normalize_domain` in `domain_ratings.py`).

**Config auto-initialization:** If `scrape_do_config` is omitted for a remote strategy, build from env vars via `ScrapeDoConfig.from_env()`. Same for `llm_config` when `verify_org` is provided.

**Verification step:** If `verify_org` is provided, the fetched content is passed to `_verify_org_content()` after the fetch. Results populate the `verified` and `verification_reason` fields. If `verify_org` is not provided, both fields are `None`.

**Errors:**
- `ValueError` if remote strategy and Scrape.do env vars missing
- `ValueError` if `verify_org` provided but MiMo env vars missing
- `ValueError` if unsupported strategy
- `ImportError` if `verify_org` provided but `openai` package not installed
- Network errors (`urllib.error.URLError`, `socket.timeout`, `http.client.HTTPException`) propagate to the caller — consistent with `hunter.py` and `domain_ratings.py` which do not catch network exceptions internally

## Internal Functions

### `_FetchResult`

```python
@dataclass
class _FetchResult:
    final_url: str
    status_code: int          # initial HTTP status before redirects
    redirect_chain: list[str]
    content: str              # HTML for local, markdown for remote
    redirects: bool
```

### `_fetch_local_direct(domain, verify_ssl, timeout_seconds)`

- Prepends `https://` to domain (no HTTP fallback — HTTPS only; if the site does not serve HTTPS, the error propagates to the caller)
- Uses `urllib.request.urlopen()` with a custom redirect handler that records each hop
- Maximum 10 redirects before raising an error (prevents redirect loops)
- Returns `_FetchResult` with HTML content
- `verify_ssl` controls whether SSL certificate verification is performed (default `True`); set to `False` for domains with expired/invalid certificates
- `timeout_seconds` passed to `urlopen()`

### `_fetch_remote(domain, config, render)`

- Uses `http.client.HTTPSConnection("api.scrape.do")` — chosen over `urllib.request` because Scrape.do returns redirect metadata in custom response headers (`Scrape.do-*`), which are easier to read from `http.client.HTTPResponse` directly
- Query params: `token`, `url`, `geoCode`, `render`, `output=markdown`, `transparentResponse=true`
- Reads redirect info from Scrape.do response headers:
  - `Scrape.do-Target-Url` — original URL
  - `Scrape.do-Resolved-Url` — final URL after redirects
  - `Scrape.do-Initial-Status-Code` — initial HTTP status
- Compares target vs resolved URL to determine `redirects`
- Timeout controlled by `config.timeout_seconds`, set on `HTTPSConnection(timeout=...)`
- Returns `_FetchResult` with markdown content

### `_verify_org_content(content, org_info, config)`

Returns `tuple[bool, str]` (verified, reason).

- Uses `openai` SDK with `config.base_url` and `config.api_key`
- System prompt includes org name, postcode (if provided), and context
- User message contains the first 4000 characters of the page content
- Model params: `temperature=0.1`, `max_completion_tokens=256`, `response_format={"type": "json_object"}`
- Expects JSON response: `{"verified": true/false, "reason": "..."}`
- On parse failure: returns `(False, "LLM response could not be parsed")`

## Dependencies

- `openai` added as an optional dependency: `[project.optional-dependencies] redirects = ["openai"]`
- Core package remains zero-deps
- Lazy import of `openai` — only imported when `verify_org` is provided

## Testing

File: `tests/test_redirects.py`

Following existing codebase pattern (in-memory fakes, no mocking libraries):

**Happy paths:**
- `_fetch_local_direct`: Fake urllib handler returning 200 (no redirect) and 301+Location (redirect with chain)
- `_fetch_remote`: Fake `http.client` responses with Scrape.do headers for redirect/no-redirect cases
- `_verify_org_content`: Fake OpenAI client returning canned JSON; test verified=True, verified=False, malformed response
- `check_redirect` routing: Verify correct strategy dispatched, verify_org optional, config auto-init from env vars

**Error paths:**
- Timeout handling: fake handler that raises `socket.timeout`
- DNS/connection failure: fake handler that raises `urllib.error.URLError`
- Scrape.do API error: fake response with non-200 status from Scrape.do itself
- Redirect loop: fake handler returning >10 consecutive redirects
- Missing config: verify `ValueError` when env vars absent

## Exports

Added to `src/common_functions/__init__.py`:

```python
from .redirects import check_redirect, ScrapeDoConfig, LlmVerifierConfig, OrgInfo
```

## Documentation

- Docstrings on all public functions/classes (pdoc-compatible, Google-style)
- README updated with redirect-checking section
- CHANGELOG updated
- API docs regenerated via pre-commit hook

## Out of Scope (v1)

- **Caching:** No cache layer for redirect results. Can be added later using the existing `CacheStore` Protocol pattern if needed for batch use cases.
- **Batch API:** Single-domain calls only. Batch orchestration is the caller's responsibility.
