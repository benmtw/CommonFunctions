-- D1 schema for merged domain ratings and naming-format distributions
CREATE TABLE IF NOT EXISTS domain_ratings (
  domain TEXT PRIMARY KEY,
  verdict TEXT NOT NULL,
  confidence INTEGER NOT NULL,
  evidence_count INTEGER NOT NULL,
  result_counts_json TEXT NOT NULL,
  raw_result_counts_json TEXT NOT NULL,
  provider_schema_counts_json TEXT NOT NULL,
  has_free_provider_evidence INTEGER NOT NULL,
  has_role_evidence INTEGER NOT NULL,
  naming_format_primary_label TEXT NOT NULL,
  naming_format_primary_confidence INTEGER NOT NULL,
  naming_format_distribution_json TEXT NOT NULL,
  raw_naming_format_codes_json TEXT NOT NULL,
  aggregated_at TEXT NOT NULL,
  source TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_domain_ratings_verdict
ON domain_ratings(verdict);
