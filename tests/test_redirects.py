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


def test_fetch_local_direct_no_redirect(monkeypatch):
    """Domain that returns 200 with no redirect."""
    from common_functions.redirects import _fetch_local_direct, _FetchResult
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


def test_redirect_tracker_loop():
    """More than 10 redirects raises URLError."""
    from common_functions.redirects import _RedirectTracker, _MAX_REDIRECTS
    import urllib.request
    import urllib.error

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

        def close(self):
            pass

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

        def close(self):
            pass

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
