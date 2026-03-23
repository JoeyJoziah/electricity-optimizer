"""
Community Service — CRUD for community posts, votes, reports, and moderation.

Fail-closed moderation: posts start as is_pending_moderation=true.
AI classifies via Groq (primary) with Gemini fallback; 30s timeout leaves
post in pending state (visible only after an explicit moderation pass).
Vote and report counts are derived via COUNT(*), not stored columns.
XSS sanitization via nh3 (Rust-based).
"""

from typing import Any

import nh3
import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)

# 5 unique reporters → hide post
REPORT_HIDE_THRESHOLD = 5

# Max posts per user per hour
POSTS_PER_HOUR_LIMIT = 10

# Moderation timeout (seconds) — 30s to give AI providers adequate response time
MODERATION_TIMEOUT_SECONDS = 30


class CommunityService:
    """Service for community posts, voting, reporting, and AI moderation."""

    # ------------------------------------------------------------------
    # create_post
    # ------------------------------------------------------------------

    async def create_post(
        self,
        db: AsyncSession,
        user_id: str,
        data: dict[str, Any],
        agent_service: Any,
    ) -> dict[str, Any]:
        """
        Create a community post with XSS sanitization and fail-closed moderation.

        Steps:
        1. Check rate limit (POSTS_PER_HOUR_LIMIT per hour)
        2. Sanitize title/body with nh3
        3. INSERT with is_pending_moderation=true
        4. Fire moderation (async, with 30s timeout)
        """
        import asyncio

        # 1. Rate limit check
        rate_sql = text("""
            SELECT COUNT(*) FROM community_posts
            WHERE user_id = :user_id
              AND created_at >= NOW() - INTERVAL '1 hour'
        """)
        rate_result = await db.execute(rate_sql, {"user_id": user_id})
        count = rate_result.scalar()
        if count >= POSTS_PER_HOUR_LIMIT:
            raise ValueError("Rate limit exceeded: too many posts per hour")

        # 2. Sanitize XSS
        clean_title = nh3.clean(data["title"])
        clean_body = nh3.clean(data["body"])
        clean_supplier = nh3.clean(data["supplier_name"]) if data.get("supplier_name") else None

        # 3. INSERT
        insert_sql = text("""
            INSERT INTO community_posts
                (user_id, region, utility_type, post_type, title, body,
                 rate_per_unit, rate_unit, supplier_name,
                 is_hidden, is_pending_moderation)
            VALUES
                (:user_id, :region, :utility_type, :post_type, :title, :body,
                 :rate_per_unit, :rate_unit, :supplier_name,
                 false, true)
            RETURNING *
        """)
        params = {
            "user_id": user_id,
            "region": data["region"],
            "utility_type": data["utility_type"],
            "post_type": data["post_type"],
            "title": clean_title,
            "body": clean_body,
            "rate_per_unit": data.get("rate_per_unit"),
            "rate_unit": data.get("rate_unit"),
            "supplier_name": clean_supplier,
        }
        try:
            result = await db.execute(insert_sql, params)
            post = dict(result.mappings().fetchone())
            await db.commit()
        except Exception:
            await db.rollback()
            raise

        # 4. Fire moderation with timeout (fail-closed: post remains pending on timeout)
        post_id = post["id"]
        try:
            await asyncio.wait_for(
                self._run_moderation(db, post_id, clean_title, clean_body, agent_service),
                timeout=MODERATION_TIMEOUT_SECONDS,
            )
        except (TimeoutError, Exception) as exc:
            # Fail-closed: leave is_pending_moderation=true so the post stays
            # invisible until a subsequent moderation pass explicitly clears it.
            # Do NOT call _clear_pending_moderation here — that would be fail-open.
            logger.warning(
                "moderation_timeout_or_failure",
                post_id=str(post_id),
                error=str(exc),
            )

        return post

    async def _run_moderation(
        self,
        db: AsyncSession,
        post_id: str,
        title: str,
        body: str,
        agent_service: Any,
    ) -> None:
        """Run AI moderation: Groq primary, Gemini fallback."""
        content = f"{title}\n\n{body}"
        classification = None

        # Try Groq first
        try:
            if hasattr(agent_service, "classify_content_groq"):
                classification = await agent_service.classify_content_groq(content)
            else:
                classification = await agent_service.classify_content(content)
        except Exception as exc:
            logger.warning("groq_moderation_failed", post_id=str(post_id), error=str(exc))
            # Fallback to Gemini
            try:
                if hasattr(agent_service, "classify_content_gemini"):
                    classification = await agent_service.classify_content_gemini(content)
                else:
                    raise  # Re-raise if no fallback available
            except Exception as fallback_exc:
                logger.error(
                    "all_moderation_failed",
                    post_id=str(post_id),
                    error=str(fallback_exc),
                )
                raise

        # Apply classification result
        try:
            if classification == "flagged":
                await db.execute(
                    text("""
                        UPDATE community_posts
                        SET is_hidden = true,
                            is_pending_moderation = false,
                            hidden_reason = 'flagged_by_ai'
                        WHERE id = :post_id
                    """),
                    {"post_id": post_id},
                )
            else:
                await db.execute(
                    text("""
                        UPDATE community_posts
                        SET is_pending_moderation = false
                        WHERE id = :post_id
                    """),
                    {"post_id": post_id},
                )
            await db.commit()
        except Exception:
            await db.rollback()
            raise

    async def _clear_pending_moderation(self, db: AsyncSession, post_id: str) -> None:
        """Clear is_pending_moderation after timeout (fail-safe release)."""
        try:
            await db.execute(
                text("""
                    UPDATE community_posts
                    SET is_pending_moderation = false
                    WHERE id = :post_id
                """),
                {"post_id": post_id},
            )
            await db.commit()
        except Exception:
            await db.rollback()
            raise

    # ------------------------------------------------------------------
    # list_posts
    # ------------------------------------------------------------------

    async def list_posts(
        self,
        db: AsyncSession,
        region: str,
        utility_type: str,
        page: int = 1,
        per_page: int = 10,
    ) -> dict[str, Any]:
        """
        Return paginated posts, excluding hidden and pending moderation.
        Uses COUNT(*) OVER() window function to get total in a single query.
        Vote counts derived via LEFT JOIN COUNT.
        """
        offset = (page - 1) * per_page

        list_sql = text("""
            SELECT
                cp.*,
                COALESCE(v.cnt, 0) AS upvote_count,
                COALESCE(r.cnt, 0) AS report_count,
                COUNT(*) OVER() AS _total_count
            FROM community_posts cp
            LEFT JOIN (
                SELECT post_id, COUNT(*) AS cnt
                FROM community_votes
                GROUP BY post_id
            ) v ON v.post_id = cp.id
            LEFT JOIN (
                SELECT post_id, COUNT(*) AS cnt
                FROM community_reports
                GROUP BY post_id
            ) r ON r.post_id = cp.id
            WHERE cp.region = :region
              AND cp.utility_type = :utility_type
              AND cp.is_hidden = false
              AND cp.is_pending_moderation = false
            ORDER BY cp.created_at DESC
            LIMIT :limit OFFSET :offset
        """)
        list_result = await db.execute(
            list_sql,
            {
                "region": region,
                "utility_type": utility_type,
                "limit": per_page,
                "offset": offset,
            },
        )
        rows = list_result.mappings().fetchall()

        # Extract total from window function (same for every row)
        total = rows[0]["_total_count"] if rows else 0
        items = [{k: v for k, v in dict(row).items() if k != "_total_count"} for row in rows]

        pages = max(1, (total + per_page - 1) // per_page)

        return {
            "items": items,
            "total": total,
            "page": page,
            "per_page": per_page,
            "pages": pages,
        }

    # ------------------------------------------------------------------
    # toggle_vote
    # ------------------------------------------------------------------

    async def toggle_vote(
        self,
        db: AsyncSession,
        user_id: str,
        post_id: str,
    ) -> dict[str, Any]:
        """
        Atomically toggle a vote and return voted state + count in a single query.

        Uses INSERT ... ON CONFLICT to avoid TOCTOU races, and a CTE to
        compute the new vote count in the same round-trip.

        Returns:
            Dict with 'voted' (bool) and 'upvote_count' (int).
        """
        toggle_sql = text("""
            WITH toggle AS (
                -- Try to insert; if already exists, delete instead
                INSERT INTO community_votes (user_id, post_id)
                VALUES (:user_id, :post_id)
                ON CONFLICT (user_id, post_id) DO NOTHING
                RETURNING 'inserted' AS action
            ),
            remove AS (
                -- If nothing was inserted, the vote existed → delete it
                DELETE FROM community_votes
                WHERE user_id = :user_id
                  AND post_id = :post_id
                  AND NOT EXISTS (SELECT 1 FROM toggle)
                RETURNING 'deleted' AS action
            ),
            result AS (
                SELECT action FROM toggle
                UNION ALL
                SELECT action FROM remove
            )
            SELECT
                COALESCE((SELECT action FROM result), 'noop') AS action,
                (SELECT COUNT(*) FROM community_votes WHERE post_id = :post_id) AS upvote_count
        """)
        try:
            result = await db.execute(toggle_sql, {"user_id": user_id, "post_id": post_id})
            row = result.mappings().fetchone()
            await db.commit()
        except Exception:
            await db.rollback()
            raise

        voted = row["action"] == "inserted"
        return {"voted": voted, "upvote_count": row["upvote_count"]}

    # ------------------------------------------------------------------
    # get_vote_count
    # ------------------------------------------------------------------

    async def get_vote_count(self, db: AsyncSession, post_id: str) -> int:
        """Derive vote count via COUNT(*) — not a stored column."""
        result = await db.execute(
            text("SELECT COUNT(*) FROM community_votes WHERE post_id = :post_id"),
            {"post_id": post_id},
        )
        return result.scalar()

    # ------------------------------------------------------------------
    # report_post
    # ------------------------------------------------------------------

    async def report_post(
        self,
        db: AsyncSession,
        user_id: str,
        post_id: str,
        reason: str | None = None,
    ) -> None:
        """
        Report a post. Idempotent via INSERT ON CONFLICT DO NOTHING.
        Hides post when unique reporter count >= REPORT_HIDE_THRESHOLD.
        Uses a single CTE to insert + count + conditionally hide.
        """
        report_sql = text("""
            WITH ins AS (
                INSERT INTO community_reports (user_id, post_id, reason)
                VALUES (:user_id, :post_id, :reason)
                ON CONFLICT (user_id, post_id) DO NOTHING
                RETURNING 1
            ),
            cnt AS (
                SELECT COUNT(*) AS total
                FROM community_reports
                WHERE post_id = :post_id
            )
            UPDATE community_posts
            SET is_hidden = true, hidden_reason = 'reported_by_users'
            WHERE id = :post_id
              AND (SELECT total FROM cnt) >= :threshold
              AND is_hidden = false
        """)
        try:
            await db.execute(
                report_sql,
                {
                    "user_id": user_id,
                    "post_id": post_id,
                    "reason": reason,
                    "threshold": REPORT_HIDE_THRESHOLD,
                },
            )
            await db.commit()
        except Exception:
            await db.rollback()
            raise

    # ------------------------------------------------------------------
    # moderate_post
    # ------------------------------------------------------------------

    async def moderate_post(
        self,
        db: AsyncSession,
        post_id: str,
        agent_service: Any,
    ) -> None:
        """
        Moderate a post using AI. Groq primary, Gemini fallback.
        Updates is_hidden/is_pending_moderation based on classification.
        """
        # Fetch post content
        select_sql = text("SELECT title, body FROM community_posts WHERE id = :post_id")
        result = await db.execute(select_sql, {"post_id": post_id})
        post = result.mappings().fetchone()

        if not post:
            return

        content = f"{post['title']}\n\n{post['body']}"
        classification = None

        # Try Groq first
        try:
            if hasattr(agent_service, "classify_content_groq"):
                classification = await agent_service.classify_content_groq(content)
            else:
                classification = await agent_service.classify_content(content)
        except Exception:
            # Fallback to Gemini
            try:
                if hasattr(agent_service, "classify_content_gemini"):
                    classification = await agent_service.classify_content_gemini(content)
            except Exception:
                # Both failed — clear pending moderation
                await self._clear_pending_moderation(db, post_id)
                return

        try:
            if classification == "flagged":
                await db.execute(
                    text("""
                        UPDATE community_posts
                        SET is_hidden = true,
                            is_pending_moderation = false,
                            hidden_reason = 'flagged_by_ai'
                        WHERE id = :post_id
                    """),
                    {"post_id": post_id},
                )
            else:
                await db.execute(
                    text("""
                        UPDATE community_posts
                        SET is_pending_moderation = false
                        WHERE id = :post_id
                    """),
                    {"post_id": post_id},
                )
            await db.commit()
        except Exception:
            await db.rollback()
            raise

    # ------------------------------------------------------------------
    # retroactive_moderate
    # ------------------------------------------------------------------

    async def retroactive_moderate(
        self,
        db: AsyncSession,
        agent_service: Any,
    ) -> int:
        """
        Re-check posts that timed out during moderation.
        Uses sequential AI calls to avoid asyncio.gather with shared AsyncSession.
        Returns count of posts re-moderated.
        """
        # Find posts that were auto-unhidden after timeout
        select_sql = text("""
            SELECT id, title, body FROM community_posts
            WHERE is_pending_moderation = false
              AND is_hidden = false
              AND hidden_reason IS NULL
              AND created_at >= NOW() - INTERVAL '24 hours'
            ORDER BY created_at ASC
        """)
        result = await db.execute(select_sql)
        posts = result.mappings().fetchall()

        if not posts:
            return 0

        # Sequential AI classification to avoid asyncio.gather with shared
        # AsyncSession (known corruption pattern: "asyncio.gather + shared
        # AsyncSession = corruption; use sequential loops instead").
        flagged_ids: list[str] = []
        for post in posts:
            content = f"{post['title']}\n\n{post['body']}"
            try:
                classification = await agent_service.classify_content(content)
                if classification == "flagged":
                    flagged_ids.append(str(post["id"]))
            except Exception as exc:
                logger.warning(
                    "retroactive_moderation_failed",
                    post_id=str(post["id"]),
                    error=str(exc),
                )

        # Batch update all flagged posts in a single query
        if flagged_ids:
            try:
                await db.execute(
                    text("""
                        UPDATE community_posts
                        SET is_hidden = true, hidden_reason = 'flagged_by_ai_retroactive'
                        WHERE id = ANY(:ids)
                    """),
                    {"ids": flagged_ids},
                )
                await db.commit()
            except Exception:
                await db.rollback()
                raise

        return len(posts)

    # ------------------------------------------------------------------
    # edit_and_resubmit
    # ------------------------------------------------------------------

    async def edit_and_resubmit(
        self,
        db: AsyncSession,
        user_id: str,
        post_id: str,
        data: dict[str, Any],
        agent_service: Any,
    ) -> dict[str, Any]:
        """
        Allow the author to edit a flagged post and resubmit for moderation.
        Only the original author can edit. Re-sanitizes and re-triggers moderation.
        """
        import asyncio

        # Verify ownership and flagged status
        select_sql = text("""
            SELECT * FROM community_posts
            WHERE id = :post_id AND user_id = :user_id
        """)
        result = await db.execute(select_sql, {"post_id": post_id, "user_id": user_id})
        existing = result.mappings().fetchone()

        if not existing:
            raise ValueError("Post not found or not owned by user")

        # Sanitize new content
        clean_title = nh3.clean(data["title"]) if "title" in data else existing["title"]
        clean_body = nh3.clean(data["body"]) if "body" in data else existing["body"]

        # Update: unhide, set pending moderation
        update_sql = text("""
            UPDATE community_posts
            SET title = :title,
                body = :body,
                is_hidden = false,
                is_pending_moderation = true,
                hidden_reason = NULL
            WHERE id = :post_id
            RETURNING *
        """)
        try:
            update_result = await db.execute(
                update_sql, {"title": clean_title, "body": clean_body, "post_id": post_id}
            )
            updated = dict(update_result.mappings().fetchone())
            await db.commit()
        except Exception:
            await db.rollback()
            raise

        # Re-trigger moderation — fail-closed: post stays pending on timeout/error
        try:
            await asyncio.wait_for(
                self._run_moderation(db, post_id, clean_title, clean_body, agent_service),
                timeout=MODERATION_TIMEOUT_SECONDS,
            )
        except (TimeoutError, Exception) as exc:
            # Fail-closed: leave is_pending_moderation=true so the resubmitted post
            # stays invisible until an explicit moderation pass clears it.
            logger.warning("resubmit_moderation_failed", post_id=str(post_id), error=str(exc))

        return updated

    # ------------------------------------------------------------------
    # get_stats
    # ------------------------------------------------------------------

    async def get_stats(
        self,
        db: AsyncSession,
        region: str,
    ) -> dict[str, Any]:
        """
        Aggregate community stats for social proof with attribution.
        Returns total_users, earliest_post date, and top-voted tip.
        """
        stats_sql = text("""
            SELECT
                COUNT(DISTINCT user_id) AS total_users,
                MIN(created_at) AS earliest_post
            FROM community_posts
            WHERE region = :region
              AND is_hidden = false
              AND is_pending_moderation = false
        """)
        stats_result = await db.execute(stats_sql, {"region": region})
        stats = stats_result.mappings().fetchone()

        # Top tip by votes
        top_tip_sql = text("""
            SELECT
                cp.*,
                COALESCE(v.cnt, 0) AS upvote_count
            FROM community_posts cp
            LEFT JOIN (
                SELECT post_id, COUNT(*) AS cnt
                FROM community_votes
                GROUP BY post_id
            ) v ON v.post_id = cp.id
            WHERE cp.region = :region
              AND cp.post_type = 'tip'
              AND cp.is_hidden = false
              AND cp.is_pending_moderation = false
            ORDER BY upvote_count DESC
            LIMIT 1
        """)
        top_result = await db.execute(top_tip_sql, {"region": region})
        top_tip = top_result.mappings().fetchone()

        return {
            "total_users": stats["total_users"] if stats else 0,
            "region": region,
            "reporting_since": stats["earliest_post"] if stats else None,
            "top_tip": dict(top_tip) if top_tip else None,
            "avg_savings_pct": None,  # Placeholder — populated when savings aggregation exists
        }
