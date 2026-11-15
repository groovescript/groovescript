"""Bundle the groovescript package (plus its pure-Python ``lark``
dependency) into ``editors/web/py/groovescript-py.zip`` for the web editor.

The editor's Web Worker unpacks this zip into Pyodide's filesystem, so the
browser runs the exact compiler checked into ``src/``. Run from anywhere:

    uv run python editors/web/scripts/build_py_bundle.py

The output is generated, not committed: the Pages deploy workflow builds it
fresh on every deploy.
"""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path

import lark

ROOT = Path(__file__).resolve().parents[3]
PACKAGES = {
    "groovescript": ROOT / "src" / "groovescript",
    "lark": Path(lark.__file__).resolve().parent,
}
OUT = ROOT / "editors" / "web" / "py" / "groovescript-py.zip"
SKIP_DIRS = {"__pycache__"}
SKIP_SUFFIXES = {".pyc", ".pyo"}


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with zipfile.ZipFile(OUT, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, pkg_dir in PACKAGES.items():
            for path in sorted(pkg_dir.rglob("*")):
                rel = path.relative_to(pkg_dir)
                if path.is_dir() or SKIP_DIRS.intersection(rel.parts):
                    continue
                if path.suffix in SKIP_SUFFIXES:
                    continue
                zf.write(path, f"{name}/{rel.as_posix()}")
                count += 1
    print(f"wrote {OUT.relative_to(ROOT)} ({count} files, {OUT.stat().st_size // 1024} KiB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
