"""Sync local disposable domain dataset into Cloudflare D1 via wrangler."""

from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import subprocess
import tempfile


def _read_domains(path: Path) -> list[str]:
    domains: set[str] = set()
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip().lower()
        if not line or line.startswith("#"):
            continue
        domains.add(line)
    return sorted(domains)


def _chunks(items: list[str], size: int) -> list[list[str]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def _sql_escape(value: str) -> str:
    return value.replace("'", "''")


def _build_insert_sql(chunk: list[str], source_label: str) -> str:
    rows = ",\n".join(
        f"('{_sql_escape(domain)}','{_sql_escape(source_label)}')" for domain in chunk
    )
    return "INSERT OR IGNORE INTO disposable_domains (domain, source) VALUES\n" f"{rows};\n"


def _run(command: list[str], cwd: Path) -> None:
    subprocess.run(command, cwd=cwd, check=True)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Load src/common_functions/data/disposable_domains.txt into Cloudflare D1."
    )
    parser.add_argument(
        "--database",
        required=True,
        help="D1 database binding/name to pass to `wrangler d1 execute`.",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=5000,
        help="Rows per INSERT batch (default: 5000).",
    )
    parser.add_argument(
        "--remote",
        action="store_true",
        help="Execute against remote D1 (adds --remote).",
    )
    parser.add_argument(
        "--source-label",
        default="github-merged",
        help="Source label stored with each imported domain.",
    )
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    dataset_path = repo_root / "src" / "common_functions" / "data" / "disposable_domains.txt"
    schema_path = repo_root / "sql" / "d1_disposable_domains_schema.sql"

    wrangler_bin = shutil.which("wrangler") or shutil.which("wrangler.cmd")
    if not wrangler_bin:
        raise RuntimeError("`wrangler` CLI not found in PATH.")
    if not dataset_path.exists():
        raise FileNotFoundError(f"Dataset file not found: {dataset_path}")
    if not schema_path.exists():
        raise FileNotFoundError(f"Schema file not found: {schema_path}")

    domains = _read_domains(dataset_path)
    if not domains:
        raise RuntimeError("No domains found in dataset file.")
    batches = _chunks(domains, args.chunk_size)

    base = [wrangler_bin, "d1", "execute", args.database]
    if args.remote:
        base.append("--remote")

    # Ensure table and index exist.
    _run([*base, f"--file={schema_path}"], cwd=repo_root)

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        for index, batch in enumerate(batches, start=1):
            sql_file = tmp_dir / f"import_{index:05d}.sql"
            sql_file.write_text(
                _build_insert_sql(chunk=batch, source_label=args.source_label),
                encoding="utf-8",
            )
            _run([*base, f"--file={sql_file}"], cwd=repo_root)
            print(f"Imported batch {index}/{len(batches)} ({len(batch)} rows)")

    print(f"Completed D1 sync: {len(domains)} unique domains.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
