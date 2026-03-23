# ===========================================================================
# DEPRECATED — Do not use this Dockerfile directly.
#
# The canonical production Dockerfile for the backend is:
#
#     backend/Dockerfile
#
# Render (render.yaml) and CI (ci.yml) both reference backend/Dockerfile
# with dockerContext: ./backend. This root Dockerfile previously existed as
# an alternative single-stage build but diverged from backend/Dockerfile
# (1 worker vs 2, different health-check start-period, etc.), creating
# operational ambiguity.
#
# For local development:
#     docker compose up              (uses backend/Dockerfile target=development)
#
# For production builds:
#     docker build -f backend/Dockerfile -t rateshift-backend ./backend --target production
#
# See: .audit-2026-03-23/20-infra-deploy.md P0-01
# ===========================================================================
