#!/usr/bin/env python3
"""
GitHub → Notion Sync Script for Electricity Optimizer
Syncs GitHub issues and PRs to the Notion roadmap database.

Two modes:
  --mode full   Fetches all open + recently closed issues/PRs, upserts to Notion
  --mode event  Processes a single GitHub webhook event (used by Actions)
"""

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional

import requests

# ---------------------------------------------------------------------------
# Configuration helpers
# ---------------------------------------------------------------------------

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


def get_github_token() -> str:
    """GITHUB_TOKEN env var in CI, falls back to `gh auth token` locally."""
    env_token = os.environ.get("GITHUB_TOKEN")
    if env_token:
        return env_token.strip()
    try:
        result = subprocess.run(
            ["gh", "auth", "token"], capture_output=True, text=True, check=True
        )
        return result.stdout.strip()
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        raise RuntimeError(
            "No GITHUB_TOKEN env var and `gh auth token` failed"
        ) from exc


# ---------------------------------------------------------------------------
# GitHub API helpers
# ---------------------------------------------------------------------------

GH_API = "https://api.github.com"


def gh_headers(token: str) -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def fetch_github_items(
    repo: str, token: str, item_type: str, closed_lookback_days: int
) -> List[Dict]:
    """Fetch open + recently-closed issues or pulls from GitHub."""
    endpoint = "issues" if item_type == "issue" else "pulls"
    headers = gh_headers(token)
    items: List[Dict] = []

    for state in ("open", "closed"):
        page = 1
        while True:
            params: Dict = {
                "state": state,
                "per_page": 100,
                "page": page,
                "sort": "updated",
                "direction": "desc",
            }
            resp = requests.get(
                f"{GH_API}/repos/{repo}/{endpoint}",
                headers=headers,
                params=params,
            )
            resp.raise_for_status()
            batch = resp.json()
            if not batch:
                break

            if state == "closed":
                cutoff = datetime.now(timezone.utc) - timedelta(
                    days=closed_lookback_days
                )
                batch = [
                    i
                    for i in batch
                    if datetime.fromisoformat(
                        i["updated_at"].replace("Z", "+00:00")
                    )
                    >= cutoff
                ]
                if not batch:
                    break

            # For the issues endpoint, filter out PRs (they appear as issues too)
            if endpoint == "issues":
                batch = [i for i in batch if "pull_request" not in i]

            items.extend(batch)
            page += 1

    return items


# ---------------------------------------------------------------------------
# Notion API helpers
# ---------------------------------------------------------------------------

NOTION_API = "https://api.notion.com/v1"


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


def find_notion_page(
    database_id: str, headers: Dict, url_field: str, url_value: str
) -> Optional[str]:
    """Query the Notion database for an existing page by URL field value."""
    payload = {
        "filter": {
            "property": url_field,
            "url": {"equals": url_value},
        }
    }
    resp = _request_with_retry(
        "POST",
        f"{NOTION_API}/databases/{database_id}/query",
        headers,
        json=payload,
    )
    results = resp.json().get("results", [])
    if results:
        return results[0]["id"]
    return None


def build_notion_properties(item: Dict, item_type: str, config: Dict) -> Dict:
    """Build the Notion properties payload from a GitHub item."""
    number = item["number"]
    title = item["title"]
    prefix = f"[Issue #{number}]" if item_type == "issue" else f"[PR #{number}]"
    full_title = f"{prefix} {title}"

    # Status mapping
    state = item.get("state", "open")
    is_draft = item.get("draft", False)
    merged = item.get("merged_at") is not None or item.get("pull_request", {}).get("merged_at") is not None
    if item_type == "issue":
        status = "Done" if state == "closed" else "In Progress"
    else:
        if merged:
            status = "Done"
        elif is_draft:
            status = "Planning"
        elif state == "open":
            status = "Review"
        else:
            status = "Done"

    # Label-based priority and category
    labels = [lbl["name"].lower() for lbl in item.get("labels", [])]
    label_mappings = config.get("github_label_mappings", {})

    priority = "Medium"
    for lbl in labels:
        mapped = label_mappings.get("priority", {}).get(lbl)
        if mapped:
            priority = mapped
            break

    category = "Backend"
    for lbl in labels:
        mapped = label_mappings.get("category", {}).get(lbl)
        if mapped:
            category = mapped
            break

    progress = 100 if status == "Done" else 0

    properties: Dict = {
        "Title": {"title": [{"text": {"content": full_title}}]},
        "Status": {"select": {"name": status}},
        "Priority": {"select": {"name": priority}},
        "Category": {"select": {"name": category}},
        "Progress": {"number": progress},
    }

    # URL field — issues use "GitHub Issue", PRs use "Related PRs"
    url_field = "GitHub Issue" if item_type == "issue" else "Related PRs"
    properties[url_field] = {"url": item["html_url"]}

    # Assignee (first one)
    assignees = item.get("assignees", [])
    if assignees:
        properties["Assignee"] = {"select": {"name": assignees[0]["login"]}}

    # Milestone
    milestone = item.get("milestone")
    if milestone and milestone.get("title"):
        properties["Milestone"] = {"select": {"name": milestone["title"]}}

    # Notes (body truncated to 2000 chars)
    body = (item.get("body") or "")[:2000]
    if body:
        properties["Notes"] = {"rich_text": [{"text": {"content": body}}]}

    # Start date
    created = item.get("created_at")
    if created:
        properties["Start Date"] = {"date": {"start": created[:10]}}

    return properties


def upsert_notion_page(
    database_id: str, headers: Dict, item: Dict, item_type: str, config: Dict
) -> str:
    """Create or update a Notion page for a GitHub item. Returns 'created' or 'updated'."""
    url_field = "GitHub Issue" if item_type == "issue" else "Related PRs"
    url_value = item["html_url"]

    existing_id = find_notion_page(database_id, headers, url_field, url_value)
    properties = build_notion_properties(item, item_type, config)

    if existing_id:
        _request_with_retry(
            "PATCH",
            f"{NOTION_API}/pages/{existing_id}",
            headers,
            json={"properties": properties},
        )
        return "updated"
    else:
        _request_with_retry(
            "POST",
            f"{NOTION_API}/pages",
            headers,
            json={"parent": {"database_id": database_id}, "properties": properties},
        )
        return "created"


# ---------------------------------------------------------------------------
# Sync modes
# ---------------------------------------------------------------------------


def full_sync(config: Dict, notion_key: str, gh_token: str):
    """Fetch all open + recently-closed issues and PRs, upsert each to Notion."""
    repo = config["github"]["repo_full_name"]
    database_id = config["notion"]["database_id"]
    lookback = config["github"].get("closed_lookback_days", 30)
    headers = notion_headers(notion_key)

    created = 0
    updated = 0

    for item_type, enabled_key in [("issue", "sync_issues"), ("pull", "sync_prs")]:
        if not config["github"].get(enabled_key, True):
            continue
        label = "issues" if item_type == "issue" else "PRs"
        print(f"Fetching {label} from {repo}...")
        items = fetch_github_items(repo, gh_token, item_type, lookback)
        print(f"  Found {len(items)} {label}")

        for item in items:
            result = upsert_notion_page(database_id, headers, item, item_type, config)
            if result == "created":
                created += 1
            else:
                updated += 1
            time.sleep(0.35)

    print(f"[{datetime.now()}] Full sync complete: {created} created, {updated} updated")


def event_sync(config: Dict, notion_key: str, gh_token: str):
    """Process a single GitHub webhook event from Actions."""
    event_name = os.environ.get("GITHUB_EVENT_NAME", "")
    event_path = os.environ.get("GITHUB_EVENT_PATH", "")

    if not event_path or not os.path.exists(event_path):
        print(f"No event payload at GITHUB_EVENT_PATH={event_path!r}")
        sys.exit(1)

    with open(event_path) as f:
        payload = json.load(f)

    if event_name == "issues":
        item = payload.get("issue", {})
        item_type = "issue"
    elif event_name == "pull_request":
        item = payload.get("pull_request", {})
        item_type = "pull"
    else:
        print(f"Unsupported event: {event_name}")
        sys.exit(1)

    if not item.get("html_url"):
        print("No html_url in event payload, skipping")
        return

    database_id = config["notion"]["database_id"]
    headers = notion_headers(notion_key)

    number = item.get("number", "?")
    action = payload.get("action", "unknown")
    print(f"Processing {event_name} #{number} ({action})...")
    result = upsert_notion_page(database_id, headers, item, item_type, config)
    print(f"  {result.capitalize()} Notion page for {event_name} #{number}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Sync GitHub issues/PRs to Notion")
    parser.add_argument(
        "--mode",
        choices=["full", "event"],
        default="full",
        help="Sync mode: 'full' fetches all items, 'event' processes a webhook event",
    )
    args = parser.parse_args()

    config = load_config()
    if not config.get("github", {}).get("enabled"):
        print("GitHub sync is disabled in config (github.enabled = false)")
        sys.exit(0)

    notion_key = get_notion_api_key(config)
    gh_token = get_github_token()

    if args.mode == "full":
        full_sync(config, notion_key, gh_token)
    elif args.mode == "event":
        event_sync(config, notion_key, gh_token)


if __name__ == "__main__":
    main()
