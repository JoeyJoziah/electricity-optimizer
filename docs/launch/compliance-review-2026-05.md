# Compliance Review — 2026-05

**Date**: 2026-05-12
**Status**: ⚠️ PARTIAL — CAN-SPAM complete; ToS/Privacy + UtilityAPI consent copy review pending manual sign-off
**PRD ref**: `.loki/prds/ph-relaunch-jun2-2026.md` Scope #13

## CAN-SPAM (✅ complete 2026-05-12)

- **Migration 068**: `unsubscribed_at TIMESTAMPTZ NULL` added to `user_drip_state` (applied to prod).
- **Public endpoint**: `GET /api/v1/public/unsubscribe?uid=&tok=` with HMAC-SHA256 token (`backend/api/v1/public/unsubscribe.py`).
- **Templates**: all 4 drip templates updated with:
  - Physical postal address (PO Box 12345, Hartford CT 06101)
  - Working "Unsubscribe" link with signed token
- **Batch query**: drip cron filters `AND unsubscribed_at IS NULL` so unsubscribed users never receive further sends.
- **Token rotation**: HMAC key sourced from `DRIP_UNSUBSCRIBE_SECRET` env var; rotation captured in DR runbook.

## ToS / Privacy Policy currency (⏳ pending)

Manual review required before Jun 2:

- Confirm last-updated date reflects 2026-05 changes (drip dispatch, UtilityAPI billing add-on).
- Confirm Stripe sub-processor language matches current product surface.
- Confirm UtilityAPI sub-processor listed in Privacy Policy.

Owner: Devin. Deadline: 2026-05-25.

## UtilityAPI consent copy (⏳ pending)

The connect-utility flow currently uses pre-rebrand copy. Review needed:

- Confirm consent screen clearly discloses $2.25/meter/mo Add-On (Scope #4 of pricing model).
- Confirm data-retention language matches Privacy Policy.
- Confirm withdrawal-of-consent path (disconnect meter → cancel sub-item) is documented.

Owner: Devin. Deadline: 2026-05-25.

## Sign-off

- [ ] ToS reviewed and dated
- [ ] Privacy Policy reviewed and dated
- [ ] UtilityAPI consent screen copy reviewed
- [x] CAN-SPAM unsubscribe flow tested end-to-end
- [x] Physical address present in all drip templates
