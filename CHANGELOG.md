# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Added
- `pdoc` API documentation automation:
  - `scripts/generate_api_docs.py`
  - `.pre-commit-config.yaml` hook to regenerate docs on commit
  - `.github/workflows/api-docs-check.yml` CI validation
  - `.github/workflows/api-docs-auto-update.yml` auto-commit on `main`
- Generated single-file API reference output:
  - `docs/API_REFERENCE.html`
- D1 disposable-domain sync tooling:
  - `sql/d1_disposable_domains_schema.sql`
  - `scripts/sync_disposable_domains_to_d1.py`
- Domain ratings and naming-format pipeline:
  - `src/common_functions/domain_ratings.py`
  - `scripts/build_domain_ratings_dataset.py`
  - `scripts/sync_domain_ratings_to_d1.py`
  - `sql/d1_domain_ratings_schema.sql`
- Intent-first lookup API:
  - `src/common_functions/lookups.py`
  - `lookup_domain(...)`
  - `lookup_email(...)`

### Changed
- Updated developer dependencies to include `pdoc` and `pre-commit`.
- Updated README with API docs generation and auto-update workflow.
- Updated README with D1 import and lookup commands for disposable-domain dataset.
- Updated D1 examples to use project-prefixed DB name: `commonfunctions_disposable_domains`.
- Improved D1 sync script compatibility for Windows `wrangler` resolution and D1 statement-size constraints.
- Expanded public module/function/class docstrings so generated `pdoc` API docs include richer usage and contract details.
- (2026-03-04) Added domain-first helper names:
  - `is_free_provider_domain(domain_or_email: str) -> bool`
  - `is_disposable_domain(domain_or_email: str) -> bool`
- (2026-03-04) Updated provider checks to accept either a domain string or an email string.
- (2026-03-04) Kept `is_free_provider_email(...)` and `is_disposable_email(...)` as backward-compatible wrappers.
- Added public API exports for domain ratings:
  - `CloudflareD1Config`
  - `CloudflareD1DomainRatingsStore`
  - `MillionVerifierClient`
- Added public intent-first exports:
  - `lookup_domain(...)`
  - `lookup_email(...)`
- Updated README with merged-domain-rating + naming-format usage and Cloudflare D1 sync steps.

### Fixed
- N/A

## [2026-03-04]

### Added
- Hunter email verification helpers:
  - `HunterClient.email_verifier(...)`
  - `get_email_verification_cached(...)`
  - `get_domain_or_email_info_cached(...)`
- New Cloudflare KV module:
  - `src/common_functions/cloudflare_kv.py`
- Cost estimate document:
  - `cloudflare_storage_cost_estimate.md`

### Changed
- Refreshed `disposable_domains.txt` using merged/deduplicated top GitHub sources.
- Split Cloudflare KV implementation from Hunter API logic.
- Added README notes for dataset provenance and Cloudflare lookup/storage cost expectations.
- Updated `AGENTS.md` to require changelog maintenance.

### Fixed
- N/A
