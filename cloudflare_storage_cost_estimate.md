# Cloudflare Storage Cost Estimate (KV vs D1 vs R2)

Date checked: 2026-03-04 (UTC)

## Assumptions
- Current deduplicated domain list in this repo: 124,109 domains.
- Serialized payload (newline-delimited): 2,008,671 bytes total (~0.001871 GB).
- Focus is **storage-only** cost in USD/month (not read/write/query operation costs).
- Cloudflare public pricing used from product docs pages (links below).

## Public pricing used (as of 2026-03-04)
- Workers KV: includes 1 GB, then **$0.50 per GB-month**.
- D1: includes 5 GB, then **$0.75 per GB-month**.
- R2 Standard: includes 10 GB-month, then **$0.015 per GB-month**.

## Estimated storage cost for current deduplicated list
- Estimated stored size: ~0.001871 GB.
- KV monthly storage: **$0.00** (well under included 1 GB).
- D1 monthly storage: **$0.00** (well under included 5 GB).
- R2 monthly storage: **$0.00** (well under included 10 GB-month).

## Rough scale example (for planning)
Assume 20 bytes/domain on average (domain + separator):
- 1,000,000 domains -> ~0.02 GB
- 100,000,000 domains -> ~2.0 GB

At ~2.0 GB stored:
- KV: (2.0 - 1.0) * $0.50 = **~$0.50/month**
- D1: within included 5 GB = **$0.00/month**
- R2: within included 10 GB-month = **$0.00/month**

## Bottom line
For the current deduplicated domain list size, storage cost is effectively **$0/month** on KV, D1, and R2. Even at very large list sizes (for example ~100M domains), raw storage charges remain low.

## Sources
- https://developers.cloudflare.com/kv/platform/pricing/
- https://developers.cloudflare.com/d1/platform/pricing/
- https://developers.cloudflare.com/r2/pricing/
