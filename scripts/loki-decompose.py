#!/usr/bin/env python3
"""
PRD Decomposer — Parse a Loki PRD markdown file into structured tasks.

Reads a PRD file (based on .loki/prd-template.md), extracts requirements
and acceptance criteria, and outputs a JSON task list for the RARV orchestrator.

Usage:
    python3 scripts/loki-decompose.py .loki/prds/my-feature.md
    python3 scripts/loki-decompose.py .loki/prds/my-feature.md --output .loki/tasks.json
"""

import json
import re
import sys
from pathlib import Path
from typing import Any


def parse_prd(prd_path: str) -> dict[str, Any]:
    """Parse a PRD markdown file into structured data."""
    text = Path(prd_path).read_text(encoding="utf-8")

    # Extract title
    title_match = re.search(r"^#\s+Feature:\s*(.+)$", text, re.MULTILINE)
    title = title_match.group(1).strip() if title_match else Path(prd_path).stem

    # Extract sections
    sections: dict[str, str] = {}
    current_section = None
    current_lines: list[str] = []

    for line in text.splitlines():
        header_match = re.match(r"^##\s+(.+)$", line)
        if header_match:
            if current_section:
                sections[current_section] = "\n".join(current_lines).strip()
            current_section = header_match.group(1).strip()
            current_lines = []
        elif current_section:
            current_lines.append(line)

    if current_section:
        sections[current_section] = "\n".join(current_lines).strip()

    # Parse numbered requirements
    requirements: list[dict[str, str]] = []
    req_text = sections.get("Requirements", "")
    for match in re.finditer(
        r"^(\d+)\.\s+\*\*(.+?)\*\*\s*[-—:]\s*(.+?)(?=\n\d+\.|\n##|\Z)",
        req_text,
        re.MULTILINE | re.DOTALL,
    ):
        requirements.append({
            "id": f"REQ-{match.group(1)}",
            "title": match.group(2).strip(),
            "description": match.group(3).strip(),
        })

    # Fallback: plain numbered list without bold
    if not requirements:
        for match in re.finditer(
            r"^(\d+)\.\s+(.+?)(?=\n\d+\.|\n##|\Z)",
            req_text,
            re.MULTILINE | re.DOTALL,
        ):
            requirements.append({
                "id": f"REQ-{match.group(1)}",
                "title": match.group(2).strip().split("\n")[0],
                "description": match.group(2).strip(),
            })

    # Parse acceptance criteria
    criteria: list[str] = []
    ac_text = sections.get("Acceptance Criteria", "")
    for match in re.finditer(r"^-\s+(.+)$", ac_text, re.MULTILINE):
        criteria.append(match.group(1).strip())

    # Parse technical constraints
    constraints: list[str] = []
    tc_text = sections.get("Technical Constraints", "")
    for match in re.finditer(r"^-\s+(.+)$", tc_text, re.MULTILINE):
        constraints.append(match.group(1).strip())

    # Generate tasks from requirements
    tasks: list[dict[str, Any]] = []
    for i, req in enumerate(requirements):
        task: dict[str, Any] = {
            "id": f"TASK-{i + 1}",
            "requirement": req["id"],
            "title": req["title"],
            "description": req["description"],
            "phase": classify_phase(req["title"], req["description"]),
            "status": "pending",
            "verification": [],
        }
        tasks.append(task)

    # Add implicit tasks from acceptance criteria
    if any("test" in c.lower() for c in criteria):
        tasks.append({
            "id": f"TASK-{len(tasks) + 1}",
            "requirement": "AC",
            "title": "Test suite validation",
            "description": "Ensure all existing tests pass and new code has >=80% coverage",
            "phase": "verification",
            "status": "pending",
            "verification": ["backend_tests", "frontend_tests", "ml_tests"],
        })

    if any("doc" in c.lower() or "codemap" in c.lower() for c in criteria):
        tasks.append({
            "id": f"TASK-{len(tasks) + 1}",
            "requirement": "AC",
            "title": "Documentation update",
            "description": "Update codemaps and relevant docs for new code",
            "phase": "documentation",
            "status": "pending",
            "verification": ["docs_updated"],
        })

    return {
        "title": title,
        "source": str(prd_path),
        "requirements": requirements,
        "acceptance_criteria": criteria,
        "constraints": constraints,
        "tasks": tasks,
        "task_count": len(tasks),
    }


def classify_phase(title: str, description: str) -> str:
    """Classify a task into a development phase."""
    text = (title + " " + description).lower()
    if any(w in text for w in ["migration", "schema", "table", "column", "database", "sql"]):
        return "database"
    if any(w in text for w in ["model", "pydantic", "enum", "dataclass", "type"]):
        return "models"
    if any(w in text for w in ["endpoint", "api", "route", "router", "handler"]):
        return "api"
    if any(w in text for w in ["service", "business logic", "orchestrat"]):
        return "services"
    if any(w in text for w in ["component", "page", "frontend", "ui", "react", "hook"]):
        return "frontend"
    if any(w in text for w in ["test", "spec", "coverage", "assert"]):
        return "verification"
    if any(w in text for w in ["ml", "model", "predict", "ensemble", "vector"]):
        return "ml"
    return "implementation"


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python3 scripts/loki-decompose.py <prd-file> [--output <json-file>]", file=sys.stderr)
        sys.exit(1)

    prd_path = sys.argv[1]
    if not Path(prd_path).exists():
        print(f"Error: PRD file not found: {prd_path}", file=sys.stderr)
        sys.exit(1)

    result = parse_prd(prd_path)

    # Output destination
    output_path = None
    if "--output" in sys.argv:
        idx = sys.argv.index("--output")
        if idx + 1 < len(sys.argv):
            output_path = sys.argv[idx + 1]

    json_str = json.dumps(result, indent=2)

    if output_path:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_text(json_str, encoding="utf-8")
        print(f"Wrote {result['task_count']} tasks to {output_path}")
    else:
        print(json_str)


if __name__ == "__main__":
    main()
