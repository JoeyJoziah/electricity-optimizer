"""
Shared fixtures for security test suite.

Provides:
  - ``client`` — function-scoped TestClient(app) for all security tests
  - ``reset_rate_limiter`` — autouse fixture that resets rate limiter state
    between tests so that high-volume tests (e.g. rate limit enforcement)
    don't leave behind state that causes subsequent tests to fail
"""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """Create a fresh test client for each test function.

    The app is imported from ``main`` which is on ``sys.path`` thanks to
    the root ``tests/conftest.py`` that inserts ``backend/`` into the path.
    """
    from main import app

    return TestClient(app)


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    """Reset the in-memory rate limiter state before and after each test.

    In the test environment (ENVIRONMENT=test), the rate limiter uses an
    in-memory store rather than Redis.  Tests that fire hundreds of requests
    (e.g. ``TestRateLimitEnforcement``) saturate the store, causing later
    tests in the same process to start already rate-limited.

    This fixture clears the store on both setup and teardown so that every
    test starts with a clean slate and leaves no residual state.
    """
    _do_reset()
    yield
    _do_reset()


def _do_reset():
    """Clear the rate limiter's in-memory state.

    ``main._app_rate_limiter`` is the ``UserRateLimiter`` instance created
    by ``app_factory.create_app()`` and wired into the ``RateLimitMiddleware``.
    In test mode it has no Redis client, so all state lives in
    ``_memory_store``.  Calling ``reset()`` clears that dict and detaches
    any Redis reference (a no-op in tests).

    We also reset the module-level ``rate_limiter`` global in
    ``middleware.rate_limiter`` in case any code path obtained a reference
    to it independently of the app factory instance.
    """
    try:
        from main import _app_rate_limiter

        _app_rate_limiter.reset()
    except (ImportError, AttributeError):
        pass

    try:
        from middleware import rate_limiter as rl_module

        if rl_module.rate_limiter is not None:
            rl_module.rate_limiter.reset()
    except (ImportError, AttributeError):
        pass
