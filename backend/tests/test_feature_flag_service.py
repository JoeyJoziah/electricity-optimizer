"""
Tests for FeatureFlagService (backend/services/feature_flag_service.py).

Coverage:
- is_enabled: flag not found → False
- is_enabled: flag disabled → False
- is_enabled: tier gating (free < pro < business hierarchy)
- is_enabled: percentage=100 always allows
- is_enabled: percentage rollout determinism — same user/flag always gets same result
- is_enabled: no user_id bypasses percentage gate
- get_all_flags: returns list with expected keys
- update_flag: returns False when no fields provided
- update_flag: commits and returns True with valid fields
- update_flag: rolls back and re-raises on DB error
"""

import hashlib
from unittest.mock import AsyncMock, MagicMock

import pytest

from services.feature_flag_service import FeatureFlagService

# =============================================================================
# Helpers
# =============================================================================


def _make_db(row=None, rows=None):
    db = AsyncMock()
    result = MagicMock()
    result.fetchone = MagicMock(return_value=row)
    result.fetchall = MagicMock(return_value=rows or [])
    db.execute = AsyncMock(return_value=result)
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    return db


def _flag_row(enabled=True, tier_required=None, percentage=100):
    """Return a tuple that matches the SELECT query column order."""
    return (enabled, tier_required, percentage)


# =============================================================================
# is_enabled
# =============================================================================


class TestIsEnabled:
    @pytest.mark.asyncio
    async def test_returns_false_when_flag_not_found(self):
        db = _make_db(row=None)
        svc = FeatureFlagService(db)
        assert await svc.is_enabled("unknown_flag") is False

    @pytest.mark.asyncio
    async def test_returns_false_when_flag_disabled(self):
        db = _make_db(row=_flag_row(enabled=False))
        svc = FeatureFlagService(db)
        assert await svc.is_enabled("my_flag", user_id="u1", user_tier="pro") is False

    @pytest.mark.asyncio
    async def test_returns_true_when_flag_enabled_no_gating(self):
        db = _make_db(row=_flag_row(enabled=True, tier_required=None, percentage=100))
        svc = FeatureFlagService(db)
        assert await svc.is_enabled("my_flag") is True

    # ---- Tier gating --------------------------------------------------------

    @pytest.mark.asyncio
    async def test_tier_gating_free_blocked_by_pro_requirement(self):
        db = _make_db(row=_flag_row(enabled=True, tier_required="pro", percentage=100))
        svc = FeatureFlagService(db)
        assert await svc.is_enabled("my_flag", user_tier="free") is False

    @pytest.mark.asyncio
    async def test_tier_gating_pro_allowed_for_pro_requirement(self):
        db = _make_db(row=_flag_row(enabled=True, tier_required="pro", percentage=100))
        svc = FeatureFlagService(db)
        assert await svc.is_enabled("my_flag", user_tier="pro") is True

    @pytest.mark.asyncio
    async def test_tier_gating_business_allowed_for_pro_requirement(self):
        """business > pro so it should pass a pro-gated flag."""
        db = _make_db(row=_flag_row(enabled=True, tier_required="pro", percentage=100))
        svc = FeatureFlagService(db)
        assert await svc.is_enabled("my_flag", user_tier="business") is True

    @pytest.mark.asyncio
    async def test_tier_gating_skipped_when_user_tier_not_provided(self):
        """When user_tier is None the tier check is skipped and flag passes."""
        db = _make_db(row=_flag_row(enabled=True, tier_required="pro", percentage=100))
        svc = FeatureFlagService(db)
        assert await svc.is_enabled("my_flag", user_tier=None) is True

    @pytest.mark.asyncio
    async def test_tier_gating_skipped_when_tier_required_is_none(self):
        db = _make_db(row=_flag_row(enabled=True, tier_required=None, percentage=100))
        svc = FeatureFlagService(db)
        assert await svc.is_enabled("my_flag", user_tier="free") is True

    # ---- Percentage rollout -------------------------------------------------

    @pytest.mark.asyncio
    async def test_percentage_100_always_allows(self):
        db = _make_db(row=_flag_row(enabled=True, percentage=100))
        svc = FeatureFlagService(db)
        assert await svc.is_enabled("my_flag", user_id="any-user") is True

    @pytest.mark.asyncio
    async def test_percentage_0_always_blocks(self):
        db = _make_db(row=_flag_row(enabled=True, percentage=0))
        svc = FeatureFlagService(db)
        assert await svc.is_enabled("my_flag", user_id="any-user") is False

    @pytest.mark.asyncio
    async def test_percentage_rollout_is_deterministic(self):
        """Same flag + user must always produce the same allow/deny outcome."""
        db = _make_db(row=_flag_row(enabled=True, percentage=50))
        svc = FeatureFlagService(db)
        results = set()
        for _ in range(5):
            # Reset mock so each call fetches the same row
            db.execute.return_value.fetchone.return_value = _flag_row(enabled=True, percentage=50)
            results.add(await svc.is_enabled("my_flag", user_id="user-abc"))
        # Deterministic: same user always same result
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_percentage_gate_skipped_when_no_user_id(self):
        """When user_id is not provided the percentage gate should be skipped."""
        db = _make_db(row=_flag_row(enabled=True, percentage=1))
        svc = FeatureFlagService(db)
        # percentage=1 with no user_id → gate bypassed → True
        assert await svc.is_enabled("my_flag", user_id=None) is True

    @pytest.mark.asyncio
    async def test_percentage_rollout_hash_boundary(self):
        """Verify the MD5 hash boundary logic matches the service implementation."""
        flag_name = "boundary_test"
        user_id = "test-user-rollout"
        hash_val = int(
            hashlib.md5(f"{flag_name}:{user_id}".encode(), usedforsecurity=False).hexdigest()[:8],
            16,
        )
        bucket = hash_val % 100
        # Set percentage to exactly bucket+1 → user is included
        db = _make_db(row=_flag_row(enabled=True, percentage=bucket + 1))
        svc = FeatureFlagService(db)
        assert await svc.is_enabled(flag_name, user_id=user_id) is True

        # Set percentage to bucket → user is excluded (hash_val % 100 >= percentage)
        db2 = _make_db(row=_flag_row(enabled=True, percentage=bucket))
        svc2 = FeatureFlagService(db2)
        assert await svc2.is_enabled(flag_name, user_id=user_id) is False


# =============================================================================
# get_all_flags
# =============================================================================


class TestGetAllFlags:
    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_flags(self):
        db = _make_db(rows=[])
        svc = FeatureFlagService(db)
        result = await svc.get_all_flags()
        assert result == []

    @pytest.mark.asyncio
    async def test_returns_flags_with_expected_keys(self):
        db = _make_db(rows=[("new_ui", True, "pro", 80, "New UI rollout")])
        svc = FeatureFlagService(db)
        flags = await svc.get_all_flags()
        assert len(flags) == 1
        flag = flags[0]
        for key in ("name", "enabled", "tier_required", "percentage", "description"):
            assert key in flag, f"Missing key: {key}"

    @pytest.mark.asyncio
    async def test_flag_values_match_db_row(self):
        db = _make_db(rows=[("beta_feature", False, "business", 25, "Beta")])
        svc = FeatureFlagService(db)
        flags = await svc.get_all_flags()
        f = flags[0]
        assert f["name"] == "beta_feature"
        assert f["enabled"] is False
        assert f["tier_required"] == "business"
        assert f["percentage"] == 25
        assert f["description"] == "Beta"


# =============================================================================
# update_flag
# =============================================================================


class TestUpdateFlag:
    @pytest.mark.asyncio
    async def test_returns_false_when_no_fields_provided(self):
        db = _make_db()
        svc = FeatureFlagService(db)
        result = await svc.update_flag("my_flag")
        assert result is False
        db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_commits_and_returns_true_when_enabled_provided(self):
        db = _make_db()
        svc = FeatureFlagService(db)
        result = await svc.update_flag("my_flag", enabled=True)
        assert result is True
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_commits_and_returns_true_when_percentage_provided(self):
        db = _make_db()
        svc = FeatureFlagService(db)
        result = await svc.update_flag("my_flag", percentage=75)
        assert result is True
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_commits_and_returns_true_when_tier_required_provided(self):
        db = _make_db()
        svc = FeatureFlagService(db)
        result = await svc.update_flag("my_flag", tier_required="pro")
        assert result is True
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_rollback_and_reraise_on_db_error(self):
        db = _make_db()
        db.execute.side_effect = Exception("deadlock detected")
        svc = FeatureFlagService(db)
        with pytest.raises(Exception, match="deadlock detected"):
            await svc.update_flag("my_flag", enabled=False)
        db.rollback.assert_awaited_once()
        db.commit.assert_not_awaited()
