from pathlib import Path
import uuid

from common_functions.domain_ratings import (
    aggregate_domain_records,
    get_domain_rating_info_cached,
    parse_evidence_from_csv_files,
)


class _InMemoryCache:
    def __init__(self):
        self.data = {}

    def get(self, key: str):
        return self.data.get(key)

    def set(self, key: str, value):
        self.data[key] = value


class _InMemoryDomainStore:
    def __init__(self, records: list[dict] | None = None):
        self.records = {record["domain"]: record for record in (records or [])}

    def get_domain_rating(self, domain: str):
        return self.records.get(domain)

    def upsert_domain_rating(self, record: dict):
        self.records[record["domain"]] = record


class _FakeMillionVerifierClient:
    def __init__(self):
        self.calls = 0

    def verify_email(self, email: str):
        self.calls += 1
        return {"result": "ok", "email": email}


def _write_csv(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8", newline="\n")


def _repo_temp_file(name_prefix: str) -> Path:
    return Path("tests") / f"{name_prefix}_{uuid.uuid4().hex}.csv"


def test_parse_evidence_handles_mv_and_elv_header_variants():
    mv_file = _repo_temp_file("mv")
    _write_csv(
        mv_file,
        'Email,quality,result,free,role\n'
        "john_smith@example.com,good,ok,yes,no\n",
    )
    elv_file = _repo_temp_file("elv")
    _write_csv(
        elv_file,
        "Email,result,EmailDomain,NamingFormat\n"
        "jsmith@example.com,ok,example.com,2\n",
    )
    try:
        rows = parse_evidence_from_csv_files([mv_file, elv_file])
        assert len(rows) == 2
        assert {row.provider_schema for row in rows} == {"mv_style", "elv_style"}
        assert {row.domain for row in rows} == {"example.com"}
    finally:
        if mv_file.exists():
            mv_file.unlink()
        if elv_file.exists():
            elv_file.unlink()


def test_aggregate_domain_records_deduplicates_email_plus_result():
    csv_file = _repo_temp_file("dedupe")
    _write_csv(
        csv_file,
        "Email,result,EmailDomain,NamingFormat\n"
        "johnsmith@example.com,ok,example.com,3\n"
        "johnsmith@example.com,ok,example.com,3\n"
        "johnsmith@example.com,invalid,example.com,3\n",
    )
    try:
        parsed = parse_evidence_from_csv_files([csv_file])
        records = aggregate_domain_records(parsed)
        assert len(records) == 1
        record = records[0]
        assert record["domain"] == "example.com"
        # one 'ok' + one 'invalid' after dedupe
        assert record["evidence_count"] == 2
        assert record["result_counts"]["good"] == 1
        assert record["result_counts"]["bad"] == 1
        assert record["verdict"] == "bad"
    finally:
        if csv_file.exists():
            csv_file.unlink()


def test_multi_format_distribution_is_returned_with_counts():
    csv_file = _repo_temp_file("formats")
    _write_csv(
        csv_file,
        "Email,result,EmailDomain,NamingFormat\n"
        "johnsmith@company.com,ok,company.com,3\n"
        "janesmith@company.com,ok,company.com,3\n"
        "joebloggs@company.com,ok,company.com,3\n"
        "john_smith@company.com,ok,company.com,11\n",
    )
    try:
        parsed = parse_evidence_from_csv_files([csv_file])
        records = aggregate_domain_records(parsed)
        record = records[0]
        distribution = {
            row["format"]: row["count"] for row in record["naming_format"]["format_distribution"]
        }
        assert distribution["{first}{last}"] == 3
        assert distribution["{first}_{last}"] == 1
    finally:
        if csv_file.exists():
            csv_file.unlink()


def test_lookup_uses_cache_then_store():
    record = {
        "domain": "example.com",
        "verdict": "risky",
        "confidence": 60,
        "evidence_count": 5,
        "result_counts": {"risky": 5},
        "raw_result_counts": {"catch_all": 5},
        "provider_schema_counts": {"mv_style": 5},
        "has_free_provider_evidence": False,
        "has_role_evidence": False,
        "naming_format": {
            "primary_format_label": "{f}{last}",
            "primary_format_confidence": 70,
            "format_distribution": [{"format": "{f}{last}", "count": 5, "pct": 100.0}],
            "raw_naming_format_codes": {"2": 5},
        },
        "aggregated_at": "2026-03-05T00:00:00Z",
        "source": "historical-merged",
    }
    store = _InMemoryDomainStore([record])
    cache = _InMemoryCache()

    first = get_domain_rating_info_cached(
        domain="example.com",
        d1_store=store,
        kv_cache=cache,
    )
    second = get_domain_rating_info_cached(
        domain="example.com",
        d1_store=store,
        kv_cache=cache,
    )

    assert first["status"] == "ok"
    assert first["cache"] == "miss"
    assert second["status"] == "ok"
    assert second["cache"] == "hit"


def test_lookup_fallback_requires_matching_email_domain():
    store = _InMemoryDomainStore()
    cache = _InMemoryCache()
    fake_client = _FakeMillionVerifierClient()
    try:
        get_domain_rating_info_cached(
            domain="example.com",
            d1_store=store,
            kv_cache=cache,
            millionverifier_client=fake_client,
            fallback_email="person@other.com",
        )
    except ValueError as exc:
        assert "must match requested domain" in str(exc)
    else:
        raise AssertionError("Expected ValueError for mismatched fallback domain")


def test_lookup_fallback_fetches_and_persists_when_not_found():
    store = _InMemoryDomainStore()
    cache = _InMemoryCache()
    fake_client = _FakeMillionVerifierClient()

    result = get_domain_rating_info_cached(
        domain="example.com",
        d1_store=store,
        kv_cache=cache,
        millionverifier_client=fake_client,
        fallback_email="jsmith@example.com",
    )

    assert result["status"] == "fallback"
    assert result["fallback_used"] is True
    assert fake_client.calls == 1
    assert store.get_domain_rating("example.com") is not None
    assert result["naming_format"]["format_distribution"][0]["count"] == 1
