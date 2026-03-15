# CommonFunctions

Reusable Python utility functions for data provider projects.

This repository starts with email-focused helpers (for example, checking whether an email looks personalized) and will grow over time with other common utility functions.

## Goals

- Keep shared logic in one place instead of duplicating it across projects.
- Provide a stable package that other repositories can install.
- Support cloud-backed execution and storage for higher-cost data workflows.

## Planned Functionality

- `lookup_domain(domain: str, ...) -> dict`
- `lookup_email(email: str, ...) -> dict`
- `is_personalized_email(email: str) -> bool`
- `is_disposable_domain(domain_or_email: str) -> bool`
- `is_free_provider_domain(domain_or_email: str) -> bool`
- Additional common validation and normalization helpers (to be added).

## Local Development (venv)

```powershell
# from repository root
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

Run tests:

```powershell
pytest
```

## API Docs (pdoc)

Generate a single-file API reference:

```powershell
python scripts/generate_api_docs.py
```

Output file:

- `docs/API_REFERENCE.html`

Automatic updates on changes:

```powershell
pre-commit install
```

After hooks are installed, commits touching `src/common_functions/`, `pyproject.toml`, or `README.md` will regenerate API docs automatically.

Repository automation:

- GitHub Actions also regenerates and commits `docs/API_REFERENCE.html` automatically on pushes to `main` when relevant files change.

## Packaging Plan

This project is intended to be installable by other repositories from GitHub.

Quick install:

```powershell
pip install "git+https://github.com/benmtw/CommonFunctions.git"
```

`pyproject.toml` is included, so this repository can be installed directly from GitHub.

## Cloud Infrastructure

This project uses Cloudflare for selected runtime functions and supporting services.

- Some function-style workloads are intended to run via Cloudflare (for example Workers-based utility APIs).
- We also use Cloudflare data products for persisted datasets that are expensive to obtain (paid source data) or expensive to recompute.
- Typical storage targets may include Cloudflare data services such as D1, KV, and/or R2 depending on the access pattern and retention needs.

This approach helps control cost, reduce repeated extraction work, and improve performance for repeated lookups.

## Hunter.io Integration

Hunter.io is used occasionally for enrichment and email intelligence lookups.

- API base endpoint: `https://api.hunter.io/v2/`
- Authentication: API key required on each request.
- Hunter docs: `https://hunter.io/api-documentation#introduction`

To reduce paid API usage, Hunter responses should be cached/persisted in Cloudflare data products:

- Use `D1` for structured relational records and queryable enrichment history.
- Use `KV` for fast key-based lookup caches (for example, by domain/email hash).
- Use `R2` for larger raw payload snapshots or archival responses.

Recommended strategy:

1. Check Cloudflare cache/storage first.
2. Call Hunter only on cache miss or stale data.
3. Persist normalized result + retrieval timestamp + source metadata.
4. Apply TTL/refresh policy based on data volatility and credit cost.

This keeps recurring lookups cheaper and avoids recomputing/re-extracting expensive data.

## Domain Ratings + Naming Format (Merged Lists)

This repository now supports domain-level intelligence merged from historical
verification CSV exports under `millionverifierlists/lists`.

The lookup helper:

- `lookup_domain(...)`

returns:

- domain verdict (`good`/`risky`/`bad`)
- evidence counts and provider/schema coverage
- naming format summary and full format distribution with counts (for example
  `{first}{last}: 3`, `{first}_{last}: 1`)

Storage pattern:

- Cloudflare `D1` as source of truth for merged domain records
- Cloudflare `KV` as read-through cache

Optional fallback:

- If a domain is missing from D1/KV, pass `fallback_email` and a
  `MillionVerifierClient` to fetch a live result and persist it.

Required env vars for live fallback/store clients:

```text
MILLIONVERIFIER_API_KEY=...
CF_ACCOUNT_ID=...
CF_D1_DATABASE_ID=...
CF_API_TOKEN=...
```

Dataset build + sync commands:

```powershell
python scripts/build_domain_ratings_dataset.py
python scripts/sync_domain_ratings_to_d1.py --database <d1_db_name> --remote
```

### Intent-First API (Recommended)

Prefer these entrypoints for new integrations:

- `lookup_domain(...)`
- `lookup_email(...)`

They provide a stable, intent-first interface and route to the configured
backend source (`ratings` or `hunter`) while preserving backward compatibility
with existing lower-level helpers.

For `source="ratings"`, you can either:

- pass `d1_store=...` explicitly, or
- omit `d1_store` and let the helper initialize a Cloudflare D1 store from:
  - `CF_ACCOUNT_ID`
  - `CF_D1_DATABASE_ID`
  - `CF_API_TOKEN`

### Domain Redirect Detection & Content Verification

Two public functions for redirect detection and organisation verification:

| Function | Purpose |
|---|---|
| `check_redirect(...)` | Fetch a domain, detect redirects, and optionally verify the page belongs to a given organisation |
| `verify_domain_belongs_to_org(...)` | Verify page content belongs to an organisation **without** fetching — useful when you already have HTML/markdown from a crawl pipeline or cached fetch |

---

#### `check_redirect`

Fetches a domain using configurable strategies and reports whether it redirects elsewhere. Optionally runs LLM-based organisation verification on the fetched content.

**Basic usage:**

```python
from common_functions import check_redirect

# Local direct (stdlib urllib, fast and free)
result = check_redirect(domain="www.sns.hackney.sch.uk")
```

Schemes are stripped automatically, so `"https://www.sns.hackney.sch.uk/"` also works.

**Example result:**

| Field | Value |
|---|---|
| `domain` | `www.sns.hackney.sch.uk` |
| `redirects` | `True` |
| `final_domain` | `www.stokenewingtonschool.co.uk` |
| `redirect_chain` | `['https://www.sns.hackney.sch.uk', 'https://www.stokenewingtonschool.co.uk/']` |
| `status_code` | `301` |
| `strategy` | `local_direct` |
| `content` | *(38,710 chars of HTML)* |
| `verified` | `None` |
| `verification_reason` | `None` |

**More examples:**

```python
# Remote without JS rendering (fast, low cost)
result = check_redirect(domain="olddomain.com", strategy="remote_direct")

# Remote with headless browser (handles JS-heavy sites)
result = check_redirect(domain="olddomain.com", strategy="remote_headless")

# Fallback chain — try local first, then remote headless on failure
result = check_redirect(
    domain="www.sns.hackney.sch.uk",
    strategy=["local_direct", "remote_headless"],
)

# With organisation verification via LLM (auto-configured from env vars)
result = check_redirect(
    domain="www.sns.hackney.sch.uk",
    verify_org={
        "name": "Stoke Newington School and Sixth Form",
        "context": "UK secondary school and sixth form in Hackney, London",
    },
)

# With explicit LLM config (custom model/provider)
from common_functions import LlmVerifierConfig
result = check_redirect(
    domain="www.sns.hackney.sch.uk",
    verify_org={
        "name": "Stoke Newington School and Sixth Form",
        "context": "UK secondary school and sixth form in Hackney, London",
    },
    llm_config=LlmVerifierConfig(
        api_key="sk-xxx",
        base_url="https://api.openai.com/v1",
        model="gpt-4o-mini",
    ),
)
```

---

#### `verify_domain_belongs_to_org`

Verifies whether page content belongs to a specific organisation using the DSPy-powered LLM verifier. Does **not** fetch any URL — you supply the content directly. This is useful when you already have the HTML/markdown from another source (e.g. a crawl pipeline, cached fetch, or a prior `check_redirect` call).

**Basic usage:**

```python
from common_functions import check_redirect, verify_domain_belongs_to_org

# Fetch content separately (or use content you already have)
page = check_redirect(domain="www.stokenewingtonschool.co.uk")

# Verify against the correct owner
result = verify_domain_belongs_to_org(
    content=page["content"],
    org_info={
        "name": "Stoke Newington School and Sixth Form",
        "context": "UK secondary school and sixth form in Hackney, London",
    },
)
```

Returns a dict with two keys: `verified` (bool) and `reason` (str).

**Live example — correct vs incorrect owner:**

| Test | `org_info["name"]` | `verified` | `reason` |
|---|---|---|---|
| Correct owner | Stoke Newington School and Sixth Form | `True` | Title, URL, and theme path all confirm it belongs to the organisation |
| Wrong owner | All Saints Catholic High School | `False` | Page clearly identifies as Stoke Newington School, no mention of All Saints |

**With explicit LLM config:**

```python
from common_functions import LlmVerifierConfig, verify_domain_belongs_to_org

result = verify_domain_belongs_to_org(
    content="<html><title>Stoke Newington School</title>...</html>",
    org_info={
        "name": "Stoke Newington School and Sixth Form",
        "postcode": "N16 6BE",
        "context": "UK secondary school and sixth form in Hackney, London",
    },
    llm_config=LlmVerifierConfig(
        api_key="sk-xxx",
        base_url="https://api.openai.com/v1",
        model="gpt-4o-mini",
    ),
)
```

Omit `llm_config` to auto-configure from environment variables (see below).

---

#### Strategies

Pass one strategy or a list for automatic fallback:

| Strategy | How it works | Cost |
|---|---|---|
| `local_direct` | stdlib `urllib`, follows redirects | Free |
| `remote_direct` | Scrape.do **without** JS rendering | Low |
| `remote_headless` | Scrape.do **with** headless browser rendering | Higher |

SSL verification is disabled by default (`verify_ssl=False`).
When a list of strategies is provided, each is tried in order;
network/timeout errors trigger fallback to the next strategy.

#### Environment variables

**Remote strategies (Scrape.do):**

| Variable | Required | Default |
|---|---|---|
| `SCRAPE_DO_API_KEY` | Yes (for remote) | — |
| `SCRAPE_DO_GEO_CODE` | No | `gb` |

**LLM verification (Xiaomi MiMo):**

| Variable | Required | Default |
|---|---|---|
| `XIAOMI_API_KEY` | Yes (for verification) | — |
| `XIAOMI_BASE_URL` | No | `https://api.xiaomimimo.com/v1` |
| `XIAOMI_MODEL` | No | `mimo-v2-flash` |

**Optional dependency:** `pip install common-functions[redirects]` for DSPy-powered LLM verification support.

The verifier uses a typed DSPy `Signature` with `bool`/`str` output fields, giving you automatic output parsing and the ability to optimise prompts with DSPy optimisers (e.g. `MIPROv2`).

### Dataset Remark (2026-03-04)

The disposable domain dataset at `src/common_functions/data/disposable_domains.txt` was refreshed from the top 3 starred, actively maintained GitHub sources below, then merged and deduplicated:

1. `disposable-email-domains/disposable-email-domains`  
   Source file: `disposable_email_blocklist.conf`
2. `ivolo/disposable-email-domains`  
   Source file: `index.json`
3. `disposable/disposable`  
   Source file: `greylist.txt`

Current merged result:

- Unique domains: `124,109`
- File size: `2,008,671` bytes (about `1.92 MiB`)

Cloudflare storage-only monthly cost estimate for this file size is effectively `$0.00/month` on KV, D1, and R2 because it is below each product's included storage tier.  
Detailed assumptions and pricing references are recorded in `cloudflare_storage_cost_estimate.md`.

Lookup example:

- For `1,000` Cloudflare-backed lookups (KV/D1/R2 read patterns), expected incremental cost is typically `$0` because this volume is below standard free/included operation tiers.
- If those `1,000` are all cache misses and each includes one KV write, it is still typically within daily free write allowance.

### D1 Dataset Sync (Recommended)

To persist the disposable domain dataset in Cloudflare D1 (cheapest practical option for bulk load + lookup):

1. Create a D1 database (if needed):

```powershell
wrangler d1 create commonfunctions_disposable_domains
```

2. Import schema + dataset in batches from this repo:

```powershell
python scripts/sync_disposable_domains_to_d1.py --database commonfunctions_disposable_domains --remote
```

Useful options:

- `--chunk-size 5000` (default) controls rows per import batch.
- Omit `--remote` to target local wrangler D1.

3. Example lookup query:

```powershell
wrangler d1 execute commonfunctions_disposable_domains --remote --command "SELECT 1 FROM disposable_domains WHERE domain='mailinator.com' LIMIT 1;"
```

Schema file:

- `sql/d1_disposable_domains_schema.sql`

### Runtime Configuration

Set these environment variables where Hunter lookups run:

```text
HUNTER_API_KEY=...
CF_ACCOUNT_ID=...
CF_KV_NAMESPACE_ID=...
CF_API_TOKEN=...
```

### Python Usage Example

```python
from common_functions import (
    CloudflareKVConfig,
    CloudflareKVStore,
    get_domain_or_email_info_cached,
    HunterClient,
    get_domain_search_cached,
)

hunter = HunterClient.from_env()
kv_store = CloudflareKVStore(CloudflareKVConfig.from_env())

result = get_domain_search_cached(
    domain="example.com",
    hunter_client=hunter,
    cache_store=kv_store,
    ttl_hours=24 * 30,
)

verified = get_domain_or_email_info_cached(
    domain_or_email="person@example.com",  # also accepts "example.com"
    hunter_client=hunter,
    cache_store=kv_store,
    ttl_hours=24 * 30,
)
```

## Install In Other Projects

Use one of the following patterns in the consuming project.

`requirements.txt`:

```text
common-functions @ git+https://github.com/benmtw/CommonFunctions.git@main
```

`pyproject.toml` (PEP 508 direct reference):

```toml
[project]
dependencies = [
  "common-functions @ git+https://github.com/benmtw/CommonFunctions.git@main"
]
```

Pin to a tag for reproducible builds (recommended once releases are created):

```text
common-functions @ git+https://github.com/benmtw/CommonFunctions.git@v0.1.0
```

## Agent Instructions

Repository-specific AI agent workflow rules are in `AGENTS.md`.

## Suggested Project Structure

```text
CommonFunctions/
  src/
    common_functions/
      __init__.py
      email_utils.py
  tests/
    test_email_utils.py
  pyproject.toml
  README.md
```

## Useful GitHub References (Found via MCP)

- https://github.com/JoshData/python-email-validator  
  Robust Python email syntax/deliverability validation.
- https://github.com/disposable-email-domains/python-disposable-email-domains  
  Maintained disposable-domain dataset and Python access.
- https://github.com/michaelherold/pyIsEmail  
  Lightweight email validation approach.
- https://github.com/audreyfeldroy/cookiecutter-pypackage  
  Well-known Python package template.
- https://github.com/alvarobartt/python-package-template  
  Modern `pyproject.toml` + tooling template.

## Roadmap

1. Expand `email_utils.py` with additional detection rules and domain datasets.
2. Add CI (lint + tests) on pull requests.
3. Add semantic versioning and GitHub release workflow.
4. Document API changes as new helpers are added.
