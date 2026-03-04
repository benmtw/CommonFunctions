"""Cloudflare KV cache helpers."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from typing import Any
from urllib import error, parse, request


@dataclass(frozen=True)
class CloudflareKVConfig:
    """Configuration required for Cloudflare KV REST operations."""

    account_id: str
    namespace_id: str
    api_token: str

    @classmethod
    def from_env(cls) -> "CloudflareKVConfig":
        account_id = os.getenv("CF_ACCOUNT_ID", "").strip()
        namespace_id = os.getenv("CF_KV_NAMESPACE_ID", "").strip()
        api_token = os.getenv("CF_API_TOKEN", "").strip()
        missing = [
            name
            for name, value in (
                ("CF_ACCOUNT_ID", account_id),
                ("CF_KV_NAMESPACE_ID", namespace_id),
                ("CF_API_TOKEN", api_token),
            )
            if not value
        ]
        if missing:
            raise ValueError(f"Missing required Cloudflare env vars: {', '.join(missing)}")
        return cls(
            account_id=account_id,
            namespace_id=namespace_id,
            api_token=api_token,
        )


class CloudflareKVStore:
    """Cloudflare KV-backed cache implementation."""

    def __init__(self, config: CloudflareKVConfig, timeout_seconds: int = 15) -> None:
        self._config = config
        self._timeout_seconds = timeout_seconds

    def _key_url(self, key: str) -> str:
        encoded_key = parse.quote(key, safe="")
        return (
            "https://api.cloudflare.com/client/v4/accounts/"
            f"{self._config.account_id}/storage/kv/namespaces/"
            f"{self._config.namespace_id}/values/{encoded_key}"
        )

    def get(self, key: str) -> dict[str, Any] | None:
        req = request.Request(
            self._key_url(key),
            method="GET",
            headers={
                "Authorization": f"Bearer {self._config.api_token}",
            },
        )
        try:
            with request.urlopen(req, timeout=self._timeout_seconds) as resp:
                payload = resp.read().decode("utf-8")
        except error.HTTPError as exc:
            if exc.code == 404:
                return None
            raise
        if not payload:
            return None
        return json.loads(payload)

    def set(self, key: str, value: dict[str, Any]) -> None:
        body = json.dumps(value, separators=(",", ":")).encode("utf-8")
        req = request.Request(
            self._key_url(key),
            method="PUT",
            data=body,
            headers={
                "Authorization": f"Bearer {self._config.api_token}",
                "Content-Type": "application/json",
            },
        )
        with request.urlopen(req, timeout=self._timeout_seconds):
            return
