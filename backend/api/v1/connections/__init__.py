"""
Connections feature package.

Public API surface (preserves all import paths used in main.py and tests):

  from api.v1.connections import router                # main.py include_router
  from api.v1.connections import require_paid_tier     # test dependency override
  from api.v1.connections import sign_callback_state   # test_utilityapi.py direct import
  from api.v1.connections import _UPLOADS_DIR          # patchable in test_bill_upload.py
  from api.v1.connections import _run_background_parse # patchable in test_bill_upload.py
  from api.v1.connections import settings              # patchable in test_email_oauth.py
                                                       # and test_utilityapi.py

Patching behaviour:
  Several tests use ``patch("api.v1.connections.<name>", ...)`` which replaces
  the named attribute on THIS module object.  For the patch to take effect in
  sub-module handlers, those handlers must look the name up through this module
  at call time (via ``import api.v1.connections as _pkg; _pkg.<name>``).
  Sub-modules that do this: bill_upload.py, email_oauth.py, and common.py.
"""

from api.v1.connections.bill_upload import _run_background_parse
from api.v1.connections.common import (_UPLOADS_DIR, require_paid_tier,
                                       sign_callback_state)
from api.v1.connections.router import router
from config.settings import settings  # re-exported so tests can patch it here

__all__ = [
    "router",
    "require_paid_tier",
    "sign_callback_state",
    "_UPLOADS_DIR",
    "_run_background_parse",
    "settings",
]
