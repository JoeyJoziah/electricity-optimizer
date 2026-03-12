"""
Community Service — CRUD for community posts, votes, reports, and moderation.

Fail-closed moderation: posts start as is_pending_moderation=true.
AI classifies via Groq (primary) with Gemini fallback; 30s timeout auto-clears.
Vote and report counts are derived via COUNT(*), not stored columns.
XSS sanitization via nh3 (Rust-based).
"""

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import nh3
import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)

# 5 unique reporters → hide post
REPORT_HIDE_THRESHOLD = 5

# Max posts per user per hour
POSTS_PER_HOUR_LIMIT = 10

# Moderation timeout (seconds)
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
        data: Dict[str, Any],
        agent_service: Any,
    ) -> Dict[str, Any]:
        """
        Create a community post with XSS sanitization and fail-closed moderation.

        Steps:
        1. Check rate limit (POSTS_PER_HOUR_LIMIT per hour)
        2. Sanitize title/body with nh3
        3. INSERT with is_pending_moderation=true
        4. Fire moderation (async, with 30s timeout)
        """
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
        result = await db.execute(insert_sql, params)
        post = dict(result.mappings().fetchone())
        await db.commit()

        # 4. Fire moderation with timeout (fail-closed: post is pending until classified)
        post_id = post["id"]
        try:
            await asyncio.wait_for(
                self._run_moderation(db, post_id, clean_title, clean_body, agent_service),
                timeout=MODERATION_TIMEOUT_SECONDS,
            )
        except (asyncio.TimeoutError, Exception) as exc:
            logger.warning(
                "moderation_timeout_or_failure",
                post_id=str(post_id),
                error=str(exc),
            )
            # Timeout: auto-clear pending moderation so post becomes visible
            await self._clear_pending_moderation(db, post_id)

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

    async def _clear_pending_moderation(self, db: AsyncSession, post_id: str) -> None:
        """Clear is_pending_moderation after timeout (fail-safe release)."""
        await db.execute(
            text("""
                UPDATE community_posts
                SET is_pending_moderation = false
                WHERE id = :post_id
            """),
            {"post_id": post_id},
        )
        await db.commit()

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
    ) -> Dict[str, Any]:
        """
        Return paginated posts, excluding hidden and pending moderation.
        Vote counts derived via LEFT JOIN COUNT.
        """
        offset = (page - 1) * per_page

        # Total count
        count_sql = text("""
            SELECT COUNT(*) FROM community_posts
            WHERE region = :region
              AND utility_type = :utility_type
              AND is_hidden = false
              AND is_pending_moderation = false
        """)
        count_result = await db.execute(
            count_sql, {"region": region, "utility_type": utility_type}
        )
        total = count_result.scalar()

        # Fetch page with derived vote/report counts
        list_sql = text("""
            SELECT
                cp.*,
                COALESCE(v.cnt, 0) AS upvote_count,
                COALESCE(r.cnt, 0) AS report_count
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
        items = [dict(row) for row in list_result.mappings().fetchall()]

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
    ) -> bool:
        """
        Toggle a vote. Returns True if vote added, False if removed.
        Uses composite PK (user_id, post_id) for dedup.
        """
        # Check existing
        check_sql = text("""
            SELECT COUNT(*) FROM community_votes
            WHERE user_id = :user_id AND post_id = :post_id
        """)
        check_result = await db.execute(
            check_sql, {"user_id": user_id, "post_id": post_id}
        )
        exists = check_result.scalar() > 0

        if exists:
            # Remove vote
            await db.execute(
                text("DELETE FROM community_votes WHERE user_id = :user_id AND post_id = :post_id"),
                {"user_id": user_id, "post_id": post_id},
            )
            await db.commit()
            return False
        else:
            # Add vote
            await db.execute(
                text("INSERT INTO community_votes (user_id, post_id) VALUES (:user_id, :post_id)"),
                {"user_id": user_id, "post_id": post_id},
            )
            await db.commit()
            return True

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
        reason: Optional[str] = None,
    ) -> None:
        """
        Report a post. Idempotent (composite PK dedup).
        Hides post when unique reporter count >= REPORT_HIDE_THRESHOLD.
        """
        # Check if already reported by this user
        check_sql = text("""
            SELECT COUNT(*) FROM community_reports
            WHERE user_id = :user_id AND post_id = :post_id
        """)
        check_result = await db.execute(
            check_sql, {"user_id": user_id, "post_id": post_id}
        )
        if check_result.scalar() > 0:
            return  # Already reported — idempotent

        # Insert report
        await db.execute(
            text("""
                INSERT INTO community_reports (user_id, post_id, reason)
                VALUES (:user_id, :post_id, :reason)
            """),
            {"user_id": user_id, "post_id": post_id, "reason": reason},
        )

        # Check total unique reporters
        count_sql = text("""
            SELECT COUNT(*) FROM community_reports WHERE post_id = :post_id
        """)
        count_result = await db.execute(count_sql, {"post_id": post_id})
        total_reports = count_result.scalar()

        if total_reports >= REPORT_HIDE_THRESHOLD:
            await db.execute(
                text("""
                    UPDATE community_posts
                    SET is_hidden = true, hidden_reason = 'reported_by_users'
                    WHERE id = :post_id
                """),
                {"post_id": post_id},
            )

        await db.commit()

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
        Returns count of posts re-moderated.
        """
        # Find posts that were auto-unhidden after timeout
        # (is_pending_moderation=false, is_hidden=false, no successful classification recorded)
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

        count = 0
        for post in posts:
            content = f"{post['title']}\n\n{post['body']}"
            try:
                classification = await agent_service.classify_content(content)
                if classification == "flagged":
                    await db.execute(
                        text("""
                            UPDATE community_posts
                            SET is_hidden = true, hidden_reason = 'flagged_by_ai_retroactive'
                            WHERE id = :post_id
                        """),
                        {"post_id": post["id"]},
                    )
                count += 1
            except Exception as exc:
                logger.warning(
                    "retroactive_moderation_failed",
                    post_id=str(post["id"]),
                    error=str(exc),
                )
        if count > 0:
            await db.commit()
        return count

    # ------------------------------------------------------------------
    # edit_and_resubmit
    # ------------------------------------------------------------------

    async def edit_and_resubmit(
        self,
        db: AsyncSession,
        user_id: str,
        post_id: str,
        data: Dict[str, Any],
        agent_service: Any,
    ) -> Dict[str, Any]:
        """
        Allow the author to edit a flagged post and resubmit for moderation.
        Only the original author can edit. Re-sanitizes and re-triggers moderation.
        """
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
        update_result = await db.execute(
            update_sql, {"title": clean_title, "body": clean_body, "post_id": post_id}
        )
        updated = dict(update_result.mappings().fetchone())
        await db.commit()

        # Re-trigger moderation
        try:
            await asyncio.wait_for(
                self._run_moderation(db, post_id, clean_title, clean_body, agent_service),
                timeout=MODERATION_TIMEOUT_SECONDS,
            )
        except (asyncio.TimeoutError, Exception) as exc:
            logger.warning("resubmit_moderation_failed", post_id=str(post_id), error=str(exc))
            await self._clear_pending_moderation(db, post_id)

        return updated

    # ------------------------------------------------------------------
    # get_stats
    # ------------------------------------------------------------------

    async def get_stats(
        self,
        db: AsyncSession,
        region: str,
    ) -> Dict[str, Any]:
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
