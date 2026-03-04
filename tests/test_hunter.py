from common_functions.hunter import (
    CloudflareKVConfig,
    HunterClient,
    get_domain_or_email_info_cached,
    get_domain_search_cached,
    get_email_verification_cached,
)


class _FakeHunterClient:
    def __init__(self) -> None:
        self.domain_calls = 0
        self.verifier_calls = 0

    def domain_search(self, domain: str):
        self.domain_calls += 1
        return {
            "data": {
                "domain": domain,
                "calls": self.domain_calls,
                "emails": [{"value": f"contact@{domain}"}],
            }
        }

    def email_verifier(self, email: str):
        self.verifier_calls += 1
        return {
            "data": {
                "email": email,
                "status": "valid",
                "result": "deliverable",
                "score": 98,
                "regexp": True,
                "gibberish": False,
                "disposable": False,
                "webmail": False,
                "mx_records": True,
                "smtp_server": True,
                "smtp_check": True,
                "accept_all": False,
                "block": False,
                "sources": [],
                "calls": self.verifier_calls,
            }
        }


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
    assert fake_hunter.domain_calls == 1


def test_email_verification_cache_miss_then_hit():
    fake_hunter = _FakeHunterClient()
    cache = _InMemoryCache()

    first = get_email_verification_cached(
        email="person@example.com",
        hunter_client=fake_hunter,
        cache_store=cache,
        ttl_hours=24,
    )
    second = get_email_verification_cached(
        email="person@example.com",
        hunter_client=fake_hunter,
        cache_store=cache,
        ttl_hours=24,
    )

    assert first["data"]["email"] == "person@example.com"
    assert second["data"]["email"] == "person@example.com"
    assert fake_hunter.verifier_calls == 1


def test_domain_or_email_info_accepts_email_and_caches():
    fake_hunter = _FakeHunterClient()
    cache = _InMemoryCache()

    first = get_domain_or_email_info_cached(
        domain_or_email="person@example.com",
        hunter_client=fake_hunter,
        cache_store=cache,
        ttl_hours=24,
    )
    second = get_domain_or_email_info_cached(
        domain_or_email="person@example.com",
        hunter_client=fake_hunter,
        cache_store=cache,
        ttl_hours=24,
    )

    assert first["input_type"] == "email"
    assert first["domain"] == "example.com"
    assert first["email"] == "person@example.com"
    assert first["email_verification"]["data"]["status"] == "valid"
    assert second["email_verification"]["data"]["status"] == "valid"
    assert fake_hunter.verifier_calls == 1
    assert fake_hunter.domain_calls == 0


def test_domain_or_email_info_accepts_domain_and_verifies_found_email():
    fake_hunter = _FakeHunterClient()
    cache = _InMemoryCache()

    result = get_domain_or_email_info_cached(
        domain_or_email="example.com",
        hunter_client=fake_hunter,
        cache_store=cache,
        ttl_hours=24,
    )

    assert result["input_type"] == "domain"
    assert result["domain"] == "example.com"
    assert result["email"] == "contact@example.com"
    assert result["domain_search"]["data"]["domain"] == "example.com"
    assert result["email_verification"]["data"]["email"] == "contact@example.com"
    assert fake_hunter.domain_calls == 1
    assert fake_hunter.verifier_calls == 1


def test_domain_or_email_info_rejects_invalid_input():
    fake_hunter = _FakeHunterClient()
    cache = _InMemoryCache()

    try:
        get_domain_or_email_info_cached(
            domain_or_email="invalid",
            hunter_client=fake_hunter,
            cache_store=cache,
            ttl_hours=24,
        )
    except ValueError as exc:
        assert "domain format" in str(exc)
    else:
        raise AssertionError("Expected ValueError for invalid input")
