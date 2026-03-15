import os


def test_scrape_do_config_from_env(monkeypatch):
    monkeypatch.setenv("SCRAPE_DO_API_KEY", "tok123")
    monkeypatch.setenv("SCRAPE_DO_GEO_CODE", "us")
    from common_functions.redirects import ScrapeDoConfig
    cfg = ScrapeDoConfig.from_env()
    assert cfg.api_token == "tok123"
    assert cfg.geo_code == "us"
    assert cfg.timeout_seconds == 30


def test_scrape_do_config_from_env_defaults(monkeypatch):
    monkeypatch.setenv("SCRAPE_DO_API_KEY", "tok123")
    monkeypatch.delenv("SCRAPE_DO_GEO_CODE", raising=False)
    from common_functions.redirects import ScrapeDoConfig
    cfg = ScrapeDoConfig.from_env()
    assert cfg.geo_code == "gb"


def test_scrape_do_config_from_env_missing(monkeypatch):
    monkeypatch.delenv("SCRAPE_DO_API_KEY", raising=False)
    from common_functions.redirects import ScrapeDoConfig
    try:
        ScrapeDoConfig.from_env()
    except ValueError as exc:
        assert "SCRAPE_DO_API_KEY" in str(exc)
    else:
        raise AssertionError("Expected ValueError")


def test_llm_verifier_config_from_env(monkeypatch):
    monkeypatch.setenv("XIAOMI_API_KEY", "key123")
    monkeypatch.setenv("XIAOMI_BASE_URL", "https://custom.api/v1")
    monkeypatch.setenv("XIAOMI_MODEL", "custom-model")
    from common_functions.redirects import LlmVerifierConfig
    cfg = LlmVerifierConfig.from_env()
    assert cfg.api_key == "key123"
    assert cfg.base_url == "https://custom.api/v1"
    assert cfg.model == "custom-model"


def test_llm_verifier_config_from_env_defaults(monkeypatch):
    monkeypatch.setenv("XIAOMI_API_KEY", "key123")
    monkeypatch.delenv("XIAOMI_BASE_URL", raising=False)
    monkeypatch.delenv("XIAOMI_MODEL", raising=False)
    from common_functions.redirects import LlmVerifierConfig
    cfg = LlmVerifierConfig.from_env()
    assert cfg.base_url == "https://api.xiaomimimo.com/v1"
    assert cfg.model == "mimo-v2-flash"


def test_llm_verifier_config_from_env_missing(monkeypatch):
    monkeypatch.delenv("XIAOMI_API_KEY", raising=False)
    from common_functions.redirects import LlmVerifierConfig
    try:
        LlmVerifierConfig.from_env()
    except ValueError as exc:
        assert "XIAOMI_API_KEY" in str(exc)
    else:
        raise AssertionError("Expected ValueError")


def test_normalize_domain_strips_and_lowercases():
    from common_functions.redirects import _normalize_domain
    assert _normalize_domain("  Example.COM  ") == "example.com"


def test_normalize_domain_strips_scheme():
    from common_functions.redirects import _normalize_domain
    assert _normalize_domain("https://Example.COM") == "example.com"
    assert _normalize_domain("http://Example.COM/") == "example.com"
    assert _normalize_domain("HTTPS://FOO.BAR/") == "foo.bar"


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

        def close(self):
            pass

    monkeypatch.setattr(http.client, "HTTPSConnection", _FakeConnection)

    config = ScrapeDoConfig(api_token="tok123")
    result = _fetch_remote("failing.com", config, render=False)
    assert result.status_code == 200  # default when header missing
    assert result.content == '{"error": "internal error"}'


def _make_fake_dspy_predict(verified_val, reason_val):
    """Factory for a fake DSPy Predict that returns canned results."""

    class _FakeResult:
        def __init__(self):
            self.verified = verified_val
            self.reason = reason_val

    class _FakePredict:
        def __init__(self, signature):
            self.signature = signature

        def __call__(self, **kwargs):
            return _FakeResult()

    return _FakePredict


def test_verify_org_content_verified(monkeypatch):
    """DSPy returns verified=True."""
    from common_functions.redirects import _verify_org_content, LlmVerifierConfig
    import types

    fake_dspy = types.ModuleType("dspy")
    fake_dspy.LM = lambda *a, **kw: None
    fake_dspy.Predict = _make_fake_dspy_predict(True, "Page matches the school")
    fake_dspy.context = lambda **kw: type("ctx", (), {"__enter__": lambda s: s, "__exit__": lambda s, *a: None})()
    # Provide InputField/OutputField/Signature stubs for _build_org_verification_signature
    fake_dspy.InputField = lambda **kw: None
    fake_dspy.OutputField = lambda **kw: None
    fake_dspy.Signature = type("Signature", (), {})

    monkeypatch.setattr("common_functions.redirects._get_dspy", lambda: fake_dspy)

    config = LlmVerifierConfig(api_key="key123")
    org_info = {"name": "Test School", "context": "UK school"}

    verified, reason = _verify_org_content("# Test School\nWelcome", org_info, config)
    assert verified is True
    assert "school" in reason.lower()


def test_verify_org_content_not_verified(monkeypatch):
    """DSPy returns verified=False."""
    from common_functions.redirects import _verify_org_content, LlmVerifierConfig
    import types

    fake_dspy = types.ModuleType("dspy")
    fake_dspy.LM = lambda *a, **kw: None
    fake_dspy.Predict = _make_fake_dspy_predict(False, "Page is a parking page")
    fake_dspy.context = lambda **kw: type("ctx", (), {"__enter__": lambda s: s, "__exit__": lambda s, *a: None})()
    fake_dspy.InputField = lambda **kw: None
    fake_dspy.OutputField = lambda **kw: None
    fake_dspy.Signature = type("Signature", (), {})

    monkeypatch.setattr("common_functions.redirects._get_dspy", lambda: fake_dspy)

    config = LlmVerifierConfig(api_key="key123")
    org_info = {"name": "Test School", "context": "UK school"}

    verified, reason = _verify_org_content("Buy domains cheap!", org_info, config)
    assert verified is False
    assert "parking" in reason.lower()


def test_verify_org_content_with_postcode(monkeypatch):
    """Postcode is included in DSPy signature instructions when provided."""
    from common_functions.redirects import _build_org_verification_signature
    import types

    fake_dspy = types.ModuleType("dspy")
    fake_dspy.InputField = lambda **kw: None
    fake_dspy.OutputField = lambda **kw: None
    fake_dspy.Signature = type("Signature", (), {})

    monkeypatch.setattr("common_functions.redirects._get_dspy", lambda: fake_dspy)

    org_info = {"name": "Test School", "postcode": "NW3 5QE", "context": "UK school"}
    sig = _build_org_verification_signature(org_info)
    assert "NW3 5QE" in sig.__doc__


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
    monkeypatch.setenv("SCRAPE_DO_API_KEY", "tok123")
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
    monkeypatch.delenv("SCRAPE_DO_API_KEY", raising=False)
    from common_functions.redirects import check_redirect

    try:
        check_redirect(domain="example.com", strategy="remote_direct")
    except ValueError as exc:
        assert "SCRAPE_DO_API_KEY" in str(exc)
    else:
        raise AssertionError("Expected ValueError")


def test_check_redirect_unsupported_strategy():
    from common_functions.redirects import check_redirect

    try:
        check_redirect(domain="example.com", strategy="magic")  # type: ignore[arg-type]
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


def test_check_redirect_strategy_fallback(monkeypatch):
    """When the first strategy fails, the next one is tried."""
    import urllib.error
    from common_functions.redirects import check_redirect, _FetchResult, ScrapeDoConfig

    monkeypatch.setattr(
        "common_functions.redirects._fetch_local_direct",
        lambda domain, verify_ssl, timeout_seconds: (_ for _ in ()).throw(
            urllib.error.URLError("SSL: CERTIFICATE_VERIFY_FAILED")
        ),
    )
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
        strategy=["local_direct", "remote_headless"],
        scrape_do_config=config,
    )
    assert result["redirects"] is True
    assert result["strategy"] == "remote_headless"
    assert result["final_domain"] == "newdomain.com"


def test_check_redirect_all_strategies_fail(monkeypatch):
    """When every strategy fails, the last exception is re-raised."""
    import urllib.error
    from common_functions.redirects import check_redirect, ScrapeDoConfig

    monkeypatch.setattr(
        "common_functions.redirects._fetch_local_direct",
        lambda domain, verify_ssl, timeout_seconds: (_ for _ in ()).throw(
            urllib.error.URLError("local failed")
        ),
    )
    monkeypatch.setattr(
        "common_functions.redirects._fetch_remote",
        lambda domain, config, render: (_ for _ in ()).throw(
            TimeoutError("remote timed out")
        ),
    )

    config = ScrapeDoConfig(api_token="tok123")
    try:
        check_redirect(
            domain="failing.com",
            strategy=["local_direct", "remote_headless"],
            scrape_do_config=config,
        )
    except TimeoutError as exc:
        assert "remote timed out" in str(exc)
    else:
        raise AssertionError("Expected TimeoutError")


def test_check_redirect_empty_strategy_list():
    """An empty strategy list raises ValueError."""
    from common_functions.redirects import check_redirect

    try:
        check_redirect(domain="example.com", strategy=[])
    except ValueError as exc:
        assert "At least one" in str(exc)
    else:
        raise AssertionError("Expected ValueError")


def test_verify_domain_belongs_to_org_verified(monkeypatch):
    """Returns dict with verified=True when content matches."""
    from common_functions.redirects import verify_domain_belongs_to_org, LlmVerifierConfig

    monkeypatch.setattr(
        "common_functions.redirects._verify_org_content",
        lambda content, org_info, config: (True, "Content matches the school"),
    )

    config = LlmVerifierConfig(api_key="key123")
    result = verify_domain_belongs_to_org(
        content="# Test School\nWelcome",
        org_info={"name": "Test School", "context": "UK school"},
        llm_config=config,
    )
    assert result == {"verified": True, "reason": "Content matches the school"}


def test_verify_domain_belongs_to_org_auto_init_config(monkeypatch):
    """Omitting llm_config auto-initialises from env vars."""
    monkeypatch.setenv("XIAOMI_API_KEY", "key123")
    monkeypatch.delenv("XIAOMI_BASE_URL", raising=False)
    monkeypatch.delenv("XIAOMI_MODEL", raising=False)
    from common_functions.redirects import verify_domain_belongs_to_org

    monkeypatch.setattr(
        "common_functions.redirects._verify_org_content",
        lambda content, org_info, config: (False, "Parking page"),
    )

    result = verify_domain_belongs_to_org(
        content="Buy domains cheap!",
        org_info={"name": "Test School", "context": "UK school"},
    )
    assert result["verified"] is False
    assert result["reason"] == "Parking page"


def test_verify_domain_belongs_to_org_missing_config(monkeypatch):
    """No env vars and no config raises ValueError."""
    monkeypatch.delenv("XIAOMI_API_KEY", raising=False)
    from common_functions.redirects import verify_domain_belongs_to_org

    try:
        verify_domain_belongs_to_org(
            content="anything",
            org_info={"name": "Test", "context": "test"},
        )
    except ValueError as exc:
        assert "XIAOMI_API_KEY" in str(exc)
    else:
        raise AssertionError("Expected ValueError")
