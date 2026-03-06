"""
Combined router for the Connections feature package.

Registration order is critical. FastAPI matches routes in the order they are
registered. The /{connection_id} wildcard in crud.py would swallow any static
path segment (like "analytics", "email", "direct") if registered first.

Required registration order:
  1. analytics   — /analytics/* static prefixes (before wildcard)
  2. email_oauth — POST /email, GET /email/callback, POST /email/{id}/scan
  3. bill_upload — POST /upload + /{id}/upload* routes
  4. direct_sync — GET /direct/callback + /{id}/sync + /{id}/sync-status
  5. rates       — /{connection_id}/rates and /{connection_id}/rates/current
  6. crud        — GET "", POST /direct, GET/DELETE/PATCH /{connection_id} wildcard

Rationale for each ordering decision:
- analytics before crud: /analytics/* must not be captured by /{connection_id}.
- email_oauth before crud: /email/callback and /email/{id}/scan must not be
  captured by /{connection_id}.
- bill_upload before crud: POST /upload must not be captured by /{connection_id}.
- direct_sync before crud: GET /direct/callback must not be captured by
  /{connection_id}. Note that POST /direct (create_direct_connection) is in
  crud.py and is a POST route — it does not conflict with the GET/DELETE/PATCH
  /{connection_id} wildcard but is registered there for logical grouping.
- rates before crud: /{id}/rates and /{id}/rates/current involve the same
  /{connection_id} parameter, so FastAPI matches by method + path. These are
  safe relative to crud's GET /{connection_id} because the /rates suffix
  makes them distinct; however, keeping rates before the generic wildcard is
  the safer convention.
"""

from fastapi import APIRouter

from api.v1.connections import (analytics, bill_upload, crud, direct_sync,
                                email_oauth, rates)

router = APIRouter()

# 1. Analytics: /analytics/comparison, /analytics/history,
#               /analytics/savings, /analytics/health
router.include_router(analytics.router)

# 2. Email OAuth: POST /email, GET /email/callback,
#                POST /email/{connection_id}/scan
router.include_router(email_oauth.router)

# 3. Bill upload:
#    POST /upload                              (create stub)
#    POST /{connection_id}/upload              (file upload)
#    GET  /{connection_id}/uploads             (list)
#    GET  /{connection_id}/uploads/{upload_id} (single)
#    POST /{connection_id}/uploads/{upload_id}/reparse
router.include_router(bill_upload.router)

# 4. Direct sync (Phase 4 / UtilityAPI):
#    GET  /direct/callback                     (UtilityAPI callback — before wildcard)
#    POST /{connection_id}/sync
#    GET  /{connection_id}/sync-status
router.include_router(direct_sync.router)

# 5. Rates: /{connection_id}/rates and /{connection_id}/rates/current
router.include_router(rates.router)

# 6. CRUD: GET "", POST /direct, GET /{connection_id},
#          DELETE /{connection_id}, PATCH /{connection_id}
#    The wildcard routes must come last.
router.include_router(crud.router)
