from common_functions.hunter import (
    CloudflareKVConfig,
    HunterClient,
    get_domain_search_cached,
)


class _FakeHunterClient:
    def __init__(self) -> None:
        self.calls = 0

    def domain_search(self, domain: str):
        self.calls += 1
        return {"data": {"domain": domain, "calls": self.calls}}


class _InMemoryCache:
    def __init__(self):
        self.data = {}

    def get(self, key: str):
        return self.data.get(key)

    def set(self, key: str, value):
        self.data[key] = value


def test_hunter_client_requires_key():
    try:
        HunterClient("")
    except ValueError as exc:
        assert "API key" in str(exc)
    else:
        raise AssertionError("Expected ValueError for missing Hunter API key")


def test_cloudflare_config_from_env_requires_all_values(monkeypatch):
    monkeypatch.delenv("CF_ACCOUNT_ID", raising=False)
    monkeypatch.delenv("CF_KV_NAMESPACE_ID", raising=False)
    monkeypatch.delenv("CF_API_TOKEN", raising=False)
    try:
        CloudflareKVConfig.from_env()
    except ValueError as exc:
        assert "CF_ACCOUNT_ID" in str(exc)
        assert "CF_KV_NAMESPACE_ID" in str(exc)
        assert "CF_API_TOKEN" in str(exc)
    else:
        raise AssertionError("Expected ValueError when Cloudflare env vars are missing")


def test_domain_search_cache_miss_then_hit():
    fake_hunter = _FakeHunterClient()
    cache = _InMemoryCache()

    first = get_domain_search_cached(
        domain="example.com",
        hunter_client=fake_hunter,
        cache_store=cache,
        ttl_hours=24,
    )
    second = get_domain_search_cached(
        domain="example.com",
        hunter_client=fake_hunter,
        cache_store=cache,
        ttl_hours=24,
    )

    assert first["data"]["domain"] == "example.com"
    assert second["data"]["domain"] == "example.com"
    assert fake_hunter.calls == 1
