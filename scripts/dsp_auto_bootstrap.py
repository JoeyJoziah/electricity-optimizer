#!/usr/bin/env python3
"""DSP Auto-Discovery Bootstrap — scans the codebase and rebuilds .dsp/ from scratch.

Uses Python AST for .py files and regex for .ts/.tsx files to discover all source
entities and their import relationships. Directly uses the dsp-cli Engine/Store
classes to avoid ~900 subprocess calls.

Usage:
    python3 scripts/dsp_auto_bootstrap.py
    python3 scripts/dsp_auto_bootstrap.py --dry-run   # show counts without writing
"""

from __future__ import annotations

import ast
import json
import os
import re
import sys
import time
from pathlib import Path

# ── Add project root to path so we can import dsp-cli ──
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Import the dsp-cli engine directly (avoids subprocess overhead)
import importlib.util

spec = importlib.util.spec_from_file_location("dsp_cli", PROJECT_ROOT / "dsp-cli.py")
dsp_cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dsp_cli)

Store = dsp_cli.Store
Engine = dsp_cli.Engine

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Configuration
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Directories to scan and their languages
SCAN_DIRS: list[tuple[str, str]] = [
    ("backend", "python"),
    ("frontend", "typescript"),
    ("ml", "python"),
    ("workers", "typescript"),
]

# Exclusion patterns (relative to project root)
EXCLUDE_PATTERNS: list[str] = [
    "node_modules",
    "__pycache__",
    ".next",
    ".pytest_cache",
    "__tests__",
    ".test.",
    ".spec.",
    "migrations/",
    "conftest.py",
]

# Filename prefixes that indicate test files (applied to basename only)
TEST_PREFIXES: tuple[str, ...] = ("test_",)

# Files to always skip
SKIP_FILES: set[str] = {"__init__.py", "setup.py", "setup.cfg"}

# Known external packages (top-level modules)
PYTHON_EXTERNALS: set[str] = {
    "fastapi", "uvicorn", "pydantic", "sqlalchemy", "alembic", "httpx",
    "structlog", "stripe", "resend", "nh3", "numpy", "scipy", "sklearn",
    "pandas", "groq", "google", "composio_core", "composio_openai",
    "opentelemetry", "starlette", "jose", "passlib", "bcrypt",
    "aiohttp", "asyncio", "datetime", "typing", "os", "sys", "re",
    "json", "uuid", "pathlib", "collections", "functools", "itertools",
    "hashlib", "hmac", "base64", "time", "logging", "abc", "enum",
    "dataclasses", "contextlib", "copy", "math", "random", "secrets",
    "textwrap", "io", "csv", "tempfile", "traceback", "inspect",
    "unittest", "cryptography", "Crypto", "dotenv", "redis",
    "tavily", "diffbot", "apscheduler", "celery", "kombu",
    "better_auth", "hnswlib", "geopy", "pytz",
}

TS_EXTERNALS: set[str] = {
    "react", "next", "next/", "@next/", "react-dom", "lucide-react",
    "recharts", "tailwind-merge", "clsx", "class-variance-authority",
    "zod", "@radix-ui", "sonner", "framer-motion", "swr",
    "@tanstack/react-query", "date-fns", "zustand", "nodemailer",
    "better-auth", "@better-auth", "stripe", "@stripe",
    "onesignal-node", "@onesignal", "next-themes", "cmdk",
}

# TypeScript path alias
TS_ALIAS = "@/"
TS_ALIAS_TARGET = "frontend/"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# File discovery
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def should_exclude(rel_path: str) -> bool:
    """Check if a file should be excluded based on patterns."""
    for pattern in EXCLUDE_PATTERNS:
        if pattern in rel_path:
            return True
    return False


def discover_files() -> list[tuple[str, str]]:
    """Walk scan dirs and return (relative_path, language) for all source files."""
    files: list[tuple[str, str]] = []

    for scan_dir, lang in SCAN_DIRS:
        root = PROJECT_ROOT / scan_dir
        if not root.is_dir():
            continue

        if lang == "python":
            extensions = {".py"}
        else:
            extensions = {".ts", ".tsx"}

        for dirpath, dirnames, filenames in os.walk(root):
            # Prune excluded directories
            dirnames[:] = [
                d for d in dirnames
                if d not in ("node_modules", "__pycache__", ".next", ".pytest_cache",
                             "__tests__", "test", "tests", ".turbo", "dist", ".git")
            ]
            for fname in filenames:
                if Path(fname).suffix not in extensions:
                    continue
                if fname in SKIP_FILES:
                    continue

                full = Path(dirpath) / fname
                rel = str(full.relative_to(PROJECT_ROOT))

                if should_exclude(rel):
                    continue
                # Test file prefix check on basename only
                if fname.startswith(TEST_PREFIXES):
                    continue

                files.append((rel, lang))

    return sorted(files)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Python import parsing (via AST)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def get_python_docstring(filepath: Path) -> str:
    """Extract the first line of the module docstring, or empty string."""
    try:
        tree = ast.parse(filepath.read_text(encoding="utf-8", errors="replace"))
        docstring = ast.get_docstring(tree)
        if docstring:
            return docstring.split("\n")[0].strip()
    except (SyntaxError, UnicodeDecodeError):
        pass
    return ""


def resolve_python_import(module: str, file_rel: str) -> str | None:
    """Resolve a Python module path to a project-relative .py file path.

    Returns None if external, unresolvable, or resolves to a package (__init__.py)
    since we don't track __init__.py as entities.
    """
    parts = module.split(".")
    top = parts[0]

    # Known external
    if top in PYTHON_EXTERNALS:
        return None

    # Project-internal: backend.services.X → backend/services/X.py
    if top in ("backend", "ml"):
        candidate = "/".join(parts) + ".py"
        if (PROJECT_ROOT / candidate).is_file():
            return candidate
        # Don't resolve to __init__.py — those aren't tracked entities

    # Bare module imports relative to package root
    file_package = file_rel.split("/")[0]
    if file_package in ("backend", "ml"):
        prefixed = file_package + "/" + "/".join(parts) + ".py"
        if (PROJECT_ROOT / prefixed).is_file():
            return prefixed
        # Don't resolve to __init__.py — those aren't tracked entities

    return None


def resolve_relative_python_import(module: str | None, level: int, file_rel: str) -> str | None:
    """Resolve a relative Python import (from . import X / from ..X import Y)."""
    file_dir = str(Path(file_rel).parent)
    parts = file_dir.split("/")

    # Go up `level` directories
    if level > len(parts):
        return None
    base_parts = parts[:len(parts) - level + 1]

    if module:
        mod_parts = module.split(".")
        target_parts = base_parts + mod_parts
    else:
        target_parts = base_parts

    candidate = "/".join(target_parts) + ".py"
    if (PROJECT_ROOT / candidate).is_file():
        return candidate
    return None


def parse_python_imports(filepath: Path, file_rel: str) -> list[tuple[str, list[str]]]:
    """Parse Python file and return list of (resolved_path, [imported_names])."""
    imports: list[tuple[str, list[str]]] = []
    externals: list[str] = []

    try:
        source = filepath.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(source)
    except (SyntaxError, UnicodeDecodeError):
        return imports

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                resolved = resolve_python_import(alias.name, file_rel)
                if resolved:
                    imports.append((resolved, [alias.name.split(".")[-1]]))
                elif alias.name.split(".")[0] not in PYTHON_EXTERNALS:
                    # Could be external we didn't list
                    externals.append(alias.name.split(".")[0])

        elif isinstance(node, ast.ImportFrom):
            if node.level > 0:
                # Relative import
                resolved = resolve_relative_python_import(node.module, node.level, file_rel)
                if resolved:
                    names = [a.name for a in (node.names or [])]
                    imports.append((resolved, names))
            elif node.module:
                resolved = resolve_python_import(node.module, file_rel)
                if resolved:
                    names = [a.name for a in (node.names or [])]
                    imports.append((resolved, names))
                else:
                    # Try resolving each imported name as a submodule of the package.
                    # e.g., "from api.v1 import prices" → backend/api/v1/prices.py
                    found_any = False
                    for alias in (node.names or []):
                        sub_module = f"{node.module}.{alias.name}"
                        sub_resolved = resolve_python_import(sub_module, file_rel)
                        if sub_resolved:
                            imports.append((sub_resolved, [alias.name]))
                            found_any = True
                    if not found_any and node.module.split(".")[0] not in PYTHON_EXTERNALS:
                        externals.append(node.module.split(".")[0])

    return imports


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TypeScript import parsing (via regex)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Matches: import ... from '...' / import '...' / import type ... from '...'
TS_IMPORT_RE = re.compile(
    r"""(?:import\s+(?:type\s+)?(?:(?:\{[^}]*\}|\*\s+as\s+\w+|\w+(?:\s*,\s*\{[^}]*\})?)\s+from\s+)?['\"]([^'"]+)['\"])""",
    re.MULTILINE,
)

# Also catch dynamic imports: import('...')
TS_DYNAMIC_IMPORT_RE = re.compile(r"""import\(\s*['\"]([^'"]+)['\"]""")

# Extract named imports: import { Foo, Bar } from '...'
TS_NAMED_IMPORT_RE = re.compile(
    r"""import\s+(?:type\s+)?\{([^}]+)\}\s+from\s+['\"]([^'"]+)['\"]""",
    re.MULTILINE,
)


def get_ts_first_comment(filepath: Path) -> str:
    """Get the first comment line from a TS/TSX file."""
    try:
        lines = filepath.read_text(encoding="utf-8", errors="replace").split("\n")
        for line in lines[:10]:
            stripped = line.strip()
            if stripped.startswith("//"):
                return stripped.lstrip("/ ").strip()
            if stripped.startswith("/*"):
                return stripped.lstrip("/* ").rstrip("*/").strip()
            if stripped and not stripped.startswith("import") and not stripped.startswith("'use"):
                break
    except (UnicodeDecodeError, OSError):
        pass
    return ""


def is_ts_external(specifier: str) -> bool:
    """Check if a TS import specifier is external (not relative, not alias)."""
    if specifier.startswith(".") or specifier.startswith(TS_ALIAS):
        return False
    for ext in TS_EXTERNALS:
        if specifier == ext or specifier.startswith(ext):
            return True
    # Any non-relative, non-alias import is likely external
    if not specifier.startswith(".") and not specifier.startswith(TS_ALIAS):
        return True
    return False


def resolve_ts_import(specifier: str, file_rel: str) -> str | None:
    """Resolve a TS import specifier to a project-relative file path."""
    if is_ts_external(specifier):
        return None

    # Handle @/ alias
    if specifier.startswith(TS_ALIAS):
        target = TS_ALIAS_TARGET + specifier[len(TS_ALIAS):]
    elif specifier.startswith("."):
        # Relative import
        file_dir = str(Path(file_rel).parent)
        target = os.path.normpath(os.path.join(file_dir, specifier))
    else:
        return None

    # Try various extensions and index files
    candidates = [
        target + ".ts",
        target + ".tsx",
        target + "/index.ts",
        target + "/index.tsx",
        target + ".js",
        target + ".jsx",
        target,  # exact path
    ]

    for candidate in candidates:
        if (PROJECT_ROOT / candidate).is_file():
            return candidate

    return None


def parse_ts_imports(filepath: Path, file_rel: str) -> list[tuple[str, list[str]]]:
    """Parse TS/TSX file and return list of (resolved_path, [imported_names])."""
    imports: list[tuple[str, list[str]]] = []

    try:
        source = filepath.read_text(encoding="utf-8", errors="replace")
    except (UnicodeDecodeError, OSError):
        return imports

    # Extract named imports with their specifiers
    named_map: dict[str, list[str]] = {}
    for match in TS_NAMED_IMPORT_RE.finditer(source):
        names = [n.strip().split(" as ")[0].strip() for n in match.group(1).split(",") if n.strip()]
        specifier = match.group(2)
        named_map.setdefault(specifier, []).extend(names)

    # Get all import specifiers
    seen: set[str] = set()
    for match in TS_IMPORT_RE.finditer(source):
        specifier = match.group(1)
        if specifier not in seen:
            seen.add(specifier)
            resolved = resolve_ts_import(specifier, file_rel)
            if resolved:
                names = named_map.get(specifier, [])
                imports.append((resolved, names))

    for match in TS_DYNAMIC_IMPORT_RE.finditer(source):
        specifier = match.group(1)
        if specifier not in seen:
            seen.add(specifier)
            resolved = resolve_ts_import(specifier, file_rel)
            if resolved:
                imports.append((resolved, []))

    return imports


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Description generation
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Path-based purpose heuristics
PURPOSE_HINTS: dict[str, str] = {
    "api/v1/": "API route handler",
    "api/v1/internal/": "Internal API endpoint",
    "services/": "Business logic service",
    "models/": "Data model definition",
    "lib/": "Shared library utility",
    "config/": "Configuration module",
    "middleware/": "Middleware handler",
    "app/(app)/": "App page component",
    "app/(public)/": "Public page component",
    "app/(auth)/": "Authentication page",
    "components/": "UI component",
    "components/ui/": "Base UI component",
    "hooks/": "React hook",
    "utils/": "Utility function",
    "types/": "TypeScript type definition",
    "optimization/": "ML optimization module",
    "handlers/": "Request handler",
}


def generate_purpose(file_rel: str, lang: str, filepath: Path) -> str:
    """Generate a description for an entity based on docstring/comment and path."""
    # Try docstring/comment first
    if lang == "python":
        docstring = get_python_docstring(filepath)
        if docstring and len(docstring) > 10:
            return docstring
    else:
        comment = get_ts_first_comment(filepath)
        if comment and len(comment) > 10:
            return comment

    # Fall back to path-based heuristic
    for path_pattern, hint in PURPOSE_HINTS.items():
        if path_pattern in file_rel:
            name = Path(file_rel).stem
            if name == "index":
                name = Path(file_rel).parent.name
            # Clean up: page → Page, my_service → MyService
            clean_name = name.replace("_", " ").replace("-", " ").title()
            return f"{hint} for {clean_name}"

    # Ultimate fallback
    name = Path(file_rel).stem
    layer = file_rel.split("/")[0]
    return f"{layer.title()} module: {name}"


def generate_import_why(imported_names: list[str], target_rel: str) -> str:
    """Generate a 'why' description for an import relationship."""
    if imported_names:
        # Use up to 3 names
        names = imported_names[:3]
        suffix = f" + {len(imported_names) - 3} more" if len(imported_names) > 3 else ""
        return f"Uses {', '.join(names)}{suffix}"
    # Fall back to module name
    name = Path(target_rel).stem
    return f"Imports from {name}"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# External dependency tracking
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def collect_python_externals(filepath: Path) -> set[str]:
    """Collect external package names from a Python file."""
    externals: set[str] = set()
    try:
        source = filepath.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(source)
    except (SyntaxError, UnicodeDecodeError):
        return externals

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".")[0]
                if top in PYTHON_EXTERNALS and top not in (
                    "os", "sys", "re", "json", "uuid", "pathlib", "collections",
                    "functools", "itertools", "hashlib", "hmac", "base64", "time",
                    "logging", "abc", "enum", "dataclasses", "contextlib", "copy",
                    "math", "random", "secrets", "textwrap", "io", "csv",
                    "tempfile", "traceback", "inspect", "unittest", "typing",
                    "datetime", "asyncio",
                ):
                    externals.add(top)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            top = node.module.split(".")[0]
            if top in PYTHON_EXTERNALS and top not in (
                "os", "sys", "re", "json", "uuid", "pathlib", "collections",
                "functools", "itertools", "hashlib", "hmac", "base64", "time",
                "logging", "abc", "enum", "dataclasses", "contextlib", "copy",
                "math", "random", "secrets", "textwrap", "io", "csv",
                "tempfile", "traceback", "inspect", "unittest", "typing",
                "datetime", "asyncio",
            ):
                externals.add(top)
    return externals


def collect_ts_externals(filepath: Path) -> set[str]:
    """Collect external package names from a TS/TSX file."""
    externals: set[str] = set()
    try:
        source = filepath.read_text(encoding="utf-8", errors="replace")
    except (UnicodeDecodeError, OSError):
        return externals

    for match in TS_IMPORT_RE.finditer(source):
        specifier = match.group(1)
        if is_ts_external(specifier) and not specifier.startswith("."):
            # Normalize: @tanstack/react-query → @tanstack/react-query
            # react → react, next/navigation → next
            if specifier.startswith("@"):
                pkg = "/".join(specifier.split("/")[:2])
            else:
                pkg = specifier.split("/")[0]
            externals.add(pkg)
    return externals


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Main bootstrap
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def main() -> None:
    dry_run = "--dry-run" in sys.argv

    start = time.time()
    print("DSP Auto-Discovery Bootstrap")
    print(f"Project root: {PROJECT_ROOT}")
    print()

    # ── Phase 1: Discover all source files ──
    print("Phase 1: Discovering source files...")
    files = discover_files()
    py_files = [(f, l) for f, l in files if l == "python"]
    ts_files = [(f, l) for f, l in files if l == "typescript"]
    print(f"  Found {len(py_files)} Python + {len(ts_files)} TypeScript = {len(files)} files")

    if dry_run:
        for f, l in files:
            print(f"  [{l[:2]}] {f}")
        print("\nDry run — no changes made.")
        return

    # ── Phase 2: Parse all imports ──
    print("\nPhase 2: Parsing imports...")
    # source_path → [(target_path, [names])]
    all_imports: dict[str, list[tuple[str, list[str]]]] = {}
    all_externals: set[str] = set()

    for file_rel, lang in files:
        filepath = PROJECT_ROOT / file_rel
        if lang == "python":
            imports = parse_python_imports(filepath, file_rel)
            exts = collect_python_externals(filepath)
        else:
            imports = parse_ts_imports(filepath, file_rel)
            exts = collect_ts_externals(filepath)

        # Deduplicate imports (same target from same file) and skip self-imports
        seen_targets: dict[str, list[str]] = {}
        for target, names in imports:
            if target == file_rel:
                continue  # skip self-imports
            if target in seen_targets:
                seen_targets[target].extend(names)
            else:
                seen_targets[target] = list(names)

        all_imports[file_rel] = [(t, n) for t, n in seen_targets.items()]
        all_externals.update(exts)

    total_imports = sum(len(v) for v in all_imports.values())
    print(f"  Parsed {total_imports} internal imports + {len(all_externals)} external packages")

    # ── Phase 3: Create entities ──
    print("\nPhase 3: Creating entities...")
    store = Store(PROJECT_ROOT)
    engine = Engine(store)

    # Map source_path → uid
    uid_map: dict[str, str] = {}

    for file_rel, lang in files:
        filepath = PROJECT_ROOT / file_rel
        purpose = generate_purpose(file_rel, lang, filepath)
        uid = engine.create_object(file_rel, purpose)
        uid_map[file_rel] = uid

    print(f"  Created {len(uid_map)} source entities")

    # Create external dependency entities
    ext_uid_map: dict[str, str] = {}
    for pkg in sorted(all_externals):
        purpose = f"External package: {pkg}"
        uid = engine.create_object(pkg, purpose, kind="external")
        ext_uid_map[pkg] = uid

    print(f"  Created {len(ext_uid_map)} external entities")

    # ── Phase 4: Create import relationships ──
    print("\nPhase 4: Creating import relationships...")
    import_count = 0
    skipped = 0

    for file_rel, imports in all_imports.items():
        importer_uid = uid_map.get(file_rel)
        if not importer_uid:
            continue

        for target_rel, names in imports:
            imported_uid = uid_map.get(target_rel)
            if not imported_uid:
                skipped += 1
                continue

            why = generate_import_why(names, target_rel)
            engine.add_import(importer_uid, imported_uid, why)
            import_count += 1

    print(f"  Created {import_count} import relationships (skipped {skipped} unresolved)")

    # ── Phase 5: Save uid_map.json ──
    print("\nPhase 5: Saving uid_map.json...")
    uid_map_path = PROJECT_ROOT / ".dsp" / "uid_map.json"
    combined_map = {**uid_map, **ext_uid_map}
    uid_map_path.write_text(
        json.dumps(combined_map, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"  Saved {len(combined_map)} entries to .dsp/uid_map.json")

    # ── Summary ──
    elapsed = time.time() - start
    print(f"\nDone in {elapsed:.1f}s")
    print(f"  Source entities:   {len(uid_map)}")
    print(f"  External entities: {len(ext_uid_map)}")
    print(f"  Total entities:    {len(combined_map)}")
    print(f"  Import edges:      {import_count}")
    print()
    print("Run verification:")
    print("  python3 dsp-cli.py --root . get-stats")
    print("  python3 dsp-cli.py --root . detect-cycles")


if __name__ == "__main__":
    main()
