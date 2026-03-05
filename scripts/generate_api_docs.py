"""Generate single-file API documentation with pdoc."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    docs_dir = repo_root / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    output_file = docs_dir / "API_REFERENCE.html"

    with tempfile.TemporaryDirectory() as tmp:
        temp_dir = Path(tmp)
        env = dict(os.environ)
        src_path = str(repo_root / "src")
        existing_pythonpath = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = src_path if not existing_pythonpath else f"{src_path};{existing_pythonpath}"

        cmd = [
            sys.executable,
            "-m",
            "pdoc",
            "common_functions",
            "--docformat",
            "google",
            "--no-search",
            "-o",
            str(temp_dir),
        ]
        subprocess.run(cmd, check=True, env=env, cwd=repo_root)

        generated = temp_dir / "common_functions.html"
        if not generated.exists():
            raise FileNotFoundError(f"Expected pdoc output file not found: {generated}")
        shutil.copyfile(generated, output_file)

    print(f"Updated {output_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
