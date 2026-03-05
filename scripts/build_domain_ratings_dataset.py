"""Build merged domain ratings dataset from local verification CSV lists."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from common_functions.domain_ratings import (
    aggregate_domain_records,
    parse_evidence_from_csv_files,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Build merged domain ratings + naming-format distribution dataset "
            "from millionverifierlists CSV files."
        )
    )
    parser.add_argument(
        "--input-dir",
        default="millionverifierlists/lists",
        help="Directory containing source CSV files.",
    )
    parser.add_argument(
        "--output-jsonl",
        default="millionverifierlists/derived/domain_ratings.jsonl",
        help="Output JSONL path for domain aggregate records.",
    )
    parser.add_argument(
        "--summary-json",
        default="millionverifierlists/derived/domain_ratings_summary.json",
        help="Output JSON path for summary stats.",
    )
    args = parser.parse_args()

    input_dir = Path(args.input_dir).resolve()
    output_jsonl = Path(args.output_jsonl).resolve()
    summary_json = Path(args.summary_json).resolve()

    if not input_dir.exists() or not input_dir.is_dir():
        raise FileNotFoundError(f"Input directory not found: {input_dir}")

    csv_files = sorted(input_dir.glob("*.csv"))
    evidence_rows = parse_evidence_from_csv_files(csv_files)
    domain_records = aggregate_domain_records(evidence_rows)

    output_jsonl.parent.mkdir(parents=True, exist_ok=True)
    with output_jsonl.open("w", encoding="utf-8", newline="\n") as handle:
        for record in domain_records:
            handle.write(json.dumps(record, separators=(",", ":")) + "\n")

    summary = {
        "input_csv_files": len(csv_files),
        "evidence_rows_parsed": len(evidence_rows),
        "unique_domains": len(domain_records),
        "output_jsonl": str(output_jsonl),
    }
    summary_json.parent.mkdir(parents=True, exist_ok=True)
    summary_json.write_text(
        json.dumps(summary, indent=2) + "\n",
        encoding="utf-8",
    )

    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
