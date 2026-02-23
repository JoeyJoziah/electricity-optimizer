#!/usr/bin/env python3
"""
Notion Database Schema Setup for Electricity Optimizer

One-time idempotent script that PATCHes the Notion roadmap database
to add all 13 required properties. Safe to re-run -- Notion ignores
properties that already exist with the same type.

Usage:
    python3 scripts/notion_setup_schema.py
    python3 scripts/notion_setup_schema.py --dry-run
"""

import json
import os
import sys
import time
from pathlib import Path
from typing import Dict

import requests

PROJECT_ROOT = Path(__file__).parent.parent


def load_config() -> Dict:
    config_path = PROJECT_ROOT / ".notion_sync_config.json"
    with open(config_path) as f:
        return json.load(f)


def get_notion_api_key(config: Dict) -> str:
    """NOTION_API_KEY env var in CI, falls back to local file."""
    env_key = os.environ.get("NOTION_API_KEY")
    if env_key:
        return env_key.strip()
    key_path = Path(config["notion"]["api_key_path"]).expanduser()
    return key_path.read_text().strip()


def notion_headers(api_key: str) -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json",
    }


def _request_with_retry(method: str, url: str, headers: Dict, **kwargs) -> requests.Response:
    """Make a request with retry on 429 / 5xx."""
    max_retries = 3
    for attempt in range(max_retries):
        resp = requests.request(method, url, headers=headers, **kwargs)
        if resp.status_code == 429 or resp.status_code >= 500:
            wait = (attempt + 1) * 2
            print(f"  Retrying in {wait}s (HTTP {resp.status_code})...")
            time.sleep(wait)
            continue
        resp.raise_for_status()
        return resp
    resp.raise_for_status()
    return resp


SCHEMA_PROPERTIES = {
    # Title is the default property -- included for completeness but Notion
    # databases always have a title column so this is a no-op.
    "Title": {"title": {}},
    "Status": {
        "select": {
            "options": [
                {"name": "Not Started", "color": "default"},
                {"name": "Planning", "color": "yellow"},
                {"name": "In Progress", "color": "blue"},
                {"name": "Blocked", "color": "red"},
                {"name": "Review", "color": "purple"},
                {"name": "Done", "color": "green"},
            ]
        }
    },
    "Phase": {
        "select": {
            "options": [
                {"name": "Phase 1: Backend Core", "color": "orange"},
                {"name": "Phase 2: Frontend", "color": "blue"},
                {"name": "Phase 3: Data/ML", "color": "purple"},
                {"name": "Phase 4: Infrastructure", "color": "gray"},
                {"name": "Phase 5: Security & Compliance", "color": "red"},
            ]
        }
    },
    "Priority": {
        "select": {
            "options": [
                {"name": "Critical", "color": "red"},
                {"name": "High", "color": "orange"},
                {"name": "Medium", "color": "yellow"},
                {"name": "Low", "color": "default"},
            ]
        }
    },
    "Category": {
        "select": {
            "options": [
                {"name": "Backend", "color": "blue"},
                {"name": "Frontend", "color": "green"},
                {"name": "Data/ML", "color": "purple"},
                {"name": "Infrastructure", "color": "gray"},
                {"name": "Security", "color": "red"},
                {"name": "Testing", "color": "yellow"},
                {"name": "Documentation", "color": "default"},
            ]
        }
    },
    "Milestone": {
        "select": {
            "options": [
                {"name": "MVP", "color": "blue"},
                {"name": "Beta", "color": "green"},
                {"name": "v1.0", "color": "purple"},
            ]
        }
    },
    "Assignee": {
        "select": {
            "options": []
        }
    },
    "Start Date": {"date": {}},
    "Due Date": {"date": {}},
    "Progress": {"number": {"format": "percent"}},
    "Notes": {"rich_text": {}},
    "GitHub Issue": {"url": {}},
    "Related PRs": {"url": {}},
}


def validate_database(database_id: str, headers: Dict) -> Dict:
    """Fetch current database metadata to validate it exists."""
    resp = _request_with_retry(
        "GET",
        f"https://api.notion.com/v1/databases/{database_id}",
        headers,
    )
    return resp.json()


def setup_schema(database_id: str, headers: Dict, dry_run: bool = False) -> None:
    """PATCH the database to add all required properties."""
    print(f"Database ID: {database_id}")
    print(f"Setting up {len(SCHEMA_PROPERTIES)} properties...")
    if dry_run:
        print("(DRY RUN -- no changes will be made)\n")

    # Validate the database exists first
    db_info = validate_database(database_id, headers)
    db_title = ""
    title_parts = db_info.get("title", [])
    if title_parts:
        db_title = title_parts[0].get("plain_text", "")
    print(f"Database: {db_title or '(untitled)'}")

    existing = set(db_info.get("properties", {}).keys())
    print(f"Existing properties: {', '.join(sorted(existing)) or '(none)'}\n")

    if dry_run:
        for name, prop_def in SCHEMA_PROPERTIES.items():
            prop_type = next(iter(prop_def))
            status = "exists" if name in existing else "CREATE"
            print(f"  [{status:>6}] {name} ({prop_type})")
        print("\nDry run complete. Re-run without --dry-run to apply.")
        return

    # Build the properties payload
    props_payload = dict(SCHEMA_PROPERTIES)

    # If the title column is named "Name" (Notion default), rename it to "Title"
    existing_props = db_info.get("properties", {})
    if "Name" in existing_props and "Title" not in existing_props:
        name_id = existing_props["Name"]["id"]
        print(f"  Renaming title column 'Name' -> 'Title' (id: {name_id})")
        # Remove the generic "Title" entry and use the property ID to rename
        props_payload.pop("Title", None)
        props_payload[name_id] = {"name": "Title", "title": {}}

    # Notion's database update API accepts all properties in a single PATCH
    payload = {"properties": props_payload}
    _request_with_retry(
        "PATCH",
        f"https://api.notion.com/v1/databases/{database_id}",
        headers,
        json=payload,
    )

    # Verify by re-fetching
    db_info = validate_database(database_id, headers)
    final_props = db_info.get("properties", {})
    print("Schema applied. Final properties:")
    for name in sorted(final_props.keys()):
        prop_type = final_props[name]["type"]
        print(f"  {name} ({prop_type})")
    print(f"\nTotal: {len(final_props)} properties")


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Set up Notion database schema for Electricity Optimizer roadmap"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be created without making changes",
    )
    args = parser.parse_args()

    config = load_config()
    database_id = config["notion"]["database_id"]
    api_key = get_notion_api_key(config)
    headers = notion_headers(api_key)

    setup_schema(database_id, headers, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
