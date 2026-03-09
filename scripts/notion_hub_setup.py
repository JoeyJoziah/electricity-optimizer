#!/usr/bin/env python3
"""
Notion Hub Setup — Creates the Electricity Optimizer Hub workspace.

Creates:
  1. Hub page (workspace root)
  2. Project Tracker database
  3. Automation Workflows database
  4. Architecture Decisions database
  5. Dashboard sub-pages (linked views)
  6. Backfills all historical data

Usage:
  python3 scripts/notion_hub_setup.py
"""

import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

API_KEY_PATH = os.path.expanduser("~/.config/notion/api_key")
NOTION_BASE = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"
PROJECT_ROOT = Path(__file__).parent.parent
OUTPUT_FILE = PROJECT_ROOT / ".notion_hub_ids.json"

def get_api_key() -> str:
    with open(API_KEY_PATH) as f:
        return f.read().strip()

def headers(api_key: str) -> dict:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Notion-Version": NOTION_VERSION,
    }

def api_post(api_key: str, endpoint: str, data: dict) -> dict:
    """POST to Notion API with retry on rate limit."""
    url = f"{NOTION_BASE}/{endpoint}"
    for attempt in range(3):
        resp = requests.post(url, headers=headers(api_key), json=data)
        if resp.status_code == 429:
            wait = int(resp.headers.get("Retry-After", 2))
            print(f"  Rate limited, waiting {wait}s...")
            time.sleep(wait)
            continue
        if resp.status_code not in (200, 201):
            print(f"  ERROR {resp.status_code}: {resp.text[:500]}")
            resp.raise_for_status()
        return resp.json()
    raise Exception(f"Failed after 3 retries: {endpoint}")

def api_patch(api_key: str, endpoint: str, data: dict) -> dict:
    url = f"{NOTION_BASE}/{endpoint}"
    for attempt in range(3):
        resp = requests.patch(url, headers=headers(api_key), json=data)
        if resp.status_code == 429:
            wait = int(resp.headers.get("Retry-After", 2))
            time.sleep(wait)
            continue
        if resp.status_code not in (200, 201):
            print(f"  ERROR {resp.status_code}: {resp.text[:500]}")
            resp.raise_for_status()
        return resp.json()
    raise Exception(f"Failed after 3 retries: {endpoint}")

def rich_text(content: str) -> list:
    """Helper to create Notion rich_text array."""
    if not content:
        return []
    return [{"type": "text", "text": {"content": content[:2000]}}]

def title_prop(content: str) -> dict:
    return {"title": rich_text(content)}

# ---------------------------------------------------------------------------
# Step 2: Create Hub Page + 3 Databases
# ---------------------------------------------------------------------------

def find_parent_page(api_key: str) -> Optional[str]:
    """Find a workspace-level page to use as parent for the Hub."""
    resp = requests.post(
        f"{NOTION_BASE}/search",
        headers=headers(api_key),
        json={"query": "", "filter": {"value": "page", "property": "object"}, "page_size": 100}
    )
    if resp.status_code == 200:
        for page in resp.json().get("results", []):
            parent = page.get("parent", {})
            if parent.get("type") == "workspace":
                print(f"  Using parent page: {page['id']}")
                return page["id"]
    return None

def create_hub_page(api_key: str) -> str:
    """Create the Electricity Optimizer Hub page under the workspace.

    Internal integrations can't create workspace-root pages, so we find
    a suitable parent page first. If the workspace has a top-level page
    we create the Hub under it; the user can drag it to root in the UI.
    """
    print("Creating Hub page...")

    # Find a workspace-level page to use as parent
    parent_page_id = find_parent_page(api_key)
    if not parent_page_id:
        raise Exception("No accessible workspace page found to create Hub under. "
                        "Share a Notion page with the integration first.")

    data = {
        "parent": {"type": "page_id", "page_id": parent_page_id},
        "icon": {"type": "emoji", "emoji": "⚡"},
        "properties": {
            "title": [{"type": "text", "text": {"content": "Electricity Optimizer Hub"}}]
        },
        "children": [
            {
                "object": "block",
                "type": "callout",
                "callout": {
                    "rich_text": rich_text("Central project hub for the Electricity Optimizer platform. Contains project tracking, automation workflows, and architecture decisions."),
                    "icon": {"type": "emoji", "emoji": "📋"},
                }
            },
            {
                "object": "block",
                "type": "divider",
                "divider": {}
            },
            {
                "object": "block",
                "type": "heading_2",
                "heading_2": {"rich_text": rich_text("Quick Links")}
            },
            {
                "object": "block",
                "type": "bulleted_list_item",
                "bulleted_list_item": {
                    "rich_text": [{"type": "text", "text": {"content": "Production: ", "link": None}}, {"type": "text", "text": {"content": "electricity-optimizer.vercel.app", "link": {"url": "https://electricity-optimizer.vercel.app"}}}]
                }
            },
            {
                "object": "block",
                "type": "bulleted_list_item",
                "bulleted_list_item": {
                    "rich_text": [{"type": "text", "text": {"content": "Backend API: ", "link": None}}, {"type": "text", "text": {"content": "electricity-optimizer.onrender.com", "link": {"url": "https://electricity-optimizer.onrender.com"}}}]
                }
            },
            {
                "object": "block",
                "type": "bulleted_list_item",
                "bulleted_list_item": {
                    "rich_text": [{"type": "text", "text": {"content": "GitHub: ", "link": None}}, {"type": "text", "text": {"content": "JoeyJoziah/electricity-optimizer", "link": {"url": "https://github.com/JoeyJoziah/electricity-optimizer"}}}]
                }
            },
            {
                "object": "block",
                "type": "divider",
                "divider": {}
            },
        ]
    }
    result = api_post(api_key, "pages", data)
    page_id = result["id"]
    print(f"  Hub page created: {page_id}")
    return page_id


def create_project_tracker(api_key: str, parent_id: str) -> str:
    """Create the Project Tracker database."""
    print("Creating Project Tracker database...")
    data = {
        "parent": {"type": "page_id", "page_id": parent_id},
        "icon": {"type": "emoji", "emoji": "🎯"},
        "title": [{"type": "text", "text": {"content": "Project Tracker"}}],
        "is_inline": False,
        "properties": {
            "Name": {"title": {}},
            "Status": {
                "select": {
                    "options": [
                        {"name": "Not Started", "color": "default"},
                        {"name": "In Progress", "color": "blue"},
                        {"name": "Done", "color": "green"},
                        {"name": "Blocked", "color": "red"},
                        {"name": "Archived", "color": "default"},
                    ]
                }
            },
            "Phase": {
                "select": {
                    "options": [
                        {"name": "Foundation", "color": "gray"},
                        {"name": "Backend Core", "color": "blue"},
                        {"name": "ML Pipeline", "color": "purple"},
                        {"name": "Frontend", "color": "green"},
                        {"name": "Testing", "color": "yellow"},
                        {"name": "Security", "color": "red"},
                        {"name": "Infrastructure", "color": "orange"},
                        {"name": "MVP Launch", "color": "pink"},
                        {"name": "Post-MVP", "color": "blue"},
                        {"name": "Automation P0", "color": "gray"},
                        {"name": "Automation P1", "color": "yellow"},
                        {"name": "Automation P2", "color": "orange"},
                        {"name": "Automation P3", "color": "red"},
                    ]
                }
            },
            "Priority": {
                "select": {
                    "options": [
                        {"name": "P0-Critical", "color": "red"},
                        {"name": "P1-High", "color": "orange"},
                        {"name": "P2-Medium", "color": "yellow"},
                        {"name": "P3-Low", "color": "gray"},
                    ]
                }
            },
            "Category": {
                "multi_select": {
                    "options": [
                        {"name": "Backend", "color": "blue"},
                        {"name": "Frontend", "color": "green"},
                        {"name": "ML", "color": "purple"},
                        {"name": "Infrastructure", "color": "orange"},
                        {"name": "Security", "color": "red"},
                        {"name": "Testing", "color": "yellow"},
                        {"name": "Documentation", "color": "gray"},
                        {"name": "DevOps", "color": "brown"},
                        {"name": "Automation", "color": "pink"},
                        {"name": "Database", "color": "blue"},
                        {"name": "Auth", "color": "red"},
                        {"name": "Billing", "color": "green"},
                        {"name": "Connections", "color": "orange"},
                        {"name": "UI/UX", "color": "purple"},
                    ]
                }
            },
            "Milestone": {
                "select": {
                    "options": [
                        {"name": "MVP", "color": "pink"},
                        {"name": "Multi-Utility", "color": "blue"},
                        {"name": "Connections", "color": "orange"},
                        {"name": "Nationwide", "color": "green"},
                        {"name": "Swarm Audit", "color": "purple"},
                        {"name": "UI/UX Overhaul", "color": "yellow"},
                        {"name": "Auth Fix", "color": "red"},
                        {"name": "Integrations", "color": "gray"},
                        {"name": "DB Audit", "color": "blue"},
                        {"name": "Automation P1", "color": "orange"},
                        {"name": "Automation P2", "color": "orange"},
                        {"name": "Automation P3", "color": "red"},
                    ]
                }
            },
            "Date Completed": {"date": {}},
            "Tests Added": {"number": {"format": "number"}},
            "GitHub URL": {"url": {}},
            "Commit": {"rich_text": {}},
            "Notes": {"rich_text": {}},
            "Source": {
                "select": {
                    "options": [
                        {"name": "Backfill", "color": "gray"},
                        {"name": "GitHub Issue", "color": "blue"},
                        {"name": "GitHub PR", "color": "green"},
                        {"name": "Manual", "color": "yellow"},
                    ]
                }
            },
        }
    }
    result = api_post(api_key, "databases", data)
    db_id = result["id"]
    print(f"  Project Tracker created: {db_id}")
    return db_id


def create_automation_workflows(api_key: str, parent_id: str) -> str:
    """Create the Automation Workflows database."""
    print("Creating Automation Workflows database...")
    data = {
        "parent": {"type": "page_id", "page_id": parent_id},
        "icon": {"type": "emoji", "emoji": "🤖"},
        "title": [{"type": "text", "text": {"content": "Automation Workflows"}}],
        "is_inline": False,
        "properties": {
            "Name": {"title": {}},
            "Status": {
                "select": {
                    "options": [
                        {"name": "Active", "color": "green"},
                        {"name": "Paused", "color": "yellow"},
                        {"name": "Deprecated", "color": "red"},
                        {"name": "Planned", "color": "default"},
                    ]
                }
            },
            "Type": {
                "select": {
                    "options": [
                        {"name": "GHA Cron", "color": "blue"},
                        {"name": "Rube Recipe", "color": "purple"},
                        {"name": "Local Hook", "color": "orange"},
                    ]
                }
            },
            "Schedule": {"rich_text": {}},
            "Endpoint": {"url": {}},
            "Recipe ID": {"rich_text": {}},
            "Workflow File": {"rich_text": {}},
            "Phase": {
                "select": {
                    "options": [
                        {"name": "Phase 1", "color": "yellow"},
                        {"name": "Phase 2", "color": "orange"},
                        {"name": "Phase 3", "color": "red"},
                    ]
                }
            },
            "Channels": {
                "multi_select": {
                    "options": [
                        {"name": "Slack #incidents", "color": "red"},
                        {"name": "Slack #deployments", "color": "blue"},
                        {"name": "Slack #metrics", "color": "green"},
                        {"name": "Email", "color": "yellow"},
                        {"name": "Google Sheets", "color": "orange"},
                    ]
                }
            },
            "Notes": {"rich_text": {}},
        }
    }
    result = api_post(api_key, "databases", data)
    db_id = result["id"]
    print(f"  Automation Workflows created: {db_id}")
    return db_id


def create_architecture_decisions(api_key: str, parent_id: str) -> str:
    """Create the Architecture Decisions database."""
    print("Creating Architecture Decisions database...")
    data = {
        "parent": {"type": "page_id", "page_id": parent_id},
        "icon": {"type": "emoji", "emoji": "🏗️"},
        "title": [{"type": "text", "text": {"content": "Architecture Decisions"}}],
        "is_inline": False,
        "properties": {
            "Name": {"title": {}},
            "Date": {"date": {}},
            "Category": {
                "select": {
                    "options": [
                        {"name": "Backend", "color": "blue"},
                        {"name": "Frontend", "color": "green"},
                        {"name": "ML", "color": "purple"},
                        {"name": "Database", "color": "orange"},
                        {"name": "Auth", "color": "red"},
                        {"name": "Billing", "color": "yellow"},
                        {"name": "Infrastructure", "color": "gray"},
                        {"name": "Automation", "color": "pink"},
                    ]
                }
            },
            "Decision": {"rich_text": {}},
            "Rationale": {"rich_text": {}},
            "Status": {
                "select": {
                    "options": [
                        {"name": "Active", "color": "green"},
                        {"name": "Superseded", "color": "red"},
                        {"name": "Revisit", "color": "yellow"},
                    ]
                }
            },
        }
    }
    result = api_post(api_key, "databases", data)
    db_id = result["id"]
    print(f"  Architecture Decisions created: {db_id}")
    return db_id

# ---------------------------------------------------------------------------
# Step 3: Backfill Historical Data
# ---------------------------------------------------------------------------

def backfill_project_tracker(api_key: str, db_id: str):
    """Backfill ~30 milestone entries into Project Tracker."""
    print("Backfilling Project Tracker...")

    entries = [
        # Completed milestones
        {"name": "MVP Launch — Core pricing engine + dashboard", "status": "Done", "phase": "MVP Launch", "priority": "P0-Critical", "categories": ["Backend", "Frontend", "Database"], "milestone": "MVP", "date": "2026-02-06", "tests": 200, "notes": "Initial launch with price comparison, supplier search, optimization recommendations", "source": "Backfill"},
        {"name": "Neon Auth Migration — Better Auth + session cookies", "status": "Done", "phase": "Security", "priority": "P0-Critical", "categories": ["Auth", "Database", "Backend"], "milestone": "Multi-Utility", "date": "2026-02-23", "tests": 50, "notes": "Migrated from JWT to Neon Auth (Better Auth). Session-based, httpOnly cookies, Resend email verification", "source": "Backfill"},
        {"name": "Multi-Utility Expansion — Region enum, 50 states + DC", "status": "Done", "phase": "Backend Core", "priority": "P1-High", "categories": ["Backend", "Database"], "milestone": "Multi-Utility", "date": "2026-02-23", "tests": 30, "notes": "Unified Region enum, backward-compat aliases (PriceRegion, PricingRegion)", "source": "Backfill"},
        {"name": "Adaptive Learning — ML ensemble predictor + HNSW vectors", "status": "Done", "phase": "ML Pipeline", "priority": "P1-High", "categories": ["ML"], "milestone": "Multi-Utility", "date": "2026-02-23", "tests": 100, "notes": "Ensemble predictor with HNSW vector search, observation loop, nightly learning", "source": "Backfill"},
        {"name": "Connection Feature Phase 1 — Foundation + schema", "status": "Done", "phase": "Backend Core", "priority": "P1-High", "categories": ["Backend", "Database", "Connections"], "milestone": "Connections", "date": "2026-02-25", "tests": 40, "notes": "connection_extracted_rates table, effective_date, supplier_name on user_connections", "source": "Backfill"},
        {"name": "Connection Feature Phase 2 — Bill OCR upload", "status": "Done", "phase": "Backend Core", "priority": "P1-High", "categories": ["Backend", "Connections"], "milestone": "Connections", "date": "2026-02-25", "tests": 30, "notes": "10MB body size limit for /connections/upload", "source": "Backfill"},
        {"name": "Connection Feature Phase 3 — Email OAuth", "status": "Done", "phase": "Backend Core", "priority": "P2-Medium", "categories": ["Backend", "Auth", "Connections"], "milestone": "Connections", "date": "2026-02-25", "tests": 20, "notes": "Email OAuth fail-fast pattern", "source": "Backfill"},
        {"name": "Connection Feature Phase 4 — UtilityAPI sync", "status": "Done", "phase": "Backend Core", "priority": "P1-High", "categories": ["Backend", "Connections", "Infrastructure"], "milestone": "Connections", "date": "2026-02-25", "tests": 25, "notes": "sync_all_due() with auto-sync via POST /internal/sync-connections", "source": "Backfill"},
        {"name": "Connection Feature Phase 5 — Analytics dashboard", "status": "Done", "phase": "Frontend", "priority": "P2-Medium", "categories": ["Frontend", "Connections"], "milestone": "Connections", "date": "2026-02-25", "tests": 15, "notes": "Connection analytics UI components", "source": "Backfill"},
        {"name": "Nationwide Expansion — Stream-chain pipelines, gap remediation", "status": "Done", "phase": "Backend Core", "priority": "P1-High", "categories": ["Backend", "Infrastructure"], "milestone": "Nationwide", "date": "2026-02-26", "tests": 50, "notes": "Stream-chain pipelines for all 50 states data processing", "source": "Backfill"},
        {"name": "Swarm Audit — 6 batches, 107 files reviewed", "status": "Done", "phase": "Testing", "priority": "P1-High", "categories": ["Testing", "Documentation"], "milestone": "Swarm Audit", "date": "2026-03-02", "tests": 0, "notes": "Multi-agent swarm code audit across entire codebase", "source": "Backfill"},
        {"name": "UI/UX Overhaul — Design system, Input component refactor", "status": "Done", "phase": "Frontend", "priority": "P1-High", "categories": ["Frontend", "UI/UX"], "milestone": "UI/UX Overhaul", "date": "2026-03-03", "tests": 51, "notes": "Design tokens, shared Input component, CSS variables, standardized colors. jest-axe a11y tests (51)", "source": "Backfill"},
        {"name": "Auth System Fix — Resend, magic link, OAuth conditional", "status": "Done", "phase": "Security", "priority": "P0-Critical", "categories": ["Auth", "Backend", "Frontend"], "milestone": "Auth Fix", "date": "2026-03-04", "tests": 20, "notes": "SendGrid->Resend migration, magic link server+client plugin, conditional OAuth buttons", "source": "Backfill"},
        {"name": "Same-Origin Proxy — Next.js rewrites for API calls", "status": "Done", "phase": "Infrastructure", "priority": "P0-Critical", "categories": ["Frontend", "Infrastructure"], "milestone": "Auth Fix", "date": "2026-03-04", "tests": 5, "notes": "Fixed URI_TOO_LONG + cookie issues. /api/v1/* proxied via BACKEND_URL server-side", "source": "Backfill"},
        {"name": "Agentic-Flow Integration — 34 agents, 8 skills (af-* namespace)", "status": "Done", "phase": "Infrastructure", "priority": "P2-Medium", "categories": ["Infrastructure", "DevOps"], "milestone": "Integrations", "date": "2026-03-04", "tests": 0, "notes": "SPARC mode, af-* namespace symlinks, MCP tools as mcp__agentic-flow__*", "source": "Backfill"},
        {"name": "Multi-Repo Skill Integration — 2,492 entities from 15 repos", "status": "Done", "phase": "Infrastructure", "priority": "P2-Medium", "categories": ["Infrastructure", "DevOps"], "milestone": "Integrations", "date": "2026-03-04", "tests": 0, "notes": "2,099 skills, 204 commands, 189 agents. Vendor-first routing. Manifests in ~/.claude/integrations/", "source": "Backfill"},
        {"name": "Connection Bug Fixes — Migrations 021-022", "status": "Done", "phase": "Backend Core", "priority": "P1-High", "categories": ["Backend", "Database", "Connections"], "milestone": "Integrations", "date": "2026-03-04", "tests": 10, "notes": "Email OAuth fail-fast, bill upload timeout, settings page fixes", "source": "Backfill"},
        {"name": "DB Audit — Migration 023, bulk_create, pool optimization", "status": "Done", "phase": "Backend Core", "priority": "P1-High", "categories": ["Backend", "Database"], "milestone": "DB Audit", "date": "2026-03-05", "tests": 15, "notes": "O(n+m) check_thresholds, PgBouncer statement_cache_size=0, pool: size=3/overflow=5", "source": "Backfill"},
        {"name": "Composio Integrations — 16 active connections", "status": "Done", "phase": "Infrastructure", "priority": "P2-Medium", "categories": ["Infrastructure", "Automation"], "milestone": "DB Audit", "date": "2026-03-05", "tests": 0, "notes": "Gmail, GitHub, Firecrawl, Sentry, Vercel, Resend, Stripe, Render, Sheets, Drive, UptimeRobot, OneSignal, Better Stack, Slack, Notion, Neon", "source": "Backfill"},
        {"name": "Automation Phase 0 — 4 prerequisite blockers resolved", "status": "Done", "phase": "Automation P0", "priority": "P0-Critical", "categories": ["Backend", "Automation"], "milestone": "Automation P1", "date": "2026-03-05", "tests": 18, "notes": "B1: Gmail SMTP fallback. B2: OneSignal binding. B3: Stripe customer ID resolution. B4: Alert system wiring", "source": "Backfill"},
        {"name": "Automation Phase 1 — 3 Rube recipes (Sentry, Deploy, Notion)", "status": "Done", "phase": "Automation P1", "priority": "P1-High", "categories": ["Automation", "Infrastructure"], "milestone": "Automation P1", "date": "2026-03-06", "tests": 0, "notes": "rcp_sQ1NKouFdXIe (Sentry/15min), rcp_9f8mVE2Z_DSP (Deploy/hourly), rcp_73Kc9K65YC5T (GitHub->Notion/6h)", "source": "Backfill"},
        {"name": "Automation Phase 2 — 5 GHA cron workflows", "status": "Done", "phase": "Automation P2", "priority": "P1-High", "categories": ["Automation", "Infrastructure", "DevOps"], "milestone": "Automation P2", "date": "2026-03-06", "tests": 9, "notes": "check-alerts (*/15min), fetch-weather (*/6h), market-research (daily 2am), sync-connections (*/2h), scrape-rates (daily 3am)", "source": "Backfill"},
        {"name": "Automation Phase 3 — Stripe dunning + KPI report", "status": "Done", "phase": "Automation P3", "priority": "P1-High", "categories": ["Automation", "Billing", "Backend"], "milestone": "Automation P3", "date": "2026-03-06", "tests": 27, "notes": "Migration 024 (payment_retry_history). DunningService: 24h dedup, soft/final emails, downgrade after 3 fails. KPI: 8 metrics. 2 GHA crons", "source": "Backfill"},
        {"name": "Notion Hub Rebuild — Fresh workspace, backfill, single sync", "status": "Done", "phase": "Infrastructure", "priority": "P1-High", "categories": ["Infrastructure", "Documentation"], "milestone": "Automation P3", "date": "2026-03-06", "tests": 0, "notes": "Replaced broken triple-sync with clean Hub + 3 databases + Rube-only sync", "source": "Backfill"},
        # Future work items (Not Started)
        {"name": "NotificationDispatcher — Unified push/email/in-app routing", "status": "Not Started", "phase": "Backend Core", "priority": "P2-Medium", "categories": ["Backend", "Infrastructure"], "milestone": None, "date": None, "tests": 0, "notes": "Central notification routing service. Currently email + OneSignal are separate paths", "source": "Backfill"},
        {"name": "ML Weight Persistence — Nightly model checkpoint saves", "status": "Not Started", "phase": "ML Pipeline", "priority": "P2-Medium", "categories": ["ML", "Infrastructure"], "milestone": None, "date": None, "tests": 0, "notes": "Persist ensemble weights across Render restarts. Currently retrains from scratch", "source": "Backfill"},
        {"name": "In-App Notification Center — Real-time alerts in dashboard", "status": "Not Started", "phase": "Frontend", "priority": "P3-Low", "categories": ["Frontend", "UI/UX"], "milestone": None, "date": None, "tests": 0, "notes": "WebSocket-based notification feed in dashboard sidebar", "source": "Backfill"},
        {"name": "Custom Email Domain — Resend domain + DKIM/SPF/DMARC", "status": "Not Started", "phase": "Infrastructure", "priority": "P2-Medium", "categories": ["Infrastructure"], "milestone": None, "date": None, "tests": 0, "notes": "Replace onboarding@resend.dev sandbox with custom domain. Required for non-account emails", "source": "Backfill"},
        {"name": "Rate Comparison Widget — Embeddable pricing widget", "status": "Not Started", "phase": "Frontend", "priority": "P3-Low", "categories": ["Frontend"], "milestone": None, "date": None, "tests": 0, "notes": "Embeddable <iframe> or Web Component for partner sites", "source": "Backfill"},
        {"name": "Admin Dashboard — Internal metrics + user management", "status": "Not Started", "phase": "Frontend", "priority": "P2-Medium", "categories": ["Frontend", "Backend"], "milestone": None, "date": None, "tests": 0, "notes": "Protected /admin route for viewing KPIs, managing users, triggering manual syncs", "source": "Backfill"},
        {"name": "API Rate Limiting — Per-user throttling with Redis", "status": "Not Started", "phase": "Security", "priority": "P2-Medium", "categories": ["Backend", "Security"], "milestone": None, "date": None, "tests": 0, "notes": "Replace simple IP-based limits with user-tier-aware rate limiting (Free: 100/h, Pro: 500/h, Business: 2000/h)", "source": "Backfill"},
        {"name": "Stale Neon Project Cleanup — Delete holy-pine-81107663", "status": "Not Started", "phase": "Infrastructure", "priority": "P3-Low", "categories": ["Database", "Infrastructure"], "milestone": None, "date": None, "tests": 0, "notes": "Old Neon project from initial setup. Manual deletion via Neon console", "source": "Backfill"},
    ]

    for i, entry in enumerate(entries):
        props: Dict[str, Any] = {
            "Name": title_prop(entry["name"]),
            "Source": {"select": {"name": entry["source"]}},
        }
        if entry.get("status"):
            props["Status"] = {"select": {"name": entry["status"]}}
        if entry.get("phase"):
            props["Phase"] = {"select": {"name": entry["phase"]}}
        if entry.get("priority"):
            props["Priority"] = {"select": {"name": entry["priority"]}}
        if entry.get("categories"):
            props["Category"] = {"multi_select": [{"name": c} for c in entry["categories"]]}
        if entry.get("milestone"):
            props["Milestone"] = {"select": {"name": entry["milestone"]}}
        if entry.get("date"):
            props["Date Completed"] = {"date": {"start": entry["date"]}}
        if entry.get("tests") and entry["tests"] > 0:
            props["Tests Added"] = {"number": entry["tests"]}
        if entry.get("notes"):
            props["Notes"] = {"rich_text": rich_text(entry["notes"])}

        api_post(api_key, "pages", {
            "parent": {"database_id": db_id},
            "properties": props,
        })
        print(f"  [{i+1}/{len(entries)}] {entry['name'][:60]}...")
        time.sleep(0.35)  # Rate limit safety

    print(f"  Backfilled {len(entries)} project entries")


def backfill_automation_workflows(api_key: str, db_id: str):
    """Backfill 9+ automation workflow entries."""
    print("Backfilling Automation Workflows...")

    workflows = [
        # Phase 1 — Rube recipes
        {"name": "Sentry-to-Slack Bridge", "status": "Active", "type": "Rube Recipe", "schedule": "*/15 * * * *", "recipe_id": "rcp_sQ1NKouFdXIe", "phase": "Phase 1", "channels": ["Slack #incidents"], "notes": "Fetches unresolved Sentry issues, classifies P0-P3, posts to #incidents (C0AKV2TK257)"},
        {"name": "Deploy Notifications", "status": "Active", "type": "Rube Recipe", "schedule": "0 * * * *", "recipe_id": "rcp_9f8mVE2Z_DSP", "phase": "Phase 1", "channels": ["Slack #deployments"], "notes": "Checks Render backend+frontend status, posts to #deployments (C0AKCN6T02Z), creates Better Stack incident on failures"},
        {"name": "GitHub-to-Notion Roadmap Sync", "status": "Active", "type": "Rube Recipe", "schedule": "0 */6 * * *", "recipe_id": "rcp_73Kc9K65YC5T", "phase": "Phase 1", "channels": [], "notes": "Syncs GitHub issues/PRs to Notion Project Tracker. Will be replaced with new recipe targeting new Hub"},
        # Phase 2 — GHA crons
        {"name": "Check Alerts", "status": "Active", "type": "GHA Cron", "schedule": "*/15 * * * *", "endpoint": "https://electricity-optimizer.onrender.com/api/v1/internal/check-alerts", "workflow_file": ".github/workflows/check-alerts.yml", "phase": "Phase 2", "channels": ["Email"], "notes": "Price threshold alerts with dedup cooldowns (immediate=1h, daily=24h, weekly=7d)"},
        {"name": "Fetch Weather", "status": "Active", "type": "GHA Cron", "schedule": "0 */6 * * *", "endpoint": "https://electricity-optimizer.onrender.com/api/v1/internal/fetch-weather", "workflow_file": ".github/workflows/fetch-weather.yml", "phase": "Phase 2", "channels": [], "notes": "Parallelized with asyncio.gather + Semaphore(10), 51 calls across all states"},
        {"name": "Market Research", "status": "Active", "type": "GHA Cron", "schedule": "0 2 * * *", "endpoint": "https://electricity-optimizer.onrender.com/api/v1/internal/market-research", "workflow_file": ".github/workflows/market-research.yml", "phase": "Phase 2", "channels": [], "notes": "Tavily + Diffbot for energy market intelligence"},
        {"name": "Sync Connections", "status": "Active", "type": "GHA Cron", "schedule": "0 */2 * * *", "endpoint": "https://electricity-optimizer.onrender.com/api/v1/internal/sync-connections", "workflow_file": ".github/workflows/sync-connections.yml", "phase": "Phase 2", "channels": [], "notes": "UtilityAPI auto-sync via sync_all_due()"},
        {"name": "Scrape Rates", "status": "Active", "type": "GHA Cron", "schedule": "0 3 * * *", "endpoint": "https://electricity-optimizer.onrender.com/api/v1/internal/scrape-rates", "workflow_file": ".github/workflows/scrape-rates.yml", "phase": "Phase 2", "channels": [], "notes": "Auto-discovers suppliers when empty body sent (queries DB for websites)"},
        # Phase 3 — GHA crons
        {"name": "Dunning Cycle", "status": "Active", "type": "GHA Cron", "schedule": "0 7 * * *", "endpoint": "https://electricity-optimizer.onrender.com/api/v1/internal/dunning-cycle", "workflow_file": ".github/workflows/dunning-cycle.yml", "phase": "Phase 3", "channels": ["Email"], "notes": "Overdue payment escalation: 24h dedup, soft/final emails (amber/red), downgrade to free after 3 failures"},
        {"name": "KPI Report", "status": "Active", "type": "GHA Cron", "schedule": "0 6 * * *", "endpoint": "https://electricity-optimizer.onrender.com/api/v1/internal/kpi-report", "workflow_file": ".github/workflows/kpi-report.yml", "phase": "Phase 3", "channels": ["Slack #metrics", "Google Sheets"], "notes": "8 metrics: active users, MRR, subscriptions, data freshness. Also via Rube recipe to Google Sheets + Slack"},
        # Rube KPI recipe
        {"name": "Nightly KPI to Sheets + Slack", "status": "Active", "type": "Rube Recipe", "schedule": "5 6 * * *", "recipe_id": "rcp_wu9mVLIZRM_n", "phase": "Phase 3", "channels": ["Slack #metrics", "Google Sheets"], "notes": "Fetches /internal/kpi-report, appends to Google Sheet (15JGyCAThhP2lUKLvuEsdarRXDBa5TjlWKDwD9mztITA), posts to Slack #metrics"},
    ]

    for i, wf in enumerate(workflows):
        props: Dict[str, Any] = {
            "Name": title_prop(wf["name"]),
        }
        if wf.get("status"):
            props["Status"] = {"select": {"name": wf["status"]}}
        if wf.get("type"):
            props["Type"] = {"select": {"name": wf["type"]}}
        if wf.get("schedule"):
            props["Schedule"] = {"rich_text": rich_text(wf["schedule"])}
        if wf.get("endpoint"):
            props["Endpoint"] = {"url": wf["endpoint"]}
        if wf.get("recipe_id"):
            props["Recipe ID"] = {"rich_text": rich_text(wf["recipe_id"])}
        if wf.get("workflow_file"):
            props["Workflow File"] = {"rich_text": rich_text(wf["workflow_file"])}
        if wf.get("phase"):
            props["Phase"] = {"select": {"name": wf["phase"]}}
        if wf.get("channels"):
            props["Channels"] = {"multi_select": [{"name": c} for c in wf["channels"]]}
        if wf.get("notes"):
            props["Notes"] = {"rich_text": rich_text(wf["notes"])}

        api_post(api_key, "pages", {
            "parent": {"database_id": db_id},
            "properties": props,
        })
        print(f"  [{i+1}/{len(workflows)}] {wf['name']}")
        time.sleep(0.35)

    print(f"  Backfilled {len(workflows)} workflow entries")


def backfill_architecture_decisions(api_key: str, db_id: str):
    """Backfill ~15 architecture decision entries."""
    print("Backfilling Architecture Decisions...")

    decisions = [
        {"name": "Neon Auth over JWT for user authentication", "date": "2026-02-23", "category": "Auth", "decision": "Use Neon Auth (Better Auth) with session-based cookies instead of JWT tokens", "rationale": "Session cookies are simpler to manage, no token refresh logic needed. httpOnly cookies prevent XSS token theft. Neon Auth integrates natively with our Neon PostgreSQL", "status": "Active"},
        {"name": "Resend over SendGrid for transactional email", "date": "2026-03-04", "category": "Infrastructure", "decision": "Replace SendGrid with Resend as primary email provider, Gmail SMTP as fallback", "rationale": "Resend has simpler API, better DX, native Next.js SDK. Gmail SMTP provides zero-cost fallback. Dual-provider pattern in send.ts ensures delivery", "status": "Active"},
        {"name": "Same-origin API proxy via Next.js rewrites", "date": "2026-03-04", "category": "Frontend", "decision": "Proxy all /api/v1/* requests through Next.js rewrites to BACKEND_URL instead of direct cross-origin calls", "rationale": "Eliminates cookie issues with session-based auth (cookies not sent cross-origin by default). Fixes URI_TOO_LONG errors. Keeps BACKEND_URL server-side only", "status": "Active"},
        {"name": "GHA Cron over Rube for scheduled API calls", "date": "2026-03-06", "category": "Automation", "decision": "Use GitHub Actions cron workflows for Phase 2/3 automations instead of Rube recipes", "rationale": "GHA provides: free CI/CD minutes, git-tracked workflow files, built-in secrets management, concurrency controls. Rube better for multi-tool orchestration (Phase 1)", "status": "Active"},
        {"name": "asyncio.gather + Semaphore for parallel API calls", "date": "2026-03-06", "category": "Backend", "decision": "Use asyncio.gather with Semaphore(N) for rate-limited parallel HTTP calls", "rationale": "Weather service needs 51 API calls per run. Sequential = 50+ seconds, parallel with Sem(10) = ~6 seconds. Semaphore prevents overwhelming external APIs", "status": "Active"},
        {"name": "UUID primary keys for all tables", "date": "2026-02-06", "category": "Database", "decision": "Use UUID type for all primary keys instead of auto-incrementing integers", "rationale": "UUIDs are globally unique (safe for distributed systems), non-sequential (no enumeration attacks), and compatible with Neon Auth which uses UUIDs", "status": "Active"},
        {"name": "PgBouncer with statement_cache_size=0", "date": "2026-03-05", "category": "Database", "decision": "Set statement_cache_size=0 in asyncpg connect_args when using PgBouncer pooling", "rationale": "PgBouncer in transaction mode doesn't support prepared statements. Without this, asyncpg caches prepared statements that become invalid when connections are reassigned", "status": "Active"},
        {"name": "RequestTimeoutMiddleware with internal exclusions", "date": "2026-03-06", "category": "Backend", "decision": "30-second timeout middleware that excludes /api/v1/internal/ and /prices/stream prefixes", "rationale": "Internal batch jobs (weather, scrape-rates, dunning) can run 60+ seconds. SSE stream needs indefinite connection. Public endpoints still protected from runaway requests", "status": "Active"},
        {"name": "Stripe async via asyncio.to_thread()", "date": "2026-02-23", "category": "Billing", "decision": "Wrap synchronous Stripe SDK calls in asyncio.to_thread() for async FastAPI compatibility", "rationale": "Stripe Python SDK is synchronous. to_thread() runs it in a thread pool without blocking the event loop. Simpler than finding/maintaining an async Stripe wrapper", "status": "Active"},
        {"name": "Alert dedup with cooldown windows", "date": "2026-03-05", "category": "Backend", "decision": "Check alert_history table for recent matching entries within time windows (1h/24h/7d) before sending", "rationale": "Prevents alert fatigue. Different frequencies need different cooldowns. Query-based dedup is simple and reliable. Same pattern reused for dunning email dedup", "status": "Active"},
        {"name": "Ensemble ML predictor over single model", "date": "2026-02-23", "category": "ML", "decision": "Use ensemble of multiple prediction models with HNSW vector similarity weighting", "rationale": "No single model works well across all regions/seasons. Ensemble averages predictions weighted by historical similarity (HNSW). Adaptive learning adjusts weights nightly", "status": "Active"},
        {"name": "Rube recipes for multi-tool orchestration", "date": "2026-03-06", "category": "Automation", "decision": "Use Rube (Composio) recipes for workflows that chain multiple third-party tools (Sentry+Slack, Render+Slack+BetterStack)", "rationale": "Rube handles tool authentication, retry logic, and scheduling. Better than custom code for cross-service orchestration. GHA better for simple API calls", "status": "Active"},
        {"name": "DunningService with 7-day grace period", "date": "2026-03-06", "category": "Billing", "decision": "3-strike dunning: soft email (day 1) -> final warning (day 4-6) -> downgrade to free (day 7+)", "rationale": "Gives users time to update payment info. Soft/final emails use distinct templates (amber/red). 24h dedup prevents spam. Downgrade preserves account but removes paid features", "status": "Active"},
        {"name": "Supplier auto-discovery for rate scraping", "date": "2026-03-06", "category": "Backend", "decision": "When scrape-rates endpoint receives empty body, query DB for all suppliers with websites", "rationale": "Eliminates need to maintain a static supplier list in the cron workflow. New suppliers added via UI are automatically included in nightly scrapes", "status": "Active"},
        {"name": "OneSignal login() for push notification binding", "date": "2026-03-05", "category": "Frontend", "decision": "Call OneSignal login(userId) after authentication to bind device to user, logout() on sign-out", "rationale": "OneSignal v3+ uses login()/logout() instead of deprecated setExternalUserId(). Must call after init(). Enables targeted push notifications per user", "status": "Active"},
    ]

    for i, d in enumerate(decisions):
        props: Dict[str, Any] = {
            "Name": title_prop(d["name"]),
        }
        if d.get("date"):
            props["Date"] = {"date": {"start": d["date"]}}
        if d.get("category"):
            props["Category"] = {"select": {"name": d["category"]}}
        if d.get("decision"):
            props["Decision"] = {"rich_text": rich_text(d["decision"])}
        if d.get("rationale"):
            props["Rationale"] = {"rich_text": rich_text(d["rationale"])}
        if d.get("status"):
            props["Status"] = {"select": {"name": d["status"]}}

        api_post(api_key, "pages", {
            "parent": {"database_id": db_id},
            "properties": props,
        })
        print(f"  [{i+1}/{len(decisions)}] {d['name'][:60]}...")
        time.sleep(0.35)

    print(f"  Backfilled {len(decisions)} architecture decisions")


# ---------------------------------------------------------------------------
# Step 4: Create Dashboard Pages
# ---------------------------------------------------------------------------

def create_dashboard_pages(api_key: str, hub_id: str, db_ids: dict):
    """Create dashboard sub-pages under the Hub."""
    print("Creating dashboard pages...")

    # Page 1: Project Overview
    print("  Creating Project Overview...")
    api_post(api_key, "pages", {
        "parent": {"type": "page_id", "page_id": hub_id},
        "icon": {"type": "emoji", "emoji": "📊"},
        "properties": {"title": [{"type": "text", "text": {"content": "Project Overview"}}]},
        "children": [
            {"object": "block", "type": "heading_2", "heading_2": {"rich_text": rich_text("Tech Stack")}},
            {"object": "block", "type": "bulleted_list_item", "bulleted_list_item": {"rich_text": rich_text("Backend: FastAPI + Python 3.12 on Render")}},
            {"object": "block", "type": "bulleted_list_item", "bulleted_list_item": {"rich_text": rich_text("Frontend: Next.js 14 + TypeScript on Vercel")}},
            {"object": "block", "type": "bulleted_list_item", "bulleted_list_item": {"rich_text": rich_text("Database: Neon PostgreSQL (cold-rice-23455092, us-east-1)")}},
            {"object": "block", "type": "bulleted_list_item", "bulleted_list_item": {"rich_text": rich_text("ML: Ensemble predictor + HNSW vector search")}},
            {"object": "block", "type": "bulleted_list_item", "bulleted_list_item": {"rich_text": rich_text("Auth: Neon Auth (Better Auth) — session cookies")}},
            {"object": "block", "type": "bulleted_list_item", "bulleted_list_item": {"rich_text": rich_text("Payments: Stripe (Free/$4.99 Pro/$14.99 Business)")}},
            {"object": "block", "type": "bulleted_list_item", "bulleted_list_item": {"rich_text": rich_text("Email: Resend (primary) + Gmail SMTP (fallback)")}},
            {"object": "block", "type": "bulleted_list_item", "bulleted_list_item": {"rich_text": rich_text("Push: OneSignal")}},
            {"object": "block", "type": "divider", "divider": {}},
            {"object": "block", "type": "heading_2", "heading_2": {"rich_text": rich_text("Quick Stats")}},
            {"object": "block", "type": "bulleted_list_item", "bulleted_list_item": {"rich_text": rich_text("3,445 total tests (Backend: 1,443 | Frontend: 1,391 | ML: 611 | E2E: 634)")}},
            {"object": "block", "type": "bulleted_list_item", "bulleted_list_item": {"rich_text": rich_text("24 database migrations deployed")}},
            {"object": "block", "type": "bulleted_list_item", "bulleted_list_item": {"rich_text": rich_text("30 public + neon_auth tables")}},
            {"object": "block", "type": "bulleted_list_item", "bulleted_list_item": {"rich_text": rich_text("7 automation workflows active")}},
            {"object": "block", "type": "bulleted_list_item", "bulleted_list_item": {"rich_text": rich_text("16 Composio/Rube integrations")}},
            {"object": "block", "type": "divider", "divider": {}},
            {"object": "block", "type": "heading_2", "heading_2": {"rich_text": rich_text("Production URLs")}},
            {"object": "block", "type": "bulleted_list_item", "bulleted_list_item": {"rich_text": [{"type": "text", "text": {"content": "Frontend: ", "link": None}}, {"type": "text", "text": {"content": "electricity-optimizer.vercel.app", "link": {"url": "https://electricity-optimizer.vercel.app"}}}]}},
            {"object": "block", "type": "bulleted_list_item", "bulleted_list_item": {"rich_text": [{"type": "text", "text": {"content": "Backend API: ", "link": None}}, {"type": "text", "text": {"content": "electricity-optimizer.onrender.com", "link": {"url": "https://electricity-optimizer.onrender.com"}}}]}},
            {"object": "block", "type": "bulleted_list_item", "bulleted_list_item": {"rich_text": [{"type": "text", "text": {"content": "GitHub: ", "link": None}}, {"type": "text", "text": {"content": "JoeyJoziah/electricity-optimizer", "link": {"url": "https://github.com/JoeyJoziah/electricity-optimizer"}}}]}},
            {"object": "block", "type": "bulleted_list_item", "bulleted_list_item": {"rich_text": [{"type": "text", "text": {"content": "Neon: ", "link": None}}, {"type": "text", "text": {"content": "cold-rice-23455092", "link": {"url": "https://console.neon.tech/app/projects/cold-rice-23455092"}}}]}},
        ]
    })
    time.sleep(0.5)

    # Page 2: Development Timeline
    print("  Creating Development Timeline...")
    api_post(api_key, "pages", {
        "parent": {"type": "page_id", "page_id": hub_id},
        "icon": {"type": "emoji", "emoji": "📅"},
        "properties": {"title": [{"type": "text", "text": {"content": "Development Timeline"}}]},
        "children": [
            {"object": "block", "type": "callout", "callout": {"rich_text": rich_text("Project started 2026-02-06 with MVP launch. Rapid iteration through multi-utility expansion, nationwide coverage, and full automation stack."), "icon": {"type": "emoji", "emoji": "🚀"}}},
            {"object": "block", "type": "divider", "divider": {}},
            {"object": "block", "type": "heading_3", "heading_3": {"rich_text": rich_text("Feb 6 — MVP Launch")}},
            {"object": "block", "type": "paragraph", "paragraph": {"rich_text": rich_text("Core pricing engine, supplier search, optimization recommendations. FastAPI backend + Next.js frontend + Neon PostgreSQL.")}},
            {"object": "block", "type": "heading_3", "heading_3": {"rich_text": rich_text("Feb 23 — Multi-Utility + Neon Auth")}},
            {"object": "block", "type": "paragraph", "paragraph": {"rich_text": rich_text("Expanded to 50 states + DC. Migrated from JWT to Neon Auth (Better Auth) with session cookies. Added ML ensemble predictor with HNSW vector search.")}},
            {"object": "block", "type": "heading_3", "heading_3": {"rich_text": rich_text("Feb 25 — Connection Feature (5 Phases)")}},
            {"object": "block", "type": "paragraph", "paragraph": {"rich_text": rich_text("Full utility connection pipeline: bill OCR upload, email OAuth, UtilityAPI sync, analytics dashboard.")}},
            {"object": "block", "type": "heading_3", "heading_3": {"rich_text": rich_text("Feb 26 — Nationwide Expansion")}},
            {"object": "block", "type": "paragraph", "paragraph": {"rich_text": rich_text("Stream-chain data pipelines for all 50 states. Gap remediation for missing coverage areas.")}},
            {"object": "block", "type": "heading_3", "heading_3": {"rich_text": rich_text("Mar 2 — Swarm Audit")}},
            {"object": "block", "type": "paragraph", "paragraph": {"rich_text": rich_text("Multi-agent swarm audit: 6 batches, 107 files reviewed for code quality, security, and patterns.")}},
            {"object": "block", "type": "heading_3", "heading_3": {"rich_text": rich_text("Mar 3 — UI/UX Overhaul")}},
            {"object": "block", "type": "paragraph", "paragraph": {"rich_text": rich_text("Design system with tokens, shared Input component, CSS variables. 51 accessibility tests (jest-axe) across 19 pages.")}},
            {"object": "block", "type": "heading_3", "heading_3": {"rich_text": rich_text("Mar 4 — Auth Fix + Integrations")}},
            {"object": "block", "type": "paragraph", "paragraph": {"rich_text": rich_text("SendGrid-to-Resend migration, magic link fix, OAuth conditional buttons, same-origin proxy. Agentic-Flow integration (34 agents). Multi-repo skill integration (2,492 entities from 15 repos).")}},
            {"object": "block", "type": "heading_3", "heading_3": {"rich_text": rich_text("Mar 5 — DB Audit + Automation Planning")}},
            {"object": "block", "type": "paragraph", "paragraph": {"rich_text": rich_text("Migration 023, bulk_create optimization, PgBouncer tuning. 16 Composio integrations. Automation plan created (9 workflows, 7 approved). Phase 0 prereqs resolved.")}},
            {"object": "block", "type": "heading_3", "heading_3": {"rich_text": rich_text("Mar 6 — Full Automation Stack")}},
            {"object": "block", "type": "paragraph", "paragraph": {"rich_text": rich_text("Phase 1: 3 Rube recipes (Sentry, Deploy, Notion sync). Phase 2: 5 GHA cron workflows. Phase 3: Stripe dunning + KPI report. 7/7 workflows complete. Notion Hub rebuild.")}},
        ]
    })
    time.sleep(0.5)

    # Page 3: Automation Dashboard (text-based, since inline linked DBs need more complex API calls)
    print("  Creating Automation Dashboard...")
    api_post(api_key, "pages", {
        "parent": {"type": "page_id", "page_id": hub_id},
        "icon": {"type": "emoji", "emoji": "⚙️"},
        "properties": {"title": [{"type": "text", "text": {"content": "Automation Dashboard"}}]},
        "children": [
            {"object": "block", "type": "callout", "callout": {"rich_text": rich_text("All 7 approved automation workflows are ACTIVE. View the Automation Workflows database for full details."), "icon": {"type": "emoji", "emoji": "✅"}}},
            {"object": "block", "type": "divider", "divider": {}},
            {"object": "block", "type": "heading_2", "heading_2": {"rich_text": rich_text("Phase 1 — Rube Recipes (Zero-Risk)")}},
            {"object": "block", "type": "bulleted_list_item", "bulleted_list_item": {"rich_text": rich_text("Sentry-to-Slack (every 15min) — rcp_sQ1NKouFdXIe → #incidents")}},
            {"object": "block", "type": "bulleted_list_item", "bulleted_list_item": {"rich_text": rich_text("Deploy Notifications (hourly) — rcp_9f8mVE2Z_DSP → #deployments")}},
            {"object": "block", "type": "bulleted_list_item", "bulleted_list_item": {"rich_text": rich_text("GitHub-to-Notion Sync (every 6h) — rcp_73Kc9K65YC5T")}},
            {"object": "block", "type": "divider", "divider": {}},
            {"object": "block", "type": "heading_2", "heading_2": {"rich_text": rich_text("Phase 2 — GHA Cron Workflows")}},
            {"object": "block", "type": "bulleted_list_item", "bulleted_list_item": {"rich_text": rich_text("check-alerts (*/15min) — Price threshold alerts with dedup")}},
            {"object": "block", "type": "bulleted_list_item", "bulleted_list_item": {"rich_text": rich_text("fetch-weather (*/6h) — 51 parallel OpenWeather calls")}},
            {"object": "block", "type": "bulleted_list_item", "bulleted_list_item": {"rich_text": rich_text("market-research (daily 2am) — Tavily + Diffbot")}},
            {"object": "block", "type": "bulleted_list_item", "bulleted_list_item": {"rich_text": rich_text("sync-connections (*/2h) — UtilityAPI auto-sync")}},
            {"object": "block", "type": "bulleted_list_item", "bulleted_list_item": {"rich_text": rich_text("scrape-rates (daily 3am) — Auto-discover suppliers")}},
            {"object": "block", "type": "divider", "divider": {}},
            {"object": "block", "type": "heading_2", "heading_2": {"rich_text": rich_text("Phase 3 — Business Automation")}},
            {"object": "block", "type": "bulleted_list_item", "bulleted_list_item": {"rich_text": rich_text("dunning-cycle (daily 7am) — Stripe payment failure escalation")}},
            {"object": "block", "type": "bulleted_list_item", "bulleted_list_item": {"rich_text": rich_text("kpi-report (daily 6am) — Business metrics → Slack #metrics + Google Sheets")}},
            {"object": "block", "type": "divider", "divider": {}},
            {"object": "block", "type": "heading_2", "heading_2": {"rich_text": rich_text("Slack Channels")}},
            {"object": "block", "type": "bulleted_list_item", "bulleted_list_item": {"rich_text": rich_text("#incidents (C0AKV2TK257) — Sentry alerts")}},
            {"object": "block", "type": "bulleted_list_item", "bulleted_list_item": {"rich_text": rich_text("#deployments (C0AKCN6T02Z) — Deploy status")}},
            {"object": "block", "type": "bulleted_list_item", "bulleted_list_item": {"rich_text": rich_text("#metrics (C0AKDD7P2HX) — KPI reports")}},
        ]
    })

    print("  Dashboard pages created")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    api_key = get_api_key()
    print(f"Notion API key loaded ({len(api_key)} chars)")

    # Step 2: Create Hub + Databases
    # Check if hub was already created (from a previous partial run)
    if OUTPUT_FILE.exists():
        with open(OUTPUT_FILE) as f:
            existing = json.load(f)
        if existing.get("hub_page_id"):
            hub_id = existing["hub_page_id"]
            print(f"Reusing existing Hub page: {hub_id}")
        else:
            hub_id = create_hub_page(api_key)
    else:
        hub_id = create_hub_page(api_key)
    time.sleep(1)

    tracker_id = create_project_tracker(api_key, hub_id)
    time.sleep(0.5)
    automation_id = create_automation_workflows(api_key, hub_id)
    time.sleep(0.5)
    decisions_id = create_architecture_decisions(api_key, hub_id)
    time.sleep(0.5)

    db_ids = {
        "hub_page_id": hub_id,
        "project_tracker_id": tracker_id,
        "automation_workflows_id": automation_id,
        "architecture_decisions_id": decisions_id,
    }

    # Save IDs for config update
    with open(OUTPUT_FILE, "w") as f:
        json.dump(db_ids, f, indent=2)
    print(f"\nDatabase IDs saved to {OUTPUT_FILE}")

    # Step 3: Backfill data
    backfill_project_tracker(api_key, tracker_id)
    backfill_automation_workflows(api_key, automation_id)
    backfill_architecture_decisions(api_key, decisions_id)

    # Step 4: Dashboard pages
    create_dashboard_pages(api_key, hub_id, db_ids)

    print(f"\n{'='*60}")
    print("Notion Hub setup complete!")
    print(f"  Hub page:     {hub_id}")
    print(f"  Tracker DB:   {tracker_id}")
    print(f"  Automation DB: {automation_id}")
    print(f"  Decisions DB: {decisions_id}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
