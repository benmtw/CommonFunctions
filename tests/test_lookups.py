from common_functions.lookups import lookup_domain, lookup_email


class _FakeHunterClient:
    def domain_search(self, domain: str):
        return {"data": {"domain": domain, "emails": [{"value": f"contact@{domain}"}]}}

    def email_verifier(self, email: str):
        return {"data": {"email": email, "status": "valid", "result": "deliverable"}}


class _InMemoryCache:
    def __init__(self):
        self.data = {}

    def get(self, key: str):
        return self.data.get(key)

    def set(self, key: str, value):
        self.data[key] = value


class _InMemoryDomainStore:
    def __init__(self, record: dict | None = None):
        self.record = record

    def get_domain_rating(self, domain: str):
        if self.record and self.record.get("domain") == domain:
            return self.record
        return None

    def upsert_domain_rating(self, record: dict):
        self.record = record


def _example_domain_record(domain: str) -> dict:
    return {
        "domain": domain,
        "verdict": "risky",
        "confidence": 61,
        "evidence_count": 2,
        "result_counts": {"risky": 2},
        "raw_result_counts": {"catch_all": 2},
        "provider_schema_counts": {"elv_style": 2},
        "has_free_provider_evidence": False,
        "has_role_evidence": False,
        "naming_format": {
            "primary_format_label": "{f}{last}",
            "primary_format_confidence": 100,
            "format_distribution": [{"format": "{f}{last}", "count": 2, "pct": 100.0}],
            "raw_naming_format_codes": {"2": 2},
        },
        "aggregated_at": "2026-03-05T00:00:00Z",
        "source": "historical-merged",
    }


def test_lookup_domain_ratings_source_returns_domain_record():
    store = _InMemoryDomainStore(_example_domain_record("example.com"))
    cache = _InMemoryCache()
    result = lookup_domain(
        domain="example.com",
        source="ratings",
        d1_store=store,
        kv_cache=cache,
    )
    assert result["status"] == "ok"
    assert result["verdict"] == "risky"


def test_lookup_domain_hunter_source_returns_hunter_payload():
    hunter = _FakeHunterClient()
    cache = _InMemoryCache()
    result = lookup_domain(
        domain="example.com",
        source="hunter",
        hunter_client=hunter,
        hunter_cache_store=cache,
    )
    assert result["input_type"] == "domain"
    assert result["domain_search"]["data"]["domain"] == "example.com"


def test_lookup_email_hunter_source_returns_email_payload():
    hunter = _FakeHunterClient()
    cache = _InMemoryCache()
    result = lookup_email(
        email="person@example.com",
        source="hunter",
        hunter_client=hunter,
        hunter_cache_store=cache,
    )
    assert result["input_type"] == "email"
    assert result["email"] == "person@example.com"


def test_lookup_email_ratings_source_uses_email_domain():
    store = _InMemoryDomainStore(_example_domain_record("example.com"))
    cache = _InMemoryCache()
    result = lookup_email(
        email="person@example.com",
        source="ratings",
        d1_store=store,
        kv_cache=cache,
    )
    assert result["status"] == "ok"
    assert result["input_domain"] == "example.com"


def test_lookup_domain_requires_store_for_ratings():
    try:
        lookup_domain(domain="example.com", source="ratings")
    except ValueError as exc:
        assert "d1_store" in str(exc)
    else:
        raise AssertionError("Expected ValueError when d1_store is missing")
