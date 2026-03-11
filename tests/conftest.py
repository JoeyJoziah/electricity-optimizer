"""
Root conftest for project-level test suites (security, performance, load).

Adds the ``backend/`` directory to ``sys.path`` so that ``from main import app``
resolves correctly when pytest is invoked from the project root rather than
from inside ``backend/``.  This mirrors the same path-injection performed by
``backend/tests/conftest.py`` for the backend unit/integration test suite.
"""

import os
import sys
from pathlib import Path

# Ensure backend/ is on the path before any test module is imported.
# This makes ``import main``, ``from main import app``, and all sibling
# backend imports (app_factory, config, etc.) work correctly.
_backend_dir = Path(__file__).parent.parent / "backend"
if str(_backend_dir) not in sys.path:
    sys.path.insert(0, str(_backend_dir))

# Put the project in test mode so app_factory skips Redis wiring, etc.
os.environ.setdefault("ENVIRONMENT", "test")
