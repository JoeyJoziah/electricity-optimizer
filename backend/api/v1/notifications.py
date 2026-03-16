"""
Notifications API

Endpoints for in-app notification management:
- GET  /notifications              — list unread notifications
- GET  /notifications/count        — unread count (for bell badge)
- PUT  /notifications/read-all     — mark all notifications read
- PUT  /notifications/{id}/read    — mark a single notification read
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_current_user, get_db_session, SessionData
from services.notification_service import NotificationService

router = APIRouter(prefix="/notifications", tags=["Notifications"])


@router.get("")
async def get_notifications(
    current_user: SessionData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """Return the caller's unread notifications (newest first, max 50)."""
    svc = NotificationService(db)
    items = await svc.get_unread(current_user.user_id)
    return {"notifications": items, "total": len(items)}


@router.get("/count")
async def get_notification_count(
    current_user: SessionData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """Return the number of unread notifications for the caller."""
    svc = NotificationService(db)
    count = await svc.get_unread_count(current_user.user_id)
    return {"unread": count}


@router.put("/read-all")
async def mark_all_notifications_read(
    current_user: SessionData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """Mark all unread notifications as read for the caller."""
    svc = NotificationService(db)
    count = await svc.mark_all_read(current_user.user_id)
    return {"success": True, "marked": count}


@router.put("/{notification_id}/read")
async def mark_notification_read(
    notification_id: uuid.UUID = Path(..., description="UUID of the notification to mark read"),
    current_user: SessionData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """Mark a single notification as read. Returns 404 if not found or already read."""
    svc = NotificationService(db)
    success = await svc.mark_read(current_user.user_id, str(notification_id))
    if not success:
        raise HTTPException(status_code=404, detail="Notification not found")
    return {"success": True}
