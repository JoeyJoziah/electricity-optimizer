#!/bin/bash
# Generate TypeScript types from FastAPI OpenAPI spec.
#
# Usage:
#   npm run generate-types                  # uses BACKEND_URL or localhost:8000
#   BACKEND_URL=http://localhost:8000 npm run generate-types
#   npm run generate-types -- --from-file  # generate from saved openapi.json
#
# The output file (types/generated/api.ts) is committed to the repo so the
# frontend can be built without a running backend.  Re-generate whenever
# backend Pydantic schemas change.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FRONTEND_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
OUTPUT="$FRONTEND_DIR/types/generated/api.ts"
SAVED_SPEC="$FRONTEND_DIR/types/generated/openapi.json"

# Allow override via env; default to localhost for local dev.
# In CI the backend runs as a service container so localhost works there too.
BACKEND_URL="${BACKEND_URL:-http://localhost:8000}"
OPENAPI_URL="$BACKEND_URL/openapi.json"

mkdir -p "$(dirname "$OUTPUT")"

# --from-file flag: regenerate from the previously saved spec without needing
# a live backend.  Useful in CI where the backend may not be running.
if [[ "${1:-}" == "--from-file" ]]; then
  if [[ ! -f "$SAVED_SPEC" ]]; then
    echo "ERROR: No saved spec found at $SAVED_SPEC"
    echo "       Run without --from-file first to download and save the spec."
    exit 1
  fi
  echo "Regenerating types from saved spec at $SAVED_SPEC ..."
  npx openapi-typescript "$SAVED_SPEC" -o "$OUTPUT"
  echo "Done. Types written to $OUTPUT"
  exit 0
fi

# Live mode: download the spec then generate.
echo "Fetching OpenAPI spec from $OPENAPI_URL ..."
if ! curl -sf "$OPENAPI_URL" -o "$SAVED_SPEC"; then
  echo "ERROR: Could not reach backend at $OPENAPI_URL"
  echo "       Make sure the backend is running, or use --from-file to regenerate"
  echo "       from a previously saved spec."
  exit 1
fi

echo "Generating TypeScript types ..."
npx openapi-typescript "$SAVED_SPEC" -o "$OUTPUT"

echo ""
echo "Generated API types at $OUTPUT"
echo "Saved raw OpenAPI spec at $SAVED_SPEC"
echo ""
echo "Next steps:"
echo "  1. Review the generated types in types/generated/api.ts"
echo "  2. Update types/api-helpers.ts if new schemas need friendly aliases"
echo "  3. Commit both files: types/generated/api.ts and types/generated/openapi.json"
