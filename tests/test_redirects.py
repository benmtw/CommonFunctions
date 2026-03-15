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
