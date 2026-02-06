"""
GDPR Compliance Module

Provides GDPR compliance functionality including:
- Consent management (Article 6, 7)
- Right to access/data export (Article 15, 20)
- Right to erasure (Article 17)
- Right to object (Article 21)
"""

from compliance.gdpr import (
    GDPRComplianceService,
    DataRetentionService,
    UserNotFoundError,
    ConsentError,
    anonymize_email,
    anonymize_name,
    anonymize_ip,
    anonymize_user_agent,
)

__all__ = [
    "GDPRComplianceService",
    "DataRetentionService",
    "UserNotFoundError",
    "ConsentError",
    "anonymize_email",
    "anonymize_name",
    "anonymize_ip",
    "anonymize_user_agent",
]
