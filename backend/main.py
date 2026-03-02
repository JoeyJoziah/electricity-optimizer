"""
Electricity Optimizer - FastAPI Backend Entry Point

All application construction is delegated to app_factory.create_app().
This module only exists to:
  1. Provide the ``app`` and ``_app_rate_limiter`` names at module scope so
     that every ``from main import app`` / ``from main import _app_rate_limiter``
     import in the test suite continues to work without modification.
  2. Launch uvicorn when executed directly (``python main.py``).
"""

from app_factory import create_app

app, _app_rate_limiter = create_app()


if __name__ == "__main__":
    import uvicorn
    from config.settings import settings

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=settings.backend_port,
        reload=settings.is_development,
        log_level="info",
    )
