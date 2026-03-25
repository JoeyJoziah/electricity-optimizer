#!/usr/bin/env python3
"""
doc-coverage-check.py — 3-layer documentation coverage checker for RateShift.

Audits source files across three independent documentation layers and surfaces
gaps as actionable output.  Designed for both human review (default), CI
annotation (--format github), pre-commit reminder (--quick --changed-only),
and machine consumption (--json).

Layer 1 — Codemap mention
--------------------------
Scans docs/CODEMAP_BACKEND.md, docs/CODEMAP_FRONTEND.md, and
docs/CODEMAP_SERVICES.md for bare filenames (basename without extension).
A file "passes" if its basename appears in any CODEMAP document.

Layer 2 — Inline docstring / JSDoc
-------------------------------------
Inspects the first 10 lines of each source file:
  - Python (.py):         passes if triple-quote docstring appears
  - TypeScript / TSX:     passes if JSDoc block (/**) appears OR if the first
                          non-blank, non-import line starts with // comment

Layer 3 — DSP entity
----------------------
Loads .dsp/uid_map.json and verifies each file's relative path (from project
root) is a key in that mapping.

Target file sets
-----------------
  backend/services/*.py          (excludes __init__.py, __pycache__)
  backend/api/v1/*.py            (excludes __init__.py, __pycache__)
  frontend/lib/hooks/*.ts
  frontend/components/**/*.tsx   (top-level only — not nested sub-dirs)
  frontend/lib/api/*.ts

Exit codes
-----------
0  Always (warning-only tool, never blocks).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import date
from pathlib import Path
from typing import Dict, List, NamedTuple, Optional

# ---------------------------------------------------------------------------
# Project-root detection
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent  # scripts/ lives one level below root

CODEMAP_FILES = [
    PROJECT_ROOT / "docs" / "CODEMAP_BACKEND.md",
    PROJECT_ROOT / "docs" / "CODEMAP_FRONTEND.md",
    PROJECT_ROOT / "docs" / "CODEMAP_SERVICES.md",
]

DSP_UID_MAP = PROJECT_ROOT / ".dsp" / "uid_map.json"
REPORTS_DIR = PROJECT_ROOT / "reports"

# ---------------------------------------------------------------------------
# File collection helpers
# ---------------------------------------------------------------------------

_EXCLUDE_NAMES = {"__init__.py", "__pycache__"}


def _collect_backend_services() -> List[Path]:
    d = PROJECT_ROOT / "backend" / "services"
    if not d.exists():
        return []
    return sorted(f for f in d.glob("*.py") if f.name not in _EXCLUDE_NAMES)


def _collect_backend_api() -> List[Path]:
    d = PROJECT_ROOT / "backend" / "api" / "v1"
    if not d.exists():
        return []
    return sorted(f for f in d.glob("*.py") if f.name not in _EXCLUDE_NAMES)


def _collect_frontend_hooks() -> List[Path]:
    d = PROJECT_ROOT / "frontend" / "lib" / "hooks"
    if not d.exists():
        return []
    return sorted(d.glob("*.ts"))


def _collect_frontend_components() -> List[Path]:
    """Top-level .tsx files directly under frontend/components/."""
    d = PROJECT_ROOT / "frontend" / "components"
    if not d.exists():
        return []
    return sorted(d.glob("*.tsx"))


def _collect_frontend_api() -> List[Path]:
    d = PROJECT_ROOT / "frontend" / "lib" / "api"
    if not d.exists():
        return []
    return sorted(d.glob("*.ts"))


def _all_target_files() -> List[Path]:
    return (
        _collect_backend_services()
        + _collect_backend_api()
        + _collect_frontend_hooks()
        + _collect_frontend_components()
        + _collect_frontend_api()
    )


# ---------------------------------------------------------------------------
# Layer 1 — Codemap mention
# ---------------------------------------------------------------------------


def _load_codemap_text() -> str:
    """Concatenate all existing CODEMAP documents into one searchable blob."""
    parts: List[str] = []
    for cm in CODEMAP_FILES:
        if cm.exists():
            try:
                parts.append(cm.read_text(encoding="utf-8"))
            except OSError:
                pass
    return "\n".join(parts)


def check_codemap_layer(files: List[Path], codemap_text: str) -> Dict[str, bool]:
    """
    Return a dict mapping relative-path string → bool (True = mentioned).

    A file passes if its basename without extension appears anywhere in the
    combined CODEMAP text.  The search is case-sensitive because Python module
    names and TypeScript file names are case-sensitive.
    """
    results: Dict[str, bool] = {}
    for f in files:
        stem = f.stem  # e.g. "price_service" from "price_service.py"
        results[str(f.relative_to(PROJECT_ROOT))] = stem in codemap_text
    return results


# ---------------------------------------------------------------------------
# Layer 2 — Inline docstring / JSDoc
# ---------------------------------------------------------------------------

_DOCSTRING_LINES = 10  # how many lines to inspect


def _has_python_docstring(path: Path) -> bool:
    """Return True if triple-quote ``\"\"\"`` appears in the first N lines."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return False
    for line in lines[:_DOCSTRING_LINES]:
        if '"""' in line:
            return True
    return False


def _has_ts_jsdoc(path: Path) -> bool:
    """
    Return True if the file contains a JSDoc block (``/**``) in the first N
    lines, OR if the first non-blank non-import line starts with ``// ``.
    """
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return False

    head = lines[:_DOCSTRING_LINES]

    # Explicit JSDoc block
    for line in head:
        if "/**" in line:
            return True

    # Fallback: first non-blank, non-directive line starts with a // comment
    _skip_prefixes = (
        "//",  # any comment (will be re-checked below)
        "import ",
        'import"',
        "import{",
        "export ",
        "'use ",
        '"use ',
        "/*",
        "*",
    )
    for line in head:
        stripped = line.strip()
        if not stripped:
            continue
        # Skip lines that are clearly directives or imports
        if any(
            stripped.startswith(p)
            for p in (
                "import ",
                'import"',
                "import{",
                "export ",
                "'use ",
                '"use ',
                "/*",
                " *",
                "* ",
            )
        ):
            continue
        # If we reach here this is the first meaningful line
        if stripped.startswith("// "):
            return True
        break  # first meaningful non-comment line found — no description

    return False


def check_docstring_layer(files: List[Path]) -> Dict[str, bool]:
    """Return a dict mapping relative-path → bool (True = documented)."""
    results: Dict[str, bool] = {}
    for f in files:
        rel = str(f.relative_to(PROJECT_ROOT))
        suffix = f.suffix.lower()
        if suffix == ".py":
            results[rel] = _has_python_docstring(f)
        elif suffix in (".ts", ".tsx"):
            results[rel] = _has_ts_jsdoc(f)
        else:
            results[rel] = False
    return results


# ---------------------------------------------------------------------------
# Layer 3 — DSP entity
# ---------------------------------------------------------------------------


def _load_uid_map() -> Optional[Dict[str, str]]:
    """Load .dsp/uid_map.json; return None if it does not exist."""
    if not DSP_UID_MAP.exists():
        return None
    try:
        return json.loads(DSP_UID_MAP.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def check_dsp_layer(
    files: List[Path], uid_map: Optional[Dict[str, str]]
) -> Dict[str, bool]:
    """
    Return a dict mapping relative-path → bool (True = has DSP entity).

    If uid_map is None (file missing / unreadable), all entries are marked
    False so the gap shows up clearly rather than silently passing.
    """
    results: Dict[str, bool] = {}
    for f in files:
        rel = str(f.relative_to(PROJECT_ROOT))
        if uid_map is None:
            results[rel] = False
        else:
            results[rel] = rel in uid_map
    return results


# ---------------------------------------------------------------------------
# --changed-only: resolve staged files
# ---------------------------------------------------------------------------

# File extensions and path prefixes that belong to our tracked sets
_TRACKED_SUFFIXES = {".py", ".ts", ".tsx"}
_TRACKED_PREFIXES = (
    "backend/services/",
    "backend/api/v1/",
    "frontend/lib/hooks/",
    "frontend/components/",
    "frontend/lib/api/",
)


def _get_staged_files() -> List[Path]:
    """Return list of staged file Paths that match our tracked file sets."""
    try:
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only"],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return []
    except (subprocess.SubprocessError, FileNotFoundError):
        return []

    staged: List[Path] = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        p = PROJECT_ROOT / line
        if (
            p.suffix.lower() in _TRACKED_SUFFIXES
            and any(line.startswith(pfx) for pfx in _TRACKED_PREFIXES)
            and p.exists()
            and p.name not in _EXCLUDE_NAMES
        ):
            staged.append(p)
    return staged


# ---------------------------------------------------------------------------
# Result structures
# ---------------------------------------------------------------------------


class FileResult(NamedTuple):
    rel_path: str
    group: str  # "services" | "api" | "hooks" | "components" | "api_ts"
    codemap: bool
    docstring: bool
    dsp: bool

    @property
    def all_pass(self) -> bool:
        return self.codemap and self.docstring and self.dsp

    @property
    def checks_passing(self) -> int:
        return sum([self.codemap, self.docstring, self.dsp])


def _file_group(path: Path) -> str:
    rel = str(path.relative_to(PROJECT_ROOT))
    if rel.startswith("backend/services/"):
        return "services"
    if rel.startswith("backend/api/"):
        return "api"
    if rel.startswith("frontend/lib/hooks/"):
        return "hooks"
    if rel.startswith("frontend/components/"):
        return "components"
    return "api_ts"


# ---------------------------------------------------------------------------
# Core runner
# ---------------------------------------------------------------------------


def run_checks(files: List[Path]) -> List[FileResult]:
    """Execute all three layers against the supplied file list."""
    if not files:
        return []

    codemap_text = _load_codemap_text()
    uid_map = _load_uid_map()

    codemap_results = check_codemap_layer(files, codemap_text)
    docstring_results = check_docstring_layer(files)
    dsp_results = check_dsp_layer(files, uid_map)

    results: List[FileResult] = []
    for f in files:
        rel = str(f.relative_to(PROJECT_ROOT))
        results.append(
            FileResult(
                rel_path=rel,
                group=_file_group(f),
                codemap=codemap_results.get(rel, False),
                docstring=docstring_results.get(rel, False),
                dsp=dsp_results.get(rel, False),
            )
        )
    return results


# ---------------------------------------------------------------------------
# Statistics helpers
# ---------------------------------------------------------------------------


class LayerStats(NamedTuple):
    passing: int
    total: int

    @property
    def pct(self) -> int:
        if self.total == 0:
            return 100
        return round(self.passing / self.total * 100)

    def __str__(self) -> str:
        return f"{self.passing}/{self.total} ({self.pct}%)"


def _compute_stats(
    results: List[FileResult],
) -> tuple[LayerStats, LayerStats, LayerStats, LayerStats]:
    """Return (codemap, docstring, dsp, overall) stats."""
    n = len(results)
    cm = LayerStats(sum(r.codemap for r in results), n)
    ds = LayerStats(sum(r.docstring for r in results), n)
    dsp = LayerStats(sum(r.dsp for r in results), n)
    overall = LayerStats(sum(r.checks_passing for r in results), n * 3)
    return cm, ds, dsp, overall


# ---------------------------------------------------------------------------
# Output formatters
# ---------------------------------------------------------------------------


def _group_label(group: str) -> str:
    return {
        "services": "backend services",
        "api": "backend API routes",
        "hooks": "frontend hooks",
        "components": "frontend components",
        "api_ts": "frontend API clients",
    }.get(group, group)


def format_human(results: List[FileResult], dsp_available: bool) -> str:
    """Render the default human-readable report."""
    cm_stats, ds_stats, dsp_stats, overall = _compute_stats(results)

    lines: List[str] = []
    today = date.today().isoformat()
    lines.append(f"Doc Coverage Report ({today})")
    lines.append("=" * 40)
    lines.append(f"Codemap coverage:   {cm_stats}")
    lines.append(f"Docstring coverage: {ds_stats}")
    dsp_note = (
        "" if dsp_available else "  [uid_map.json not found — all marked missing]"
    )
    lines.append(f"DSP coverage:       {dsp_stats}{dsp_note}")
    lines.append(
        f"Overall:            {overall.passing}/{overall.total} checks passing ({overall.pct}%)"
    )
    lines.append("")

    # Group missing items by layer
    missing_codemap = [r for r in results if not r.codemap]
    missing_docstring = [r for r in results if not r.docstring]
    missing_dsp = [r for r in results if not r.dsp]

    if missing_codemap:
        lines.append(f"Missing codemap entries ({len(missing_codemap)}):")
        for r in missing_codemap:
            lines.append(f"  - {r.rel_path}")
        lines.append("")

    if missing_docstring:
        lines.append(f"Missing docstrings / JSDoc ({len(missing_docstring)}):")
        for r in missing_docstring:
            lines.append(f"  - {r.rel_path}")
        lines.append("")

    if missing_dsp:
        lines.append(f"Missing DSP entities ({len(missing_dsp)}):")
        for r in missing_dsp:
            lines.append(f"  - {r.rel_path}")
        lines.append("")

    if not missing_codemap and not missing_docstring and not missing_dsp:
        lines.append("All documentation checks passing.")

    return "\n".join(lines)


def format_github(results: List[FileResult]) -> str:
    """Render GitHub Actions annotation lines for each missing check."""
    lines: List[str] = []
    for r in results:
        if not r.codemap:
            lines.append(
                f"::warning file={r.rel_path}::"
                f"doc-coverage: {r.rel_path} has no codemap entry "
                f"(add basename '{Path(r.rel_path).stem}' to a CODEMAP_*.md file)"
            )
        if not r.docstring:
            suffix = Path(r.rel_path).suffix.lower()
            hint = (
                'triple-quote module docstring (""")'
                if suffix == ".py"
                else "JSDoc block (/**) or // description comment"
            )
            lines.append(
                f"::warning file={r.rel_path}::"
                f"doc-coverage: {r.rel_path} is missing inline documentation ({hint})"
            )
        if not r.dsp:
            lines.append(
                f"::warning file={r.rel_path}::"
                f"doc-coverage: {r.rel_path} has no DSP entity in .dsp/uid_map.json "
                f"(run: rm -rf .dsp && python3 dsp-cli.py --root . init && python3 scripts/dsp_auto_bootstrap.py)"
            )
    if not lines:
        lines.append("::notice::doc-coverage: all checks passing")
    return "\n".join(lines)


def format_json(results: List[FileResult], dsp_available: bool) -> str:
    """Render structured JSON report."""
    cm_stats, ds_stats, dsp_stats, overall = _compute_stats(results)
    today = date.today().isoformat()

    payload = {
        "generated": today,
        "dsp_uid_map_available": dsp_available,
        "summary": {
            "codemap": {
                "passing": cm_stats.passing,
                "total": cm_stats.total,
                "pct": cm_stats.pct,
            },
            "docstring": {
                "passing": ds_stats.passing,
                "total": ds_stats.total,
                "pct": ds_stats.pct,
            },
            "dsp": {
                "passing": dsp_stats.passing,
                "total": dsp_stats.total,
                "pct": dsp_stats.pct,
            },
            "overall": {
                "passing": overall.passing,
                "total": overall.total,
                "pct": overall.pct,
            },
        },
        "files": [
            {
                "path": r.rel_path,
                "group": r.group,
                "codemap": r.codemap,
                "docstring": r.docstring,
                "dsp": r.dsp,
                "all_pass": r.all_pass,
            }
            for r in results
        ],
    }
    return json.dumps(payload, indent=2)


def format_quick(results: List[FileResult]) -> str:
    """Compact output for pre-commit --quick --changed-only mode."""
    if not results:
        return "doc-coverage: no tracked files changed"

    issues: List[str] = []
    for r in results:
        tags: List[str] = []
        if not r.codemap:
            tags.append("codemap")
        if not r.docstring:
            tags.append("docstring")
        if not r.dsp:
            tags.append("dsp")
        if tags:
            issues.append(f"  {r.rel_path}: missing {', '.join(tags)}")

    if not issues:
        return f"doc-coverage: {len(results)} changed file(s) — all checks passing"

    lines = [
        f"doc-coverage: {len(issues)} of {len(results)} changed file(s) need documentation:"
    ]
    lines.extend(issues)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# JSON report persistence
# ---------------------------------------------------------------------------


def write_json_report(results: List[FileResult], dsp_available: bool) -> None:
    """Write JSON report to reports/doc-coverage.json, creating dir if needed."""
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORTS_DIR / "doc-coverage.json"
    try:
        report_path.write_text(format_json(results, dsp_available), encoding="utf-8")
    except OSError as exc:
        print(
            f"  WARNING: could not write JSON report to {report_path}: {exc}",
            file=sys.stderr,
        )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="doc-coverage-check",
        description=(
            "3-layer documentation coverage checker for RateShift.\n"
            "Checks codemap mentions, inline docstrings, and DSP entity registration."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/doc-coverage-check.py
  python scripts/doc-coverage-check.py --ci
  python scripts/doc-coverage-check.py --format github
  python scripts/doc-coverage-check.py --json
  python scripts/doc-coverage-check.py --quick --changed-only

Exit codes:
  0  Always (warning-only — never blocks CI or commits).
""",
    )
    parser.add_argument(
        "--ci",
        action="store_true",
        help="CI mode: same human-readable output, always exits 0.",
    )
    parser.add_argument(
        "--format",
        choices=["human", "github"],
        default="human",
        help="Output format (default: human). Use 'github' for GHA ::warning annotations.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output structured JSON report to stdout (also writes reports/doc-coverage.json).",
    )
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Quick mode: compact single-line-per-file output.",
    )
    parser.add_argument(
        "--changed-only",
        dest="changed_only",
        action="store_true",
        help=(
            "Only check files that are staged in git (for pre-commit hook usage). "
            "Implies --quick."
        ),
    )
    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    # ------------------------------------------------------------------
    # Resolve file list
    # ------------------------------------------------------------------
    if args.changed_only:
        files = _get_staged_files()
    else:
        files = _all_target_files()

    # ------------------------------------------------------------------
    # Run checks
    # ------------------------------------------------------------------
    results = run_checks(files)
    dsp_available = DSP_UID_MAP.exists()

    # ------------------------------------------------------------------
    # Render output
    # ------------------------------------------------------------------
    if args.json:
        print(format_json(results, dsp_available))
        write_json_report(results, dsp_available)
        sys.exit(0)

    if args.quick or args.changed_only:
        print(format_quick(results))
        # Skip JSON report in quick mode — pre-commit treats file writes as "modified"
        sys.exit(0)

    if args.format == "github":
        print(format_github(results))
        write_json_report(results, dsp_available)
        sys.exit(0)

    # Default: human-readable (also covers --ci)
    print(format_human(results, dsp_available))
    write_json_report(results, dsp_available)

    # --ci and default both exit 0 — this tool is advisory only
    sys.exit(0)


if __name__ == "__main__":
    main()
