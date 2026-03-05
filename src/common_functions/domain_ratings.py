"""Domain ratings and naming-format helpers.

This module provides:
- domain-level aggregation of historical email verification evidence,
- naming-format inference/distribution per domain,
- Cloudflare D1 + KV-backed lookup helpers,
- MillionVerifier live fallback for domain misses (email-driven).
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import csv
import json
import os
from pathlib import Path
import re
from typing import Any, Iterable, Protocol
from urllib import parse, request


RESULT_TO_QUALITY = {
    "ok": "good",
    "catch_all": "risky",
    "accept_all": "risky",
    "ok_for_all": "risky",
    "unknown": "risky",
    "invalid": "bad",
    "invalid_mx": "bad",
    "email_disabled": "bad",
    "dead_server": "bad",
    "disposable": "bad",
}

_FORMAT_PRECEDENCE = [
    "{first}.{last}",
    "{first}_{last}",
    "{first}-{last}",
    "{first}{last}",
    "{f}{last}",
    "{f}.{last}",
    "{f}_{last}",
    "{first}{l}",
    "{first}",
    "{last}{f}",
    "other",
    "unknown",
]

_NAMING_CODE_TO_FORMAT = {
    "1": "{first}",
    "2": "{f}{last}",
    "7": "{first}.{last}",
    "8": "{last}{f}",
}

D1_DOMAIN_RATINGS_TABLE = "domain_ratings"


class CacheStore(Protocol):
    """Minimal JSON cache contract used by lookup helpers."""

    def get(self, key: str) -> dict[str, Any] | None:
        """Return cached payload for key, or None if not found."""

    def set(self, key: str, value: dict[str, Any]) -> None:
        """Persist payload for key."""


class DomainRatingsStore(Protocol):
    """Domain ratings storage contract."""

    def get_domain_rating(self, domain: str) -> dict[str, Any] | None:
        """Return an aggregated domain rating record."""

    def upsert_domain_rating(self, record: dict[str, Any]) -> None:
        """Insert/update an aggregated domain rating record."""


@dataclass(frozen=True)
class CloudflareD1Config:
    """Configuration required for Cloudflare D1 REST operations."""

    account_id: str
    database_id: str
    api_token: str

    @classmethod
    def from_env(cls) -> "CloudflareD1Config":
        """Load D1 configuration from environment variables.

        Required variables:
        - ``CF_ACCOUNT_ID``
        - ``CF_D1_DATABASE_ID``
        - ``CF_API_TOKEN``
        """
        account_id = os.getenv("CF_ACCOUNT_ID", "").strip()
        database_id = os.getenv("CF_D1_DATABASE_ID", "").strip()
        api_token = os.getenv("CF_API_TOKEN", "").strip()
        missing = [
            name
            for name, value in (
                ("CF_ACCOUNT_ID", account_id),
                ("CF_D1_DATABASE_ID", database_id),
                ("CF_API_TOKEN", api_token),
            )
            if not value
        ]
        if missing:
            raise ValueError(f"Missing required Cloudflare env vars: {', '.join(missing)}")
        return cls(
            account_id=account_id,
            database_id=database_id,
            api_token=api_token,
        )


class CloudflareD1DomainRatingsStore:
    """Cloudflare D1-backed domain ratings store."""

    def __init__(self, config: CloudflareD1Config, timeout_seconds: int = 20) -> None:
        self._config = config
        self._timeout_seconds = timeout_seconds

    def _query_url(self) -> str:
        return (
            "https://api.cloudflare.com/client/v4/accounts/"
            f"{self._config.account_id}/d1/database/{self._config.database_id}/query"
        )

    def _execute(self, sql: str, params: list[Any] | None = None) -> list[dict[str, Any]]:
        body = json.dumps(
            {
                "sql": sql,
                "params": params or [],
            },
            separators=(",", ":"),
        ).encode("utf-8")
        req = request.Request(
            self._query_url(),
            method="POST",
            data=body,
            headers={
                "Authorization": f"Bearer {self._config.api_token}",
                "Content-Type": "application/json",
            },
        )
        with request.urlopen(req, timeout=self._timeout_seconds) as resp:
            payload = json.loads(resp.read().decode("utf-8"))

        result = payload.get("result")
        if not isinstance(result, list) or not result:
            return []
        first = result[0]
        if not isinstance(first, dict):
            return []
        rows = first.get("results")
        if isinstance(rows, list):
            return [row for row in rows if isinstance(row, dict)]
        return []

    def get_domain_rating(self, domain: str) -> dict[str, Any] | None:
        normalized = _normalize_domain(domain)
        sql = (
            "SELECT domain, verdict, confidence, evidence_count, result_counts_json, "
            "raw_result_counts_json, provider_schema_counts_json, has_free_provider_evidence, "
            "has_role_evidence, naming_format_primary_label, naming_format_primary_confidence, "
            "naming_format_distribution_json, raw_naming_format_codes_json, aggregated_at, source "
            f"FROM {D1_DOMAIN_RATINGS_TABLE} WHERE domain = ? LIMIT 1"
        )
        rows = self._execute(sql, [normalized])
        if not rows:
            return None
        row = rows[0]
        return {
            "domain": row["domain"],
            "verdict": row["verdict"],
            "confidence": int(row["confidence"]),
            "evidence_count": int(row["evidence_count"]),
            "result_counts": json.loads(row["result_counts_json"]),
            "raw_result_counts": json.loads(row["raw_result_counts_json"]),
            "provider_schema_counts": json.loads(row["provider_schema_counts_json"]),
            "has_free_provider_evidence": bool(int(row["has_free_provider_evidence"])),
            "has_role_evidence": bool(int(row["has_role_evidence"])),
            "naming_format": {
                "primary_format_label": row["naming_format_primary_label"],
                "primary_format_confidence": int(row["naming_format_primary_confidence"]),
                "format_distribution": json.loads(row["naming_format_distribution_json"]),
                "raw_naming_format_codes": json.loads(row["raw_naming_format_codes_json"]),
            },
            "aggregated_at": row["aggregated_at"],
            "source": row["source"],
        }

    def upsert_domain_rating(self, record: dict[str, Any]) -> None:
        naming = record.get("naming_format", {})
        sql = (
            f"INSERT INTO {D1_DOMAIN_RATINGS_TABLE} ("
            "domain, verdict, confidence, evidence_count, result_counts_json, "
            "raw_result_counts_json, provider_schema_counts_json, has_free_provider_evidence, "
            "has_role_evidence, naming_format_primary_label, naming_format_primary_confidence, "
            "naming_format_distribution_json, raw_naming_format_codes_json, aggregated_at, source"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(domain) DO UPDATE SET "
            "verdict=excluded.verdict, confidence=excluded.confidence, "
            "evidence_count=excluded.evidence_count, "
            "result_counts_json=excluded.result_counts_json, "
            "raw_result_counts_json=excluded.raw_result_counts_json, "
            "provider_schema_counts_json=excluded.provider_schema_counts_json, "
            "has_free_provider_evidence=excluded.has_free_provider_evidence, "
            "has_role_evidence=excluded.has_role_evidence, "
            "naming_format_primary_label=excluded.naming_format_primary_label, "
            "naming_format_primary_confidence=excluded.naming_format_primary_confidence, "
            "naming_format_distribution_json=excluded.naming_format_distribution_json, "
            "raw_naming_format_codes_json=excluded.raw_naming_format_codes_json, "
            "aggregated_at=excluded.aggregated_at, source=excluded.source"
        )
        self._execute(
            sql,
            [
                record["domain"],
                record["verdict"],
                int(record["confidence"]),
                int(record["evidence_count"]),
                json.dumps(record["result_counts"], separators=(",", ":")),
                json.dumps(record["raw_result_counts"], separators=(",", ":")),
                json.dumps(record["provider_schema_counts"], separators=(",", ":")),
                1 if record["has_free_provider_evidence"] else 0,
                1 if record["has_role_evidence"] else 0,
                naming.get("primary_format_label", "unknown"),
                int(naming.get("primary_format_confidence", 0)),
                json.dumps(naming.get("format_distribution", []), separators=(",", ":")),
                json.dumps(naming.get("raw_naming_format_codes", {}), separators=(",", ":")),
                record["aggregated_at"],
                record["source"],
            ],
        )


class MillionVerifierClient:
    """Minimal MillionVerifier API client (single-email verification)."""

    _BASE_URL = "https://api.millionverifier.com/api/v3/"

    def __init__(self, api_key: str, timeout_seconds: int = 20) -> None:
        api_key = api_key.strip()
        if not api_key:
            raise ValueError("MillionVerifier API key is required.")
        self._api_key = api_key
        self._timeout_seconds = timeout_seconds

    @classmethod
    def from_env(cls) -> "MillionVerifierClient":
        """Build a client from ``MILLIONVERIFIER_API_KEY``."""
        api_key = os.getenv("MILLIONVERIFIER_API_KEY", "").strip()
        if not api_key:
            raise ValueError("Missing required env var: MILLIONVERIFIER_API_KEY")
        return cls(api_key=api_key)

    def verify_email(self, email: str) -> dict[str, Any]:
        """Verify one email address via MillionVerifier."""
        normalized = _normalize_email(email)
        query = parse.urlencode(
            {
                "api": self._api_key,
                "email": normalized,
            }
        )
        url = f"{self._BASE_URL}?{query}"
        req = request.Request(url, method="GET")
        with request.urlopen(req, timeout=self._timeout_seconds) as resp:
            payload = resp.read().decode("utf-8")
        return json.loads(payload)


@dataclass(frozen=True)
class _EvidenceRow:
    domain: str
    email: str
    provider_schema: str
    raw_result: str
    normalized_result: str
    is_free_provider: bool | None
    is_role_address: bool | None
    raw_naming_format_code: str | None


def _normalize_domain(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("Domain must be a string.")
    normalized = value.strip().lower()
    if not normalized:
        raise ValueError("Domain is required.")
    if "@" in normalized:
        raise ValueError("Expected a domain, not an email address.")
    if "." not in normalized or normalized.startswith(".") or normalized.endswith("."):
        raise ValueError("Invalid domain format.")
    if ".." in normalized:
        raise ValueError("Invalid domain format.")
    return normalized


def _normalize_email(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("Email must be a string.")
    normalized = value.strip().lower()
    if normalized.count("@") != 1:
        raise ValueError("Invalid email format.")
    local, domain = normalized.split("@", 1)
    if not local or not domain:
        raise ValueError("Invalid email format.")
    _normalize_domain(domain)
    return normalized


def _parse_bool(value: str) -> bool | None:
    lowered = value.strip().lower()
    if lowered in {"yes", "true", "1"}:
        return True
    if lowered in {"no", "false", "0"}:
        return False
    return None


def _normalize_result(raw: str) -> str:
    lowered = raw.strip().lower()
    if not lowered:
        return "risky"
    return RESULT_TO_QUALITY.get(lowered, "risky")


def _infer_format_from_local(local_part: str) -> str:
    local = local_part.strip().lower()
    if not local:
        return "unknown"
    if "." in local:
        parts = [part for part in local.split(".") if part]
        if len(parts) == 2 and all(part.isalpha() for part in parts):
            if len(parts[0]) == 1:
                return "{f}.{last}"
            return "{first}.{last}"
        return "other"
    if "_" in local:
        parts = [part for part in local.split("_") if part]
        if len(parts) == 2 and all(part.isalpha() for part in parts):
            if len(parts[0]) == 1:
                return "{f}_{last}"
            return "{first}_{last}"
        return "other"
    if "-" in local:
        parts = [part for part in local.split("-") if part]
        if len(parts) == 2 and all(part.isalpha() for part in parts):
            return "{first}-{last}"
        return "other"
    if re.fullmatch(r"[a-z]+", local) is None:
        return "other"
    if len(local) == 1:
        return "{first}"
    if 2 <= len(local) <= 4:
        return "{f}{last}"
    if len(local) >= 9:
        return "{first}{last}"
    return "{f}{last}"


def _resolve_naming_format(raw_code: str | None, email: str) -> str:
    if raw_code is not None:
        normalized_code = raw_code.strip()
        if normalized_code in _NAMING_CODE_TO_FORMAT:
            return _NAMING_CODE_TO_FORMAT[normalized_code]
    local = email.split("@", 1)[0]
    return _infer_format_from_local(local)


def _detect_provider_schema(field_names: set[str]) -> str:
    lowered = {field.lower() for field in field_names}
    if {"quality", "result", "free", "role"}.issubset(lowered):
        return "mv_style"
    if "result" in lowered and "emaildomain" in lowered:
        return "elv_style"
    return "other_style"


def _extract_evidence(row: dict[str, str], provider_schema: str) -> _EvidenceRow | None:
    row_l = {
        key.lower(): (value or "").strip()
        for key, value in row.items()
        if isinstance(key, str) and key.strip()
    }
    email = row_l.get("email") or row_l.get("generatedemail")
    if not email:
        return None
    try:
        normalized_email = _normalize_email(email)
    except ValueError:
        return None

    domain = row_l.get("emaildomain", "")
    if domain:
        try:
            normalized_domain = _normalize_domain(domain)
        except ValueError:
            normalized_domain = normalized_email.split("@", 1)[1]
    else:
        normalized_domain = normalized_email.split("@", 1)[1]

    raw_result = row_l.get("result") or row_l.get("emailresult") or ""
    normalized_result = _normalize_result(raw_result)
    free = _parse_bool(row_l.get("free", ""))
    role = _parse_bool(row_l.get("role", ""))
    raw_naming_format_code = row_l.get("namingformat")
    if raw_naming_format_code:
        raw_naming_format_code = raw_naming_format_code.strip()
    else:
        raw_naming_format_code = None
    return _EvidenceRow(
        domain=normalized_domain,
        email=normalized_email,
        provider_schema=provider_schema,
        raw_result=raw_result.strip().lower(),
        normalized_result=normalized_result,
        is_free_provider=free,
        is_role_address=role,
        raw_naming_format_code=raw_naming_format_code,
    )


def _score_confidence(
    *,
    evidence_count: int,
    schema_count: int,
    result_counts: dict[str, int],
) -> int:
    score = 50
    if evidence_count >= 5:
        score += 20
    if evidence_count >= 20:
        score += 10
    if schema_count >= 2:
        score += 10
    if result_counts.get("good", 0) > 0 and result_counts.get("bad", 0) > 0:
        score -= 15
    return max(0, min(100, score))


def _choose_primary_format(format_counts: Counter[str]) -> str:
    if not format_counts:
        return "unknown"
    precedence = {value: index for index, value in enumerate(_FORMAT_PRECEDENCE)}
    items = sorted(
        format_counts.items(),
        key=lambda item: (-item[1], precedence.get(item[0], len(precedence))),
    )
    return items[0][0]


def _build_distribution(format_counts: Counter[str]) -> list[dict[str, Any]]:
    total = sum(format_counts.values())
    if total <= 0:
        return [{"format": "unknown", "count": 0, "pct": 0.0}]
    precedence = {value: index for index, value in enumerate(_FORMAT_PRECEDENCE)}
    ordered = sorted(
        format_counts.items(),
        key=lambda item: (-item[1], precedence.get(item[0], len(precedence))),
    )
    return [
        {
            "format": fmt,
            "count": count,
            "pct": round((count / total) * 100.0, 2),
        }
        for fmt, count in ordered
    ]


def aggregate_domain_records(evidences: Iterable[_EvidenceRow]) -> list[dict[str, Any]]:
    """Aggregate evidence rows into domain-level records.

    Rows are deduplicated per domain using ``(email, normalized_result)``.
    """
    grouped: dict[str, list[_EvidenceRow]] = defaultdict(list)
    for row in evidences:
        grouped[row.domain].append(row)

    now_iso = datetime.now(tz=timezone.utc).isoformat().replace("+00:00", "Z")
    records: list[dict[str, Any]] = []

    for domain, rows in grouped.items():
        seen: set[tuple[str, str]] = set()
        result_counts: Counter[str] = Counter()
        raw_result_counts: Counter[str] = Counter()
        schema_counts: Counter[str] = Counter()
        format_counts: Counter[str] = Counter()
        raw_codes: Counter[str] = Counter()
        has_free = False
        has_role = False

        for row in rows:
            dedupe_key = (row.email, row.normalized_result)
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            result_counts[row.normalized_result] += 1
            if row.raw_result:
                raw_result_counts[row.raw_result] += 1
            schema_counts[row.provider_schema] += 1
            if row.is_free_provider is True:
                has_free = True
            if row.is_role_address is True:
                has_role = True
            fmt = _resolve_naming_format(row.raw_naming_format_code, row.email)
            format_counts[fmt] += 1
            if row.raw_naming_format_code:
                raw_codes[row.raw_naming_format_code] += 1

        evidence_count = sum(result_counts.values())
        if result_counts.get("bad", 0) > 0:
            verdict = "bad"
        elif result_counts.get("risky", 0) > 0:
            verdict = "risky"
        else:
            verdict = "good"

        primary_format = _choose_primary_format(format_counts)
        distribution = _build_distribution(format_counts)
        primary_count = int(format_counts.get(primary_format, 0))
        format_confidence = int(
            round((primary_count / max(1, sum(format_counts.values()))) * 100)
        )

        records.append(
            {
                "domain": domain,
                "verdict": verdict,
                "confidence": _score_confidence(
                    evidence_count=evidence_count,
                    schema_count=len(schema_counts),
                    result_counts=dict(result_counts),
                ),
                "evidence_count": evidence_count,
                "result_counts": dict(result_counts),
                "raw_result_counts": dict(raw_result_counts),
                "provider_schema_counts": dict(schema_counts),
                "has_free_provider_evidence": has_free,
                "has_role_evidence": has_role,
                "naming_format": {
                    "primary_format_label": primary_format,
                    "primary_format_confidence": format_confidence,
                    "format_distribution": distribution,
                    "raw_naming_format_codes": dict(raw_codes),
                },
                "aggregated_at": now_iso,
                "source": "historical-merged",
            }
        )
    return sorted(records, key=lambda record: record["domain"])


def parse_evidence_from_csv_files(file_paths: Iterable[Path]) -> list[_EvidenceRow]:
    """Parse evidence rows from heterogeneous provider CSV exports."""
    parsed: list[_EvidenceRow] = []
    for path in file_paths:
        if path.suffix.lower() != ".csv":
            continue
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if not reader.fieldnames:
                continue
            provider_schema = _detect_provider_schema(set(reader.fieldnames))
            for row in reader:
                evidence = _extract_evidence(row, provider_schema=provider_schema)
                if evidence is not None:
                    parsed.append(evidence)
    return parsed


def _is_stale(record: dict[str, Any], now: datetime) -> bool:
    expires_at = record.get("expires_at")
    if not isinstance(expires_at, str):
        return True
    try:
        expiry = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
    except ValueError:
        return True
    return now >= expiry


def _cache_key_for_domain(domain: str) -> str:
    return f"domain-rating:v1:{domain}"


def _response_from_record(
    *,
    input_domain: str,
    status: str,
    cache_state: str,
    record: dict[str, Any] | None,
    fallback_used: bool,
    raw_provider_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if record is None:
        return {
            "input_domain": input_domain,
            "status": status,
            "verdict": None,
            "confidence": None,
            "evidence_count": 0,
            "result_counts": {},
            "provider_schema_counts": {},
            "has_free_provider_evidence": False,
            "has_role_evidence": False,
            "naming_format": {
                "primary_format_label": "unknown",
                "primary_format_confidence": 0,
                "format_distribution": [{"format": "unknown", "count": 0, "pct": 0.0}],
                "raw_naming_format_codes": {},
            },
            "source": None,
            "cache": cache_state,
            "retrieved_at": datetime.now(tz=timezone.utc).isoformat().replace("+00:00", "Z"),
            "fallback_used": fallback_used,
            "raw_provider_payload": raw_provider_payload,
        }
    return {
        "input_domain": input_domain,
        "status": status,
        "verdict": record["verdict"],
        "confidence": record["confidence"],
        "evidence_count": record["evidence_count"],
        "result_counts": record["result_counts"],
        "provider_schema_counts": record["provider_schema_counts"],
        "has_free_provider_evidence": record["has_free_provider_evidence"],
        "has_role_evidence": record["has_role_evidence"],
        "naming_format": record["naming_format"],
        "source": record["source"],
        "cache": cache_state,
        "retrieved_at": datetime.now(tz=timezone.utc).isoformat().replace("+00:00", "Z"),
        "fallback_used": fallback_used,
        "raw_provider_payload": raw_provider_payload,
    }


def _record_from_fallback(
    *,
    domain: str,
    email: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    raw_result = str(payload.get("result", "")).strip().lower()
    normalized_result = _normalize_result(raw_result)
    if normalized_result == "bad":
        verdict = "bad"
    elif normalized_result == "risky":
        verdict = "risky"
    else:
        verdict = "good"
    fmt = _resolve_naming_format(None, email)
    return {
        "domain": domain,
        "verdict": verdict,
        "confidence": 55,
        "evidence_count": 1,
        "result_counts": {normalized_result: 1},
        "raw_result_counts": {raw_result or "unknown": 1},
        "provider_schema_counts": {"millionverifier_live": 1},
        "has_free_provider_evidence": False,
        "has_role_evidence": False,
        "naming_format": {
            "primary_format_label": fmt,
            "primary_format_confidence": 100,
            "format_distribution": [{"format": fmt, "count": 1, "pct": 100.0}],
            "raw_naming_format_codes": {},
        },
        "aggregated_at": datetime.now(tz=timezone.utc).isoformat().replace("+00:00", "Z"),
        "source": "millionverifier-live",
    }


def get_domain_rating_info_cached(
    *,
    domain: str,
    d1_store: DomainRatingsStore,
    kv_cache: CacheStore | None = None,
    millionverifier_client: MillionVerifierClient | None = None,
    fallback_email: str | None = None,
    ttl_hours: int = 24 * 30,
) -> dict[str, Any]:
    """Return domain rating and naming-format info with cache-first behavior.

    Lookup order:
    1) KV cache (optional)
    2) D1 store
    3) MillionVerifier fallback only if ``fallback_email`` is provided and the
       client is available.
    """
    normalized_domain = _normalize_domain(domain)
    cache_key = _cache_key_for_domain(normalized_domain)
    now = datetime.now(tz=timezone.utc)

    if kv_cache is not None:
        cached = kv_cache.get(cache_key)
        if cached and not _is_stale(cached, now):
            return _response_from_record(
                input_domain=normalized_domain,
                status="ok",
                cache_state="hit",
                record=cached.get("result"),
                fallback_used=False,
            )

    record = d1_store.get_domain_rating(normalized_domain)
    if record is not None:
        if kv_cache is not None:
            expires = now + timedelta(hours=ttl_hours)
            kv_cache.set(
                cache_key,
                {
                    "source": record.get("source", "domain-ratings"),
                    "retrieved_at": now.isoformat().replace("+00:00", "Z"),
                    "expires_at": expires.isoformat().replace("+00:00", "Z"),
                    "result": record,
                },
            )
        return _response_from_record(
            input_domain=normalized_domain,
            status="ok",
            cache_state="miss",
            record=record,
            fallback_used=False,
        )

    if fallback_email and millionverifier_client is not None:
        normalized_email = _normalize_email(fallback_email)
        email_domain = normalized_email.split("@", 1)[1]
        if email_domain != normalized_domain:
            raise ValueError("fallback_email domain must match requested domain.")
        payload = millionverifier_client.verify_email(normalized_email)
        fallback_record = _record_from_fallback(
            domain=normalized_domain,
            email=normalized_email,
            payload=payload,
        )
        d1_store.upsert_domain_rating(fallback_record)
        if kv_cache is not None:
            expires = now + timedelta(hours=ttl_hours)
            kv_cache.set(
                cache_key,
                {
                    "source": fallback_record["source"],
                    "retrieved_at": now.isoformat().replace("+00:00", "Z"),
                    "expires_at": expires.isoformat().replace("+00:00", "Z"),
                    "result": fallback_record,
                },
            )
        return _response_from_record(
            input_domain=normalized_domain,
            status="fallback",
            cache_state="miss",
            record=fallback_record,
            fallback_used=True,
            raw_provider_payload=payload,
        )

    return _response_from_record(
        input_domain=normalized_domain,
        status="not_found",
        cache_state="miss",
        record=None,
        fallback_used=False,
    )
