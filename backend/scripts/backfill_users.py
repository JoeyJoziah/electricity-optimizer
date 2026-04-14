#!/usr/bin/env python3
"""
One-time backfill: sync neon_auth.user → public.users

Inserts a public.users row for every account in neon_auth.user that
does not already have a corresponding row.  Existing rows are updated
if email or name differs (e.g. user changed display name in provider).

Usage
-----
    # Dry-run (no writes) — see what would change
    .venv/bin/python scripts/backfill_users.py --dry-run

    # Live run
    .venv/bin/python scripts/backfill_users.py

    # Verbose live run
    .venv/bin/python scripts/backfill_users.py --verbose

Environment
-----------
    DATABASE_URL — Neon connection string (reads from .env automatically
                   if python-dotenv is available)

The script is intentionally standalone (no FastAPI process required).
It uses the same asyncpg driver that SQLAlchemy uses in production.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from typing import NamedTuple

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass  # python-dotenv not installed — that is fine in production

try:
    import asyncpg
except ImportError:
    print("ERROR: asyncpg is not installed.  Run: .venv/bin/pip install asyncpg")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


class NeonUser(NamedTuple):
    id: str
    email: str
    name: str


class SyncResult(NamedTuple):
    user_id: str
    email: str
    action: str  # "created" | "updated" | "skipped" | "error"
    detail: str = ""


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------


async def fetch_neon_users(conn: asyncpg.Connection) -> list[NeonUser]:
    """Return all users from neon_auth.user ordered by creation date."""
    rows = await conn.fetch("""
        SELECT
            id::text          AS id,
            email             AS email,
            COALESCE(name, '') AS name
        FROM neon_auth."user"
        ORDER BY "createdAt"
        """)
    return [NeonUser(id=r["id"], email=r["email"], name=r["name"]) for r in rows]


async def sync_user(
    conn: asyncpg.Connection,
    user: NeonUser,
    *,
    dry_run: bool,
) -> SyncResult:
    """
    Upsert one user from neon_auth into public.users.

    Returns a SyncResult describing what happened.
    """
    # Check current state
    existing = await conn.fetchrow(
        "SELECT id, email, name FROM public.users WHERE id = $1",
        user.id,
    )

    if existing is None:
        action = "created"
        if not dry_run:
            await conn.execute(
                """
                INSERT INTO public.users
                    (id, email, name, region, is_active, created_at, updated_at)
                VALUES
                    ($1, $2, $3, NULL, true, NOW(), NOW())
                ON CONFLICT (id) DO NOTHING
                """,
                user.id,
                user.email.lower(),
                user.name,
            )
        return SyncResult(user_id=user.id, email=user.email, action=action)

    # Determine whether an update is needed
    needs_email_update = existing["email"] != user.email.lower()
    needs_name_update = user.name != "" and existing["name"] != user.name

    if not needs_email_update and not needs_name_update:
        return SyncResult(user_id=user.id, email=user.email, action="skipped")

    action = "updated"
    if not dry_run:
        set_parts = []
        params: list = [user.id]  # $1 = id

        if needs_email_update:
            params.append(user.email.lower())
            set_parts.append(f"email = ${len(params)}")

        if needs_name_update:
            params.append(user.name)
            set_parts.append(f"name = ${len(params)}")

        params.append("NOW()")
        # updated_at uses NOW() directly — no param needed
        set_clause = ", ".join(set_parts) + ", updated_at = NOW()"
        await conn.execute(
            f"UPDATE public.users SET {set_clause} WHERE id = $1",
            *params[:-1],  # exclude the "NOW()" placeholder we added for clarity
        )

    detail_parts = []
    if needs_email_update:
        detail_parts.append(f"email: {existing['email']} → {user.email.lower()}")
    if needs_name_update:
        detail_parts.append(f"name: {existing['name']!r} → {user.name!r}")

    return SyncResult(
        user_id=user.id,
        email=user.email,
        action=action,
        detail=", ".join(detail_parts),
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def run(*, dry_run: bool, verbose: bool) -> None:
    database_url = os.environ.get("DATABASE_URL", "")
    if not database_url:
        print("ERROR: DATABASE_URL environment variable is not set.")
        sys.exit(1)

    # asyncpg requires postgresql:// scheme (not postgresql+asyncpg://)
    dsn = database_url.replace("postgresql+asyncpg://", "postgresql://")
    # Strip SQLAlchemy options not understood by asyncpg
    if "?options=" in dsn:
        dsn = dsn.split("?options=")[0]

    if dry_run:
        print("DRY-RUN MODE — no changes will be written to the database.\n")

    print("Connecting to database…")
    conn = await asyncpg.connect(dsn)

    try:
        neon_users = await fetch_neon_users(conn)
        print(f"Found {len(neon_users)} user(s) in neon_auth.user.\n")

        results: list[SyncResult] = []
        for user in neon_users:
            try:
                result = await sync_user(conn, user, dry_run=dry_run)
            except Exception as exc:
                result = SyncResult(
                    user_id=user.id,
                    email=user.email,
                    action="error",
                    detail=str(exc),
                )
            results.append(result)

            if verbose or result.action != "skipped":
                tag = {
                    "created": "[CREATE]",
                    "updated": "[UPDATE]",
                    "skipped": "[skip  ]",
                    "error": "[ERROR ]",
                }[result.action]
                line = f"  {tag} {result.email} ({result.user_id[:8]}…)"
                if result.detail:
                    line += f"  →  {result.detail}"
                print(line)

    finally:
        await conn.close()

    # Summary
    counts = {"created": 0, "updated": 0, "skipped": 0, "error": 0}
    for r in results:
        counts[r.action] = counts.get(r.action, 0) + 1

    print()
    print("=" * 60)
    print(f"  Total neon_auth users : {len(results)}")
    print(f"  Created               : {counts['created']}")
    print(f"  Updated               : {counts['updated']}")
    print(f"  Already in sync       : {counts['skipped']}")
    print(f"  Errors                : {counts['error']}")
    if dry_run:
        print()
        print("  (DRY-RUN — nothing was written)")
    print("=" * 60)

    if counts["error"] > 0:
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill public.users from neon_auth.user")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would change without writing to the database",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print a line for every user, including already-synced ones",
    )
    args = parser.parse_args()

    asyncio.run(run(dry_run=args.dry_run, verbose=args.verbose))


if __name__ == "__main__":
    main()
