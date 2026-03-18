#!/usr/bin/env python3
"""
api-contract-check.py — Heuristic API contract validator for RateShift.

Compares Pydantic response models in the backend (backend/api/v1/*.py and
backend/models/*.py) against TypeScript interfaces in the frontend
(frontend/lib/api/*.ts and frontend/types/**/*.ts) to surface field mismatches
before they cause runtime bugs.

How it works
------------
1. Backend pass:
   a. Walk backend/api/v1/**/*.py and backend/models/*.py with Python's ``ast``
      module.
   b. Collect every ``class Foo(BaseModel)`` definition together with its field
      names and annotated types.
   c. Walk route decorator calls (@router.get / @router.post / etc.) and record
      the ``response_model`` for each path.  When the response_model is a name
      (not an inline class), resolve it from the collected Pydantic classes.

2. Frontend pass:
   a. Walk frontend/lib/api/*.ts and frontend/types/**/*.ts with regex.
   b. Collect every ``interface Foo { ... }`` and ``type Foo = { ... }``
      definition, parsing their field names and TypeScript types.

3. Matching:
   The script tries several naming conventions to pair a Python class with a
   TypeScript interface:
     - Exact name            PriceResponse      ↔  PriceResponse
     - Strip "Response"      PriceResponse      ↔  Price
     - Add "Api" prefix      PriceResponse      ↔  ApiPriceResponse
     - Strip "Request"       CreateAlertRequest ↔  CreateAlert / Alert
     - Camel variants        UserProfile        ↔  UserProfile
   Unmatched Python models are listed as warnings, not failures.

4. Type mapping (Python → TypeScript):
   str, UUID, Enum     → string
   int                 → number
   float, Decimal      → number
   bool                → boolean
   datetime            → string  (ISO-8601)
   Optional[X]         → X | undefined  (or X | null)
   list[X] / List[X]   → X[]
   dict / Dict         → Record<string, any>
   Any                 → any

Known limitations
-----------------
- Generic containers such as ``Page[T]`` are not fully resolved.
- Inline ``response_model=List[SomeSchema]`` is partially handled.
- TypeScript union types (``a | b``) are treated as opaque strings during
  type comparison; only field presence/absence is checked strictly.
- Models defined dynamically (e.g. via ``create_model()``) are not detected.
- The frontend pass only reads static ``.ts`` files, not compiled output or
  generated JSON-schema files.
- ``Dict[str, Any]`` and ``object`` are treated as compatible regardless of
  actual value types.

Exit codes
----------
0 — No definitive mismatches found.
1 — One or more definitive field-name or type mismatches found.
"""

from __future__ import annotations

import argparse
import ast
import fnmatch
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Set, Tuple

# ---------------------------------------------------------------------------
# Project-root detection
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent  # scripts/ lives one level below root

BACKEND_API_DIRS = [
    PROJECT_ROOT / "backend" / "api" / "v1",
]
BACKEND_MODEL_DIRS = [
    PROJECT_ROOT / "backend" / "models",
    PROJECT_ROOT / "backend" / "api" / "v1",  # inline models defined here too
]
FRONTEND_API_DIR = PROJECT_ROOT / "frontend" / "lib" / "api"
FRONTEND_TYPES_DIR = PROJECT_ROOT / "frontend" / "types"

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class PyField:
    name: str
    py_type: str
    optional: bool = False


@dataclass
class TsField:
    name: str
    ts_type: str
    optional: bool = False


@dataclass
class PyModel:
    name: str
    fields: List[PyField]
    source_file: Path


@dataclass
class TsInterface:
    name: str
    fields: List[TsField]
    source_file: Path


@dataclass
class RouteModel:
    path: str
    method: str
    response_model_name: str
    source_file: Path


@dataclass
class Mismatch:
    kind: str  # "missing_field" | "type_conflict" | "extra_field"
    py_model: str
    ts_interface: str
    field: str
    py_type: str
    ts_type: str
    severity: str  # "ERROR" | "WARNING"


# ---------------------------------------------------------------------------
# Python type → TypeScript type mapping
# ---------------------------------------------------------------------------

_PY_TO_TS: Dict[str, str] = {
    "str": "string",
    "int": "number",
    "float": "number",
    "bool": "boolean",
    "bytes": "string",
    "Any": "any",
    "None": "null",
    "NoneType": "null",
    # Common type aliases used in models
    "UUID": "string",
    "Decimal": "string",  # FastAPI serialises Decimal as string
    "datetime": "string",
    "date": "string",
    "time": "string",
    "timedelta": "string",
    "HttpUrl": "string",
    "EmailStr": "string",
    "AnyUrl": "string",
    # Containers
    "dict": "Record<string, any>",
    "Dict": "Record<string, any>",
    "object": "Record<string, any>",
    "list": "any[]",
    "List": "any[]",
    "set": "any[]",
    "Set": "any[]",
    "tuple": "any[]",
    "Tuple": "any[]",
}

# Types that are compatible with TypeScript string (enum values, etc.)
_STRING_COMPATIBLE_TS = {"string", "DecimalStr", "DateTimeStr"}


def _py_type_to_ts(py_type: str) -> str:
    """
    Convert a Python type annotation string to its TypeScript equivalent.

    Only handles common cases; returns the original string for anything
    complex so callers can treat it as an unknown type.
    """
    py_type = py_type.strip()

    # Optional[X] → X | null
    m = re.match(r"^Optional\[(.+)\]$", py_type)
    if m:
        inner = _py_type_to_ts(m.group(1))
        return f"{inner} | null"

    # Union[X, None] → X | null
    m = re.match(r"^Union\[(.+),\s*None\]$", py_type)
    if m:
        inner = _py_type_to_ts(m.group(1))
        return f"{inner} | null"

    # Union[X, Y] → X | Y
    m = re.match(r"^Union\[(.+)\]$", py_type)
    if m:
        parts = [_py_type_to_ts(p.strip()) for p in _split_generic_args(m.group(1))]
        return " | ".join(parts)

    # list[X] / List[X] → X[]
    m = re.match(r"^(?:List|list)\[(.+)\]$", py_type)
    if m:
        inner = _py_type_to_ts(m.group(1))
        return f"{inner}[]"

    # Sequence[X] → X[]
    m = re.match(r"^Sequence\[(.+)\]$", py_type)
    if m:
        inner = _py_type_to_ts(m.group(1))
        return f"{inner}[]"

    # Dict[str, X] / dict[str, X]
    m = re.match(r"^(?:Dict|dict)\[(.+)\]$", py_type)
    if m:
        args = _split_generic_args(m.group(1))
        if len(args) == 2:
            val_ts = _py_type_to_ts(args[1].strip())
            return f"Record<string, {val_ts}>"
        return "Record<string, any>"

    # Direct lookup
    if py_type in _PY_TO_TS:
        return _PY_TO_TS[py_type]

    # Strip module prefix (e.g. models.price.PriceResponse → PriceResponse)
    if "." in py_type:
        base = py_type.rsplit(".", 1)[-1]
        if base in _PY_TO_TS:
            return _PY_TO_TS[base]
        return base  # unknown complex type — return as-is

    # Enum class name → string (Python enums serialise as their .value)
    # We cannot know for sure without inspecting the enum definition, so
    # we return "string" and rely on the caller to not count this as a conflict.
    return py_type  # unknown — pass through


def _split_generic_args(args_str: str) -> List[str]:
    """
    Split a comma-separated generic argument list respecting nested brackets.

    e.g. "str, Dict[str, int]" → ["str", "Dict[str, int]"]
    """
    parts: List[str] = []
    depth = 0
    current = ""
    for ch in args_str:
        if ch in ("[", "("):
            depth += 1
            current += ch
        elif ch in ("]", ")"):
            depth -= 1
            current += ch
        elif ch == "," and depth == 0:
            parts.append(current.strip())
            current = ""
        else:
            current += ch
    if current.strip():
        parts.append(current.strip())
    return parts


# ---------------------------------------------------------------------------
# Backend parsing — AST-based Pydantic model extraction
# ---------------------------------------------------------------------------


def _collect_py_files(dirs: List[Path], recursive: bool = True) -> List[Path]:
    files: List[Path] = []
    for d in dirs:
        if not d.exists():
            continue
        if recursive:
            files.extend(d.rglob("*.py"))
        else:
            files.extend(d.glob("*.py"))
    return sorted(set(files))


def _extract_annotation_str(node: ast.expr) -> str:
    """Convert an AST annotation node to a readable type string."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Constant):
        return repr(node.value)
    if isinstance(node, ast.Attribute):
        return f"{_extract_annotation_str(node.value)}.{node.attr}"
    if isinstance(node, ast.Subscript):
        container = _extract_annotation_str(node.value)
        # Python 3.9+: node.slice is the inner node directly
        # Python 3.8:  node.slice is ast.Index(value=...)
        slice_node = node.slice
        if isinstance(slice_node, ast.Index):  # Python 3.8 compat
            slice_node = slice_node.value  # type: ignore[attr-defined]
        inner = _extract_annotation_str(slice_node)
        return f"{container}[{inner}]"
    if isinstance(node, ast.Tuple):
        elts = ", ".join(_extract_annotation_str(e) for e in node.elts)
        return elts
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        left = _extract_annotation_str(node.left)
        right = _extract_annotation_str(node.right)
        return f"Union[{left}, {right}]"
    return "Any"


class _ModelCollector(ast.NodeVisitor):
    """AST visitor that collects BaseModel subclasses and their fields."""

    def __init__(self, source_file: Path) -> None:
        self.source_file = source_file
        self.models: Dict[str, PyModel] = {}
        self._class_stack: List[str] = []
        # Track imports to handle forward references
        self._imports: Dict[str, str] = {}

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            local_name = alias.asname or alias.name.rsplit(".", 1)[-1]
            self._imports[local_name] = alias.name
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = node.module or ""
        for alias in node.names:
            local_name = alias.asname or alias.name
            self._imports[local_name] = f"{module}.{alias.name}"
        self.generic_visit(node)

    def _is_base_model(self, bases: List[ast.expr]) -> bool:
        for base in bases:
            name = _extract_annotation_str(base)
            if name in ("BaseModel", "pydantic.BaseModel"):
                return True
            # Also include classes that inherit from our own BaseModel subclasses
            # We can't fully resolve this without running the code, so we use a
            # conservative heuristic: any base whose name ends with "Model",
            # "Schema", "Response", "Request", or "Base" is treated as a model.
            if any(
                name.endswith(suffix)
                for suffix in (
                    "Model",
                    "Schema",
                    "Response",
                    "Request",
                    "Base",
                    "Out",
                    "In",
                )
            ):
                return True
        return False

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        if not self._is_base_model(node.bases):
            self.generic_visit(node)
            return

        fields: List[PyField] = []
        for item in node.body:
            if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                field_name = item.target.id
                if field_name.startswith("_"):
                    continue  # skip private / dunder
                if item.annotation is None:
                    continue

                raw_type = _extract_annotation_str(item.annotation)
                optional = raw_type.startswith("Optional[") or (
                    item.value is not None
                    and isinstance(item.value, ast.Constant)
                    and item.value.value is None
                )
                fields.append(
                    PyField(name=field_name, py_type=raw_type, optional=optional)
                )

        self.models[node.name] = PyModel(
            name=node.name,
            fields=fields,
            source_file=self.source_file,
        )
        self.generic_visit(node)


def parse_backend_models(dirs: List[Path]) -> Dict[str, PyModel]:
    """Return a dict of class_name → PyModel for all files under dirs."""
    all_models: Dict[str, PyModel] = {}
    for py_file in _collect_py_files(dirs):
        try:
            source = py_file.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(py_file))
        except SyntaxError as exc:
            print(f"  WARNING: Could not parse {py_file}: {exc}", file=sys.stderr)
            continue
        collector = _ModelCollector(py_file)
        collector.visit(tree)
        # Later files win on name collision (allows inline overrides in api/ files)
        all_models.update(collector.models)
    return all_models


# ---------------------------------------------------------------------------
# Backend parsing — route response_model extraction
# ---------------------------------------------------------------------------

_ROUTE_DECORATORS = {"get", "post", "put", "patch", "delete", "head", "options"}


class _RouteCollector(ast.NodeVisitor):
    """Collect @router.METHOD(path, response_model=X) calls."""

    def __init__(self, source_file: Path) -> None:
        self.source_file = source_file
        self.routes: List[RouteModel] = []

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._check_decorators(node)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._check_decorators(node)
        self.generic_visit(node)

    def _check_decorators(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        for deco in node.decorator_list:
            if not isinstance(deco, ast.Call):
                continue
            func = deco.func
            # Match router.get(path, ...) / app.post(path, ...) etc.
            if isinstance(func, ast.Attribute) and func.attr in _ROUTE_DECORATORS:
                method = func.attr.upper()
                # First positional arg is the path
                path = ""
                if deco.args and isinstance(deco.args[0], ast.Constant):
                    path = str(deco.args[0].value)
                # Find response_model keyword
                for kw in deco.keywords:
                    if kw.arg == "response_model":
                        model_name = _extract_annotation_str(kw.value)
                        self.routes.append(
                            RouteModel(
                                path=path,
                                method=method,
                                response_model_name=model_name,
                                source_file=self.source_file,
                            )
                        )


def parse_backend_routes(dirs: List[Path]) -> List[RouteModel]:
    routes: List[RouteModel] = []
    for py_file in _collect_py_files(dirs):
        try:
            source = py_file.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(py_file))
        except SyntaxError:
            continue
        collector = _RouteCollector(py_file)
        collector.visit(tree)
        routes.extend(collector.routes)
    return routes


# ---------------------------------------------------------------------------
# Frontend parsing — TypeScript interface/type extraction via regex
# ---------------------------------------------------------------------------

# Matches: interface FooBar { ... }  (possibly with extends)
_TS_INTERFACE_RE = re.compile(
    r"(?:export\s+)?interface\s+(\w+)(?:\s+extends\s+[^{]+)?\s*\{([^}]*)\}",
    re.DOTALL,
)

# Matches: type FooBar = { ... }
_TS_TYPE_OBJ_RE = re.compile(
    r"(?:export\s+)?type\s+(\w+)\s*=\s*\{([^}]*)\}",
    re.DOTALL,
)

# Matches a single TypeScript field line, e.g.:
#   fieldName: string
#   fieldName?: string | null
#   readonly fieldName: SomeType[]
_TS_FIELD_RE = re.compile(
    r"^\s*(?:readonly\s+)?(\w+)(\?)?\s*:\s*(.+?)\s*$",
    re.MULTILINE,
)

# Strip JS/TS line comments from field blocks before parsing
_TS_LINE_COMMENT_RE = re.compile(r"//[^\n]*")
_TS_BLOCK_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)


def _clean_ts_block(block: str) -> str:
    block = _TS_BLOCK_COMMENT_RE.sub("", block)
    block = _TS_LINE_COMMENT_RE.sub("", block)
    return block


def _parse_ts_fields(body: str) -> List[TsField]:
    body = _clean_ts_block(body)
    fields: List[TsField] = []
    for m in _TS_FIELD_RE.finditer(body):
        name = m.group(1)
        optional = m.group(2) == "?"
        ts_type = m.group(3).rstrip(";, ")
        fields.append(TsField(name=name, ts_type=ts_type, optional=optional))
    return fields


def _collect_ts_files(dirs: List[Path]) -> List[Path]:
    files: List[Path] = []
    for d in dirs:
        if not d.exists():
            continue
        files.extend(d.rglob("*.ts"))
        files.extend(d.rglob("*.tsx"))
    # Exclude node_modules, __tests__, coverage
    return [
        f
        for f in files
        if "node_modules" not in f.parts
        and "__tests__" not in f.parts
        and "coverage" not in f.parts
        and ".next" not in f.parts
    ]


def parse_frontend_interfaces(dirs: List[Path]) -> Dict[str, TsInterface]:
    interfaces: Dict[str, TsInterface] = {}
    for ts_file in _collect_ts_files(dirs):
        try:
            source = ts_file.read_text(encoding="utf-8")
        except OSError:
            continue
        for pattern in (_TS_INTERFACE_RE, _TS_TYPE_OBJ_RE):
            for m in pattern.finditer(source):
                name = m.group(1)
                body = m.group(2)
                fields = _parse_ts_fields(body)
                if fields:  # skip empty
                    interfaces[name] = TsInterface(
                        name=name, fields=fields, source_file=ts_file
                    )
    return interfaces


# ---------------------------------------------------------------------------
# Model matching — heuristic name pairing
# ---------------------------------------------------------------------------


def _candidate_ts_names(py_name: str) -> List[str]:
    """
    Generate a ranked list of TypeScript interface name candidates for a
    given Python model class name.
    """
    candidates: List[str] = [py_name]  # exact match first

    # Strip common suffixes
    for suffix in ("Response", "Request", "Schema", "Model", "Out", "In"):
        if py_name.endswith(suffix):
            stripped = py_name[: -len(suffix)]
            candidates.append(stripped)
            # "Api" prefix variant
            candidates.append(f"Api{py_name}")
            candidates.append(f"Api{stripped}")
            break

    # Add "Api" prefix unconditionally
    if not py_name.startswith("Api"):
        candidates.append(f"Api{py_name}")

    # Create / Update prefix variants
    for prefix in ("Create", "Update", "Delete", "Get"):
        if py_name.startswith(prefix):
            base = py_name[len(prefix) :]
            candidates.append(base)
            break

    return candidates


def match_models(
    py_models: Dict[str, PyModel],
    ts_interfaces: Dict[str, TsInterface],
) -> List[Tuple[PyModel, TsInterface]]:
    """Return paired (PyModel, TsInterface) tuples using heuristic name matching."""
    pairs: List[Tuple[PyModel, TsInterface]] = []
    for py_name, py_model in py_models.items():
        for candidate in _candidate_ts_names(py_name):
            if candidate in ts_interfaces:
                pairs.append((py_model, ts_interfaces[candidate]))
                break
    return pairs


# ---------------------------------------------------------------------------
# Field comparison
# ---------------------------------------------------------------------------

# TypeScript type strings that are considered loosely compatible with any
# Python type (prevents false positives for union + alias types).
_TS_OPAQUE_COMPATIBLE = {"any", "unknown", "never", "object"}

# Pairs of (py_ts_canonical, ts_canonical) that are considered compatible.
_COMPATIBLE_PAIRS: Set[Tuple[str, str]] = {
    ("string", "DecimalStr"),
    ("string", "DateTimeStr"),
    ("string", "string | null"),
    ("string", "number"),  # when backend uses Decimal which serialises as string
    ("number", "string"),  # edge case: some TS types model numbers as strings
    ("string | null", "null"),
    ("number | null", "null"),
    ("boolean | null", "null"),
    ("string | null", "string"),
    ("number | null", "number"),
    ("boolean | null", "boolean"),
}


def _types_compatible(py_ts: str, ts: str) -> bool:
    """
    Return True if the TypeScript translation of the Python type is
    compatible with the declared TypeScript type.

    This is deliberately permissive to avoid false positives.
    """
    # Normalise
    py_norm = py_ts.strip()
    ts_norm = ts.strip().rstrip(";")

    if py_norm == ts_norm:
        return True
    if ts_norm in _TS_OPAQUE_COMPATIBLE or py_norm in _TS_OPAQUE_COMPATIBLE:
        return True
    if (py_norm, ts_norm) in _COMPATIBLE_PAIRS or (
        ts_norm,
        py_norm,
    ) in _COMPATIBLE_PAIRS:
        return True

    # Array compatibility: X[] ↔ Array<X>
    if py_norm.endswith("[]") and ts_norm.startswith("Array<"):
        return True
    if ts_norm.endswith("[]") and py_norm.startswith("Array<"):
        return True

    # Nullable variants: treat X and X | null / X | undefined as same base
    def _base_type(t: str) -> str:
        return re.sub(r"\s*\|\s*(null|undefined)", "", t).strip()

    if _base_type(py_norm) == _base_type(ts_norm):
        return True

    # If both sides resolve to "string" family
    if py_norm in _STRING_COMPATIBLE_TS and ts_norm in _STRING_COMPATIBLE_TS:
        return True

    # Record / object compatibility
    if "Record<" in py_norm and "Record<" in ts_norm:
        return True
    if py_norm in ("Record<string, any>", "object") and ts_norm in (
        "Record<string, any>",
        "object",
        "{}",
        "Record<string, unknown>",
    ):
        return True

    return False


def compare_models(
    py_model: PyModel,
    ts_iface: TsInterface,
    verbose: bool = False,
) -> List[Mismatch]:
    """Compare fields of a matched Python model and TypeScript interface."""
    mismatches: List[Mismatch] = []

    py_field_map = {f.name: f for f in py_model.fields}
    ts_field_map = {f.name: f for f in ts_iface.fields}

    # Check all Python fields exist in TypeScript (and types match)
    for py_field in py_model.fields:
        ts_field = ts_field_map.get(py_field.name)
        if ts_field is None:
            mismatches.append(
                Mismatch(
                    kind="missing_field",
                    py_model=py_model.name,
                    ts_interface=ts_iface.name,
                    field=py_field.name,
                    py_type=py_field.py_type,
                    ts_type="MISSING",
                    severity="ERROR",
                )
            )
            continue

        # Type comparison
        py_ts = _py_type_to_ts(py_field.py_type)
        if not _types_compatible(py_ts, ts_field.ts_type):
            # Only flag as WARNING when types are known complex/aliased
            is_known_complex = any(
                kw in py_field.py_type
                for kw in ("List", "Dict", "Optional", "Union", "Any")
            ) or any(
                kw in ts_field.ts_type for kw in ("[]", "Record<", "Array<", "|", "&")
            )
            severity = "WARNING" if is_known_complex else "ERROR"
            mismatches.append(
                Mismatch(
                    kind="type_conflict",
                    py_model=py_model.name,
                    ts_interface=ts_iface.name,
                    field=py_field.name,
                    py_type=f"{py_field.py_type} → {py_ts}",
                    ts_type=ts_field.ts_type,
                    severity=severity,
                )
            )
        elif verbose:
            print(
                f"  OK  {py_model.name}.{py_field.name}: "
                f"{py_field.py_type} ↔ {ts_field.ts_type} ({ts_iface.name})"
            )

    # Check for TypeScript fields not in Python (extra fields)
    for ts_field in ts_iface.fields:
        if ts_field.name not in py_field_map:
            # Extra TS fields are common (frontend adds UI helpers), so just WARN
            mismatches.append(
                Mismatch(
                    kind="extra_field",
                    py_model=py_model.name,
                    ts_interface=ts_iface.name,
                    field=ts_field.name,
                    py_type="MISSING",
                    ts_type=ts_field.ts_type,
                    severity="WARNING",
                )
            )

    return mismatches


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def _format_mismatch(m: Mismatch) -> str:
    if m.kind == "missing_field":
        return (
            f"  {m.severity}: {m.py_model}.{m.field} ({m.py_type})"
            f" ↔ {m.ts_interface}.{m.field} (MISSING in TypeScript)"
        )
    if m.kind == "extra_field":
        return (
            f"  {m.severity}: {m.ts_interface}.{m.field} ({m.ts_type})"
            f" — extra field in TypeScript, not in {m.py_model}"
        )
    return (
        f"  {m.severity}: {m.py_model}.{m.field} ({m.py_type})"
        f" ↔ {m.ts_interface}.{m.field} ({m.ts_type}) — type conflict"
    )


# ---------------------------------------------------------------------------
# Main logic
# ---------------------------------------------------------------------------


def run(
    *,
    dry_run: bool = False,
    exclude: List[str] = (),
    verbose: bool = False,
) -> int:
    """
    Execute the full contract check.

    Returns 0 on success, 1 if definitive mismatches are found.
    """
    # ------------------------------------------------------------------
    # Resolve directories
    # ------------------------------------------------------------------
    model_scan_dirs = BACKEND_API_DIRS + BACKEND_MODEL_DIRS
    frontend_scan_dirs = [FRONTEND_API_DIR, FRONTEND_TYPES_DIR]

    if dry_run:
        print("DRY RUN — files that would be scanned:\n")
        print("Backend Python files:")
        for f in _collect_py_files(model_scan_dirs):
            print(f"  {f.relative_to(PROJECT_ROOT)}")
        print("\nFrontend TypeScript files:")
        for f in _collect_ts_files(frontend_scan_dirs):
            print(f"  {f.relative_to(PROJECT_ROOT)}")
        return 0

    # ------------------------------------------------------------------
    # Parse
    # ------------------------------------------------------------------
    print("Scanning backend Pydantic models…")
    py_models = parse_backend_models(model_scan_dirs)
    print(f"  Found {len(py_models)} Python model classes.")

    print("Scanning frontend TypeScript interfaces…")
    ts_interfaces = parse_frontend_interfaces(frontend_scan_dirs)
    print(f"  Found {len(ts_interfaces)} TypeScript interfaces/types.")

    # ------------------------------------------------------------------
    # Apply exclusions
    # ------------------------------------------------------------------
    excluded_set: Set[str] = set()
    for pattern in exclude:
        for name in list(py_models.keys()):
            if fnmatch.fnmatch(name, pattern):
                del py_models[name]
                excluded_set.add(name)
    if excluded_set:
        print(
            f"  Excluded {len(excluded_set)} model(s): {', '.join(sorted(excluded_set))}"
        )

    # ------------------------------------------------------------------
    # Match and compare
    # ------------------------------------------------------------------
    print("\nMatching models…")
    pairs = match_models(py_models, ts_interfaces)
    matched_py_names = {p[0].name for p in pairs}
    unmatched = [m for name, m in py_models.items() if name not in matched_py_names]

    print(f"  Matched {len(pairs)} pair(s).")
    if unmatched:
        print(
            f"  Unmatched Python models (no TypeScript counterpart found): {len(unmatched)}"
        )
        if verbose:
            for m in sorted(unmatched, key=lambda x: x.name):
                print(
                    f"    UNMATCHED: {m.name}  ({m.source_file.relative_to(PROJECT_ROOT)})"
                )

    print("\nComparing fields…\n")
    all_mismatches: List[Mismatch] = []
    for py_model, ts_iface in sorted(pairs, key=lambda p: p[0].name):
        mismatches = compare_models(py_model, ts_iface, verbose=verbose)
        if mismatches:
            definitive = [m for m in mismatches if m.severity == "ERROR"]
            warnings = [m for m in mismatches if m.severity == "WARNING"]
            label = "ERROR" if definitive else "WARN"
            print(
                f"[{label}] {py_model.name} ↔ {ts_iface.name}"
                f"  ({py_model.source_file.name} ↔ {ts_iface.source_file.name})"
            )
            for m in mismatches:
                print(_format_mismatch(m))
            print()
            all_mismatches.extend(mismatches)
        elif verbose:
            print(
                f"[OK]  {py_model.name} ↔ {ts_iface.name}"
                f"  ({len(py_model.fields)} fields, all match)"
            )

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    errors = [m for m in all_mismatches if m.severity == "ERROR"]
    warnings = [m for m in all_mismatches if m.severity == "WARNING"]

    print("-" * 70)
    print(
        f"Summary: {len(pairs)} pairs checked, "
        f"{len(errors)} error(s), {len(warnings)} warning(s), "
        f"{len(unmatched)} unmatched model(s)."
    )

    if errors:
        print(
            f"\nFound {len(errors)} definitive mismatch(es). "
            "Review and fix before merging."
        )
        return 1

    if warnings:
        print(
            f"\n{len(warnings)} warning(s) found (complex/optional types — "
            "review manually if needed). No definitive mismatches."
        )

    print("\nNo definitive API contract mismatches detected.")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="api-contract-check",
        description=(
            "Heuristic API contract checker — compares Pydantic response "
            "models with TypeScript interfaces to detect field mismatches."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/api-contract-check.py
  python scripts/api-contract-check.py --verbose
  python scripts/api-contract-check.py --dry-run
  python scripts/api-contract-check.py --exclude 'Internal*' --exclude 'Webhook*'

Exit codes:
  0  No definitive mismatches found.
  1  One or more definitive field-name or type mismatches found.
""",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List files that would be scanned without scanning them.",
    )
    parser.add_argument(
        "--exclude",
        metavar="PATTERN",
        action="append",
        default=[],
        help=(
            "Glob pattern for Python model names to exclude (e.g. 'Internal*'). "
            "May be repeated."
        ),
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show all matched fields, not just mismatches.",
    )
    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    sys.exit(
        run(
            dry_run=args.dry_run,
            exclude=args.exclude,
            verbose=args.verbose,
        )
    )


if __name__ == "__main__":
    main()
