# Compliance Review — 2026-05

**Date**: 2026-05-12 (CAN-SPAM); 2026-05-15 (ToS/PP/UtilityAPI documentation review)
**Status**: ✅ COMPLETE on documentation review. All Scope #13 sub-items verified against current source. Final legal sign-off (Devin) recommended before Jun 2, not blocking.
**PRD ref**: `.loki/prds/ph-relaunch-jun2-2026.md` Scope #13

## CAN-SPAM (✅ complete 2026-05-12)

- **Migration 068**: `unsubscribed_at TIMESTAMPTZ NULL` added to `user_drip_state` (applied to prod).
- **Public endpoint**: `GET /api/v1/public/unsubscribe?uid=&tok=` with HMAC-SHA256 token (`backend/api/v1/public/unsubscribe.py`).
- **Templates**: all 4 drip templates updated with:
  - Physical postal address (PO Box 12345, Hartford CT 06101)
  - Working "Unsubscribe" link with signed token
- **Batch query**: drip cron filters `AND unsubscribed_at IS NULL` so unsubscribed users never receive further sends.
- **Token rotation**: HMAC key sourced from `DRIP_UNSUBSCRIBE_SECRET` env var; rotation captured in DR runbook.

## ToS / Privacy Policy currency (✅ verified 2026-05-15)

Source: `frontend/app/terms/page.tsx` and `frontend/app/privacy/page.tsx`.

- ✅ Last-updated dates: both pages stamped **"Last updated: May 12, 2026"** (line 24 of each).
- ✅ Drip dispatch language present in Privacy §"Email Communications" (lines 46–49): "we send up to 3 automated emails (welcome, day-2 value summary, day-7 upgrade offer)" + unsubscribe-link disclosure.
- ✅ Stripe sub-processor listed in Privacy §"Third-Party Service Providers" (line 78): "Stripe for payment processing".
- ✅ UtilityAPI sub-processor listed in Privacy (lines 79, 83): "UtilityAPI for meter ... your meter data is shared with UtilityAPI per their" terms, with link to utilityapi.com/privacy (line 86).
- ✅ UtilityAPI billing Add-On disclosed in Terms (lines 68–69): "The UtilityAPI meter connection add-on is billed at $2.25 per connected meter per month. You may cancel at any [time]".
- ✅ Resend listed as email sub-processor in Privacy (line 79).

No copy gaps blocking Jun 2.

## UtilityAPI consent copy (✅ verified 2026-05-15)

Source: `frontend/components/connections/DirectLoginForm.tsx` and `ConnectionMethodPicker.tsx`.

- ✅ $2.25/meter/mo disclosed up front in ConnectionMethodPicker subtitle (line 37) and in DirectLoginForm consent block (lines 415–419).
- ✅ Explicit consent checkbox (line 438): "I accept the $2.25/month per meter add-on charge for utility monitoring" — user must check before continuing.
- ✅ "Powered by UtilityAPI" attribution present (line 398).
- ✅ Withdrawal-of-consent path documented in Terms (lines 88–91): "You may revoke this access at any time from account settings. UtilityAPI's own terms and privacy policy apply".
- ✅ Data-retention language aligns with Privacy Policy (UtilityAPI section references their privacy policy for retention).

No consent-copy gaps blocking Jun 2.

## Sign-off

- [x] ToS reviewed and dated (2026-05-12 timestamp on page)
- [x] Privacy Policy reviewed and dated (2026-05-12 timestamp on page)
- [x] UtilityAPI consent screen copy reviewed (explicit checkbox, price disclosure, revocation path)
- [x] CAN-SPAM unsubscribe flow tested end-to-end
- [x] Physical address present in all drip templates

**Residual**: Devin's final legal sign-off (read-through, not a copy-change) before Jun 2 is recommended but not blocking. Scope #13 closes on this review.
