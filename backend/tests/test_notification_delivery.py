"""
Tests for notification delivery tracking (migration 029).

Coverage:
  1. Migration SQL parse check — validates structural conventions without
     executing SQL against a database.
  2. Notification model fields — confirms the Pydantic model exposes all
     columns added by migration 029.
  3. Delivery status transitions — verifies the model accepts every valid
     status and rejects unknown ones.
  4. DeliveryChannel validation — verifies the model accepts all three
     channel values and rejects unknown ones.
  5. Default values — delivery_status defaults to 'pending', delivery_metadata
     defaults to {}, retry_count defaults to 0.
  6. NotificationCreate schema — optional delivery_channel, body, metadata.
  7. NotificationDeliveryUpdate schema — partial-update semantics.
  8. NotificationResponse schema — confirms public API shape.
"""

import os
import re

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

MIGRATIONS_DIR = os.path.join(os.path.dirname(__file__), "..", "migrations")
MIGRATION_PREFIX = "029"


def _read_migration_029() -> str:
    """Return the raw SQL content of migration 029."""
    for filename in os.listdir(MIGRATIONS_DIR):
        if filename.startswith(MIGRATION_PREFIX) and filename.endswith(".sql"):
            path = os.path.join(MIGRATIONS_DIR, filename)
            with open(path) as fh:
                return fh.read()
    raise FileNotFoundError(
        f"No migration file starting with '{MIGRATION_PREFIX}' found in {MIGRATIONS_DIR}"
    )


# ===========================================================================
# 1. Migration SQL structural checks
# ===========================================================================


class TestMigration029Structure:
    """Parse migration 029 SQL for correctness without executing it."""

    def test_migration_file_exists(self):
        """Migration 029 SQL file must be present."""
        sql = _read_migration_029()
        assert sql.strip(), "Migration 029 file is empty"

    def test_targets_notifications_table(self):
        """Migration must operate on the notifications table."""
        sql = _read_migration_029()
        assert "notifications" in sql.lower(), (
            "Migration 029 must reference the 'notifications' table"
        )

    def test_alter_table_uses_if_not_exists(self):
        """Every ADD COLUMN statement must include IF NOT EXISTS."""
        sql = _read_migration_029()
        violations = []
        for i, line in enumerate(sql.splitlines(), 1):
            stripped = line.strip().upper()
            if stripped.startswith("--"):
                continue
            if "ADD COLUMN" in stripped and "IF NOT EXISTS" not in stripped:
                violations.append(f"line {i}: {line.strip()}")
        assert not violations, (
            "ADD COLUMN without IF NOT EXISTS:\n" + "\n".join(violations)
        )

    def test_index_uses_if_not_exists(self):
        """CREATE INDEX must include IF NOT EXISTS."""
        sql = _read_migration_029()
        violations = []
        for i, line in enumerate(sql.splitlines(), 1):
            stripped = line.strip().upper()
            if stripped.startswith("--"):
                continue
            if (
                stripped.startswith("CREATE INDEX")
                and "IF NOT EXISTS" not in stripped
                and "CONCURRENTLY" not in stripped
            ):
                violations.append(f"line {i}: {line.strip()}")
        assert not violations, (
            "CREATE INDEX without IF NOT EXISTS:\n" + "\n".join(violations)
        )

    def test_no_serial_columns(self):
        """Migration must not use SERIAL or BIGSERIAL (violates project conventions)."""
        sql = _read_migration_029()
        assert "SERIAL" not in sql.upper(), (
            "Migration 029 must not use SERIAL/BIGSERIAL — use INTEGER DEFAULT 0 instead"
        )

    def test_contains_grant_to_neondb_owner(self):
        """Migration must include a GRANT to neondb_owner."""
        sql = _read_migration_029()
        assert "neondb_owner" in sql, (
            "Migration 029 must GRANT permissions to neondb_owner"
        )

    def test_delivery_channel_column_present(self):
        """SQL must add the delivery_channel column."""
        sql = _read_migration_029()
        assert "delivery_channel" in sql.lower(), (
            "Migration 029 must add a 'delivery_channel' column"
        )

    def test_delivery_status_column_present(self):
        """SQL must add the delivery_status column with default 'pending'."""
        sql = _read_migration_029()
        assert "delivery_status" in sql.lower(), (
            "Migration 029 must add a 'delivery_status' column"
        )
        assert "pending" in sql.lower(), (
            "delivery_status column must DEFAULT to 'pending'"
        )

    def test_delivered_at_column_present(self):
        """SQL must add the delivered_at TIMESTAMPTZ column."""
        sql = _read_migration_029()
        assert "delivered_at" in sql.lower(), (
            "Migration 029 must add a 'delivered_at' column"
        )

    def test_delivery_metadata_column_present(self):
        """SQL must add the delivery_metadata JSONB column."""
        sql = _read_migration_029()
        assert "delivery_metadata" in sql.lower(), (
            "Migration 029 must add a 'delivery_metadata' column"
        )

    def test_retry_count_column_present(self):
        """SQL must add the retry_count INTEGER column."""
        sql = _read_migration_029()
        assert "retry_count" in sql.lower(), (
            "Migration 029 must add a 'retry_count' column"
        )

    def test_index_on_user_id_delivery_status(self):
        """SQL must create an index covering (user_id, delivery_status)."""
        sql = _read_migration_029()
        # Normalise whitespace for pattern matching
        normalised = re.sub(r"\s+", " ", sql.lower())
        assert "user_id" in normalised and "delivery_status" in normalised, (
            "Migration 029 must create an index on (user_id, delivery_status)"
        )
        # Confirm the index exists by finding a CREATE INDEX … ON notifications block
        assert re.search(
            r"create index if not exists\s+\w+\s+on notifications\s*\(",
            normalised,
        ), "Migration 029 must CREATE INDEX IF NOT EXISTS on the notifications table"


# ===========================================================================
# 2. Notification model field presence
# ===========================================================================


class TestNotificationModelFields:
    """Confirm the Pydantic Notification model exposes all migration-029 columns."""

    def test_model_has_delivery_channel(self):
        from models.notification import Notification
        assert "delivery_channel" in Notification.model_fields

    def test_model_has_delivery_status(self):
        from models.notification import Notification
        assert "delivery_status" in Notification.model_fields

    def test_model_has_delivered_at(self):
        from models.notification import Notification
        assert "delivered_at" in Notification.model_fields

    def test_model_has_delivery_metadata(self):
        from models.notification import Notification
        assert "delivery_metadata" in Notification.model_fields

    def test_model_has_retry_count(self):
        from models.notification import Notification
        assert "retry_count" in Notification.model_fields

    def test_model_has_core_fields(self):
        """All pre-029 columns should still be present."""
        from models.notification import Notification
        for field in ("id", "user_id", "type", "title", "body", "read_at", "created_at"):
            assert field in Notification.model_fields, (
                f"Core field '{field}' missing from Notification model"
            )

    def test_model_has_metadata_field(self):
        """Metadata column from migration 026 must be preserved."""
        from models.notification import Notification
        assert "metadata" in Notification.model_fields


# ===========================================================================
# 3. Default values
# ===========================================================================


class TestNotificationModelDefaults:
    """Verify column defaults match the DDL."""

    def test_delivery_status_defaults_to_pending(self):
        from models.notification import Notification
        n = Notification(user_id="u1", title="Hello")
        assert n.delivery_status == "pending"

    def test_delivery_metadata_defaults_to_empty_dict(self):
        from models.notification import Notification
        n = Notification(user_id="u1", title="Hello")
        assert n.delivery_metadata == {}

    def test_retry_count_defaults_to_zero(self):
        from models.notification import Notification
        n = Notification(user_id="u1", title="Hello")
        assert n.retry_count == 0

    def test_delivery_channel_defaults_to_none(self):
        from models.notification import Notification
        n = Notification(user_id="u1", title="Hello")
        assert n.delivery_channel is None

    def test_delivered_at_defaults_to_none(self):
        from models.notification import Notification
        n = Notification(user_id="u1", title="Hello")
        assert n.delivered_at is None

    def test_type_defaults_to_info(self):
        from models.notification import Notification
        n = Notification(user_id="u1", title="Hello")
        assert n.type == "info"


# ===========================================================================
# 4. Delivery status transitions
# ===========================================================================


class TestDeliveryStatusTransitions:
    """All valid delivery_status values must be accepted by the model."""

    @pytest.mark.parametrize("status", ["pending", "sent", "delivered", "failed", "bounced"])
    def test_valid_status_accepted(self, status):
        from models.notification import Notification
        n = Notification(user_id="u1", title="T", delivery_status=status)
        assert n.delivery_status == status

    def test_invalid_status_rejected(self):
        from models.notification import Notification
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            Notification(user_id="u1", title="T", delivery_status="unknown_status")

    def test_status_transition_pending_to_sent(self):
        """Simulates a dispatcher updating a notification after a successful send."""
        from models.notification import Notification
        n = Notification(user_id="u1", title="Price Alert", delivery_status="pending")
        assert n.delivery_status == "pending"
        # Simulate the row being updated in the DB and re-fetched
        updated = n.model_copy(update={"delivery_status": "sent"})
        assert updated.delivery_status == "sent"

    def test_status_transition_sent_to_delivered(self):
        from models.notification import Notification
        from datetime import datetime, timezone
        n = Notification(
            user_id="u1",
            title="Price Alert",
            delivery_status="sent",
            delivery_channel="email",
        )
        confirmed_at = datetime.now(timezone.utc)
        updated = n.model_copy(
            update={"delivery_status": "delivered", "delivered_at": confirmed_at}
        )
        assert updated.delivery_status == "delivered"
        assert updated.delivered_at == confirmed_at

    def test_status_transition_sent_to_bounced(self):
        from models.notification import Notification
        n = Notification(
            user_id="u1",
            title="Price Alert",
            delivery_status="sent",
            delivery_channel="email",
        )
        updated = n.model_copy(
            update={
                "delivery_status": "bounced",
                "delivery_metadata": {"bounce_reason": "invalid_address"},
            }
        )
        assert updated.delivery_status == "bounced"
        assert updated.delivery_metadata["bounce_reason"] == "invalid_address"

    def test_status_transition_failed_increments_retry(self):
        from models.notification import Notification
        n = Notification(user_id="u1", title="T", delivery_status="pending", retry_count=0)
        updated = n.model_copy(update={"delivery_status": "failed", "retry_count": 1})
        assert updated.delivery_status == "failed"
        assert updated.retry_count == 1


# ===========================================================================
# 5. DeliveryChannel validation
# ===========================================================================


class TestDeliveryChannelValidation:
    """All valid channel values must be accepted; unknown values rejected."""

    @pytest.mark.parametrize("channel", ["email", "push", "in_app"])
    def test_valid_channel_accepted(self, channel):
        from models.notification import Notification
        n = Notification(user_id="u1", title="T", delivery_channel=channel)
        assert n.delivery_channel == channel

    def test_invalid_channel_rejected(self):
        from models.notification import Notification
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            Notification(user_id="u1", title="T", delivery_channel="sms")

    def test_none_channel_accepted(self):
        """delivery_channel is nullable — None must not raise."""
        from models.notification import Notification
        n = Notification(user_id="u1", title="T", delivery_channel=None)
        assert n.delivery_channel is None


# ===========================================================================
# 6. NotificationCreate schema
# ===========================================================================


class TestNotificationCreateSchema:
    """Validate the create-input schema."""

    def test_minimal_create_succeeds(self):
        from models.notification import NotificationCreate
        nc = NotificationCreate(user_id="u1", title="Hello")
        assert nc.user_id == "u1"
        assert nc.title == "Hello"
        assert nc.type == "info"
        assert nc.body is None
        assert nc.metadata is None
        assert nc.delivery_channel is None

    def test_create_with_all_fields(self):
        from models.notification import NotificationCreate
        nc = NotificationCreate(
            user_id="u1",
            type="price_alert",
            title="Low price",
            body="$0.08/kWh in CT",
            metadata={"dedup_key": "price_alert:us_ct"},
            delivery_channel="email",
        )
        assert nc.delivery_channel == "email"
        assert nc.metadata == {"dedup_key": "price_alert:us_ct"}

    def test_title_required(self):
        from models.notification import NotificationCreate
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            NotificationCreate(user_id="u1")

    def test_invalid_delivery_channel_rejected(self):
        from models.notification import NotificationCreate
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            NotificationCreate(user_id="u1", title="T", delivery_channel="fax")


# ===========================================================================
# 7. NotificationDeliveryUpdate schema
# ===========================================================================


class TestNotificationDeliveryUpdateSchema:
    """Validate the delivery-update patch schema."""

    def test_status_only_update(self):
        from models.notification import NotificationDeliveryUpdate
        upd = NotificationDeliveryUpdate(delivery_status="sent")
        assert upd.delivery_status == "sent"
        assert upd.delivery_channel is None
        assert upd.delivered_at is None
        assert upd.delivery_metadata is None
        assert upd.retry_count is None

    def test_full_delivery_update(self):
        from models.notification import NotificationDeliveryUpdate
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        upd = NotificationDeliveryUpdate(
            delivery_status="delivered",
            delivery_channel="push",
            delivered_at=now,
            delivery_metadata={"onesignal_id": "abc123"},
            retry_count=0,
        )
        assert upd.delivery_status == "delivered"
        assert upd.delivery_channel == "push"
        assert upd.delivered_at == now
        assert upd.delivery_metadata == {"onesignal_id": "abc123"}

    def test_invalid_status_rejected(self):
        from models.notification import NotificationDeliveryUpdate
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            NotificationDeliveryUpdate(delivery_status="lost")

    def test_negative_retry_count_rejected(self):
        from models.notification import NotificationDeliveryUpdate
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            NotificationDeliveryUpdate(delivery_status="failed", retry_count=-1)


# ===========================================================================
# 8. NotificationResponse schema
# ===========================================================================


class TestNotificationResponseSchema:
    """Validate the public response schema shape."""

    def test_response_has_delivery_fields(self):
        from models.notification import NotificationResponse
        fields = NotificationResponse.model_fields
        for field in ("delivery_channel", "delivery_status", "delivered_at", "retry_count"):
            assert field in fields, f"NotificationResponse missing field '{field}'"

    def test_response_defaults(self):
        from models.notification import NotificationResponse
        from datetime import datetime, timezone
        r = NotificationResponse(
            id="abc",
            type="info",
            title="Test",
            created_at=datetime.now(timezone.utc),
        )
        assert r.delivery_status == "pending"
        assert r.retry_count == 0
        assert r.delivery_channel is None
        assert r.delivered_at is None

    def test_response_excludes_internal_fields(self):
        """NotificationResponse should not expose delivery_metadata or metadata."""
        from models.notification import NotificationResponse
        fields = set(NotificationResponse.model_fields.keys())
        # These are internal — not part of the public response
        assert "delivery_metadata" not in fields, (
            "delivery_metadata should not be in NotificationResponse (internal use only)"
        )
        assert "metadata" not in fields, (
            "metadata (dedup/internal) should not be in NotificationResponse"
        )

    def test_notification_list_response(self):
        from models.notification import NotificationListResponse, NotificationResponse
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        items = [
            NotificationResponse(id=f"id-{i}", type="info", title=f"Notif {i}", created_at=now)
            for i in range(3)
        ]
        resp = NotificationListResponse(notifications=items, total=3)
        assert resp.total == 3
        assert len(resp.notifications) == 3
