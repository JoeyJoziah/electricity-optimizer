"""
GDPR Compliance API Endpoints

Implements GDPR data subject rights:
- POST /consent: Record consent decision
- GET /gdpr/export: Export all user data (Article 15, 20)
- DELETE /gdpr/delete-my-data: Delete all user data (Article 17)
- GET /gdpr/consents: Get consent history
"""

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from api.dependencies import get_current_user, get_db_session, TokenData
from compliance.gdpr import GDPRComplianceService, UserNotFoundError
from compliance.repositories import ConsentRepository, DeletionLogRepository
from repositories.user_repository import UserRepository
from models.consent import (
    ConsentRequest,
    ConsentResponse,
    ConsentHistoryResponse,
    ConsentStatusResponse,
    DataDeletionRequest,
    DataDeletionResponse,
    UserDataExport,
)


router = APIRouter()


# =============================================================================
# DEPENDENCY INJECTION
# =============================================================================


async def get_gdpr_service(session=Depends(get_db_session)):
    """Get GDPR compliance service instance"""
    consent_repo = ConsentRepository(session)
    user_repo = UserRepository(session)

    return GDPRComplianceService(
        consent_repository=consent_repo,
        user_repository=user_repo,
    )


# =============================================================================
# CONSENT ENDPOINTS
# =============================================================================


@router.post(
    "/consent",
    response_model=ConsentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Record consent decision",
    description="Record a user's consent decision for a specific purpose"
)
async def record_consent(
    request: Request,
    consent_request: ConsentRequest,
    current_user: TokenData = Depends(get_current_user),
    gdpr_service: GDPRComplianceService = Depends(get_gdpr_service),
):
    """
    Record a consent decision (grant or withdrawal).

    Required for GDPR Article 6 (Lawful basis) and Article 7 (Conditions for consent).
    """
    # Get client information for audit trail
    ip_address = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "unknown")

    try:
        record = await gdpr_service.record_consent(
            user_id=current_user.user_id,
            purpose=consent_request.purpose,
            consent_given=consent_request.consent_given,
            ip_address=ip_address,
            user_agent=user_agent,
            consent_version=consent_request.consent_version or "1.0",
        )

        action = "given" if consent_request.consent_given else "withdrawn"

        return ConsentResponse(
            id=record.id,
            user_id=record.user_id,
            purpose=record.purpose,
            consent_given=record.consent_given,
            timestamp=record.timestamp,
            message=f"Consent {action} for {record.purpose}"
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to record consent: {str(e)}"
        )


@router.get(
    "/gdpr/consents",
    response_model=ConsentHistoryResponse,
    summary="Get consent history",
    description="Retrieve complete consent history for the current user"
)
async def get_consent_history(
    current_user: TokenData = Depends(get_current_user),
    gdpr_service: GDPRComplianceService = Depends(get_gdpr_service),
):
    """
    Get complete consent history for the authenticated user.
    """
    try:
        records = await gdpr_service.get_consent_history(current_user.user_id)

        return ConsentHistoryResponse(
            user_id=current_user.user_id,
            consents=records,
            total_count=len(records)
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve consent history: {str(e)}"
        )


@router.get(
    "/gdpr/consents/status",
    response_model=ConsentStatusResponse,
    summary="Get current consent status",
    description="Get current consent status for all purposes"
)
async def get_consent_status(
    current_user: TokenData = Depends(get_current_user),
    gdpr_service: GDPRComplianceService = Depends(get_gdpr_service),
):
    """
    Get current consent status for all purposes.

    Returns the latest consent decision for each purpose.
    """
    try:
        status_dict = await gdpr_service.get_current_consent_status(current_user.user_id)

        return ConsentStatusResponse(
            user_id=current_user.user_id,
            consents=status_dict,
            last_updated=datetime.now(timezone.utc)
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve consent status: {str(e)}"
        )


# =============================================================================
# DATA EXPORT ENDPOINT (Article 15, 20)
# =============================================================================


@router.get(
    "/gdpr/export",
    response_model=UserDataExport,
    summary="Export all user data",
    description="Export all user data in machine-readable JSON format (GDPR Article 15, 20)"
)
async def export_user_data(
    current_user: TokenData = Depends(get_current_user),
    gdpr_service: GDPRComplianceService = Depends(get_gdpr_service),
):
    """
    Export all user data in machine-readable format.

    Implements GDPR Article 15 (Right of access) and
    Article 20 (Right to data portability).

    Returns complete user data including:
    - Profile information
    - Preferences
    - Consent history
    - Price alerts
    - Recommendations
    - Activity logs
    """
    try:
        export_data = await gdpr_service.export_user_data(current_user.user_id)

        return UserDataExport(
            user_id=export_data["user_id"],
            export_timestamp=datetime.fromisoformat(export_data["export_timestamp"]),
            export_format_version=export_data.get("export_format_version", "1.0"),
            profile_data=export_data.get("profile_data", {}),
            preferences_data=export_data.get("preferences_data", {}),
            consent_history=export_data.get("consent_history", []),
            price_alerts=export_data.get("price_alerts", []),
            recommendations=export_data.get("recommendations", []),
            activity_logs=export_data.get("activity_logs", []),
        )

    except UserNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to export user data: {str(e)}"
        )


# =============================================================================
# DATA DELETION ENDPOINT (Article 17)
# =============================================================================


@router.delete(
    "/gdpr/delete-my-data",
    response_model=DataDeletionResponse,
    summary="Delete all user data",
    description="Permanently delete all user data (GDPR Article 17 - Right to Erasure)"
)
async def delete_user_data(
    request: Request,
    deletion_request: DataDeletionRequest,
    current_user: TokenData = Depends(get_current_user),
    gdpr_service: GDPRComplianceService = Depends(get_gdpr_service),
):
    """
    Delete all user data (Right to Erasure).

    Implements GDPR Article 17. This action is irreversible.

    The user must confirm the deletion by setting `confirmation: true`.

    Optionally, anonymized data can be retained for analytics
    by setting `retain_anonymized: true`.
    """
    # Require explicit confirmation
    if not deletion_request.confirmation:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Deletion requires explicit confirmation"
        )

    # Get client information for audit trail
    ip_address = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "unknown")

    try:
        deletion_log = await gdpr_service.delete_user_data(
            user_id=current_user.user_id,
            deleted_by=current_user.user_id,
            ip_address=ip_address,
            user_agent=user_agent,
            anonymize_retained=deletion_request.retain_anonymized,
        )

        return DataDeletionResponse(
            success=True,
            user_id=current_user.user_id,
            deleted_at=deletion_log.deleted_at,
            deleted_categories=deletion_log.data_categories_deleted,
            message="All user data has been deleted successfully",
            deletion_log_id=deletion_log.id,
        )

    except UserNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete user data: {str(e)}"
        )


# =============================================================================
# DATA DELETION ALIAS ENDPOINT (Article 17) — no-body variant
# =============================================================================


@router.delete(
    "/gdpr/delete",
    response_model=DataDeletionResponse,
    summary="Delete account (no-body variant)",
    description="Permanently delete the authenticated user's account and all associated data (GDPR Article 17). Confirmation is implied by calling this endpoint."
)
async def delete_account(
    request: Request,
    current_user: TokenData = Depends(get_current_user),
    gdpr_service: GDPRComplianceService = Depends(get_gdpr_service),
):
    """
    Delete all user data — convenience endpoint that does not require a request body.

    Confirmation is considered given by the act of calling this endpoint
    (the frontend must obtain explicit user confirmation before invoking it).
    Implements GDPR Article 17 (Right to Erasure).
    """
    ip_address = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "unknown")

    try:
        deletion_log = await gdpr_service.delete_user_data(
            user_id=current_user.user_id,
            deleted_by=current_user.user_id,
            ip_address=ip_address,
            user_agent=user_agent,
            anonymize_retained=False,
        )

        return DataDeletionResponse(
            success=True,
            user_id=current_user.user_id,
            deleted_at=deletion_log.deleted_at,
            deleted_categories=deletion_log.data_categories_deleted,
            message="All user data has been deleted successfully",
            deletion_log_id=deletion_log.id,
        )

    except UserNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete user data: {str(e)}"
        )


# =============================================================================
# CONSENT WITHDRAWAL ENDPOINT (Article 21)
# =============================================================================


@router.post(
    "/gdpr/withdraw-all-consents",
    response_model=ConsentHistoryResponse,
    summary="Withdraw all consents",
    description="Withdraw consent for all purposes (GDPR Article 21)"
)
async def withdraw_all_consents(
    request: Request,
    current_user: TokenData = Depends(get_current_user),
    gdpr_service: GDPRComplianceService = Depends(get_gdpr_service),
):
    """
    Withdraw consent for all purposes.

    Implements GDPR Article 21 (Right to object).
    Creates withdrawal records for all consent purposes.
    """
    # Get client information for audit trail
    ip_address = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "unknown")

    try:
        withdrawal_records = await gdpr_service.withdraw_all_consents(
            user_id=current_user.user_id,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        return ConsentHistoryResponse(
            user_id=current_user.user_id,
            consents=withdrawal_records,
            total_count=len(withdrawal_records)
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to withdraw consents: {str(e)}"
        )
