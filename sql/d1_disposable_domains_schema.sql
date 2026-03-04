-- D1 schema for disposable domain lookups
CREATE TABLE IF NOT EXISTS disposable_domains (
  domain TEXT PRIMARY KEY,
  source TEXT NOT NULL DEFAULT 'github-merged',
  imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_disposable_domains_domain
ON disposable_domains(domain);
