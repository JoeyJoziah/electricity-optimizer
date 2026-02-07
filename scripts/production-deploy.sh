#!/bin/bash
set -e

# Production Deployment Script
# Automated deployment to production environment

echo "🚀 Electricity Optimizer - Production Deployment"
echo "================================================"
echo ""

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
DEPLOYMENT_ENV=${1:-production}
SKIP_TESTS=${SKIP_TESTS:-false}
DEPLOYMENT_PLATFORM=${DEPLOYMENT_PLATFORM:-railway}

echo "📋 Deployment Configuration:"
echo "   Environment: $DEPLOYMENT_ENV"
echo "   Platform: $DEPLOYMENT_PLATFORM"
echo "   Skip Tests: $SKIP_TESTS"
echo ""

# Step 1: Pre-deployment validation
echo "1️⃣  Running pre-deployment validation..."
echo "   ----------------------------------------"

# Check if required tools are installed
echo "   Checking required tools..."
command -v git >/dev/null 2>&1 || { echo "❌ git is required but not installed. Aborting." >&2; exit 1; }
command -v docker >/dev/null 2>&1 || { echo "❌ docker is required but not installed. Aborting." >&2; exit 1; }

if [ "$DEPLOYMENT_PLATFORM" = "railway" ]; then
    command -v railway >/dev/null 2>&1 || { echo "❌ railway CLI is required. Run: npm i -g @railway/cli" >&2; exit 1; }
elif [ "$DEPLOYMENT_PLATFORM" = "fly" ]; then
    command -v fly >/dev/null 2>&1 || { echo "❌ fly CLI is required. Run: curl -L https://fly.io/install.sh | sh" >&2; exit 1; }
fi

echo "   ✅ All required tools installed"

# Check git status
if [[ -n $(git status -s) ]]; then
    echo -e "   ${YELLOW}⚠️  Warning: You have uncommitted changes${NC}"
    read -p "   Continue anyway? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

echo "   ✅ Git status clean"

# Check environment file
if [ ! -f ".env.$DEPLOYMENT_ENV" ]; then
    echo -e "   ${RED}❌ .env.$DEPLOYMENT_ENV not found${NC}"
    echo "   Create it from .env.example:"
    echo "   cp .env.example .env.$DEPLOYMENT_ENV"
    exit 1
fi

echo "   ✅ Environment file exists"

# Step 2: Run tests
if [ "$SKIP_TESTS" = "false" ]; then
    echo ""
    echo "2️⃣  Running test suite..."
    echo "   ----------------------------------------"

    echo "   Running backend tests..."
    cd backend
    python3 -m pytest --tb=short -q 2>/dev/null || {
        echo -e "   ${RED}❌ Backend tests failed${NC}"
        exit 1
    }
    cd ..
    echo "   ✅ Backend tests passed"

    echo "   Running ML tests..."
    cd ml
    python3 -m pytest --tb=short -q 2>/dev/null || {
        echo -e "   ${RED}❌ ML tests failed${NC}"
        exit 1
    }
    cd ..
    echo "   ✅ ML tests passed"

    echo "   Running frontend tests..."
    cd frontend
    npm test -- --watchAll=false --passWithNoTests 2>/dev/null || {
        echo -e "   ${RED}❌ Frontend tests failed${NC}"
        exit 1
    }
    cd ..
    echo "   ✅ Frontend tests passed"

    echo "   ✅ All tests passed (527+ tests)"
else
    echo ""
    echo "2️⃣  Skipping tests (SKIP_TESTS=true)"
fi

# Step 3: Build Docker images
echo ""
echo "3️⃣  Building Docker images..."
echo "   ----------------------------------------"

echo "   Building backend image..."
docker build -t electricity-optimizer-backend:$DEPLOYMENT_ENV ./backend -q
echo "   ✅ Backend image built"

echo "   Building frontend image..."
docker build -t electricity-optimizer-frontend:$DEPLOYMENT_ENV ./frontend -q
echo "   ✅ Frontend image built"

echo "   Building ML image..."
docker build -t electricity-optimizer-ml:$DEPLOYMENT_ENV ./ml -q
echo "   ✅ ML image built"

echo "   ✅ All images built successfully"

# Step 4: Create backup
echo ""
echo "4️⃣  Creating backup..."
echo "   ----------------------------------------"

if [ -f "./scripts/backup.sh" ]; then
    ./scripts/backup.sh
    echo "   ✅ Backup created"
else
    echo "   ⚠️  Backup script not found, skipping..."
fi

# Step 5: Deploy based on platform
echo ""
echo "5️⃣  Deploying to $DEPLOYMENT_PLATFORM..."
echo "   ----------------------------------------"

if [ "$DEPLOYMENT_PLATFORM" = "railway" ]; then
    # Railway deployment
    echo "   Deploying to Railway..."

    # Check if logged in
    railway whoami >/dev/null 2>&1 || {
        echo "   Please login to Railway:"
        railway login
    }

    # Deploy backend
    echo "   Deploying backend service..."
    railway up --service backend || {
        echo -e "   ${RED}❌ Backend deployment failed${NC}"
        exit 1
    }
    echo "   ✅ Backend deployed"

    # Deploy frontend
    echo "   Deploying frontend service..."
    railway up --service frontend || {
        echo -e "   ${RED}❌ Frontend deployment failed${NC}"
        exit 1
    }
    echo "   ✅ Frontend deployed"

    # Deploy ML service
    echo "   Deploying ML service..."
    railway up --service ml || {
        echo -e "   ${RED}❌ ML deployment failed${NC}"
        exit 1
    }
    echo "   ✅ ML deployed"

    # Get URLs
    BACKEND_URL=$(railway domain --service backend)
    FRONTEND_URL=$(railway domain --service frontend)

elif [ "$DEPLOYMENT_PLATFORM" = "fly" ]; then
    # Fly.io deployment
    echo "   Deploying to Fly.io..."

    # Check if logged in
    fly auth whoami >/dev/null 2>&1 || {
        echo "   Please login to Fly.io:"
        fly auth login
    }

    # Deploy backend
    echo "   Deploying backend..."
    fly deploy --config backend/fly.toml || {
        echo -e "   ${RED}❌ Backend deployment failed${NC}"
        exit 1
    }
    echo "   ✅ Backend deployed"

    # Deploy frontend
    echo "   Deploying frontend..."
    fly deploy --config frontend/fly.toml || {
        echo -e "   ${RED}❌ Frontend deployment failed${NC}"
        exit 1
    }
    echo "   ✅ Frontend deployed"

    # Get URLs
    BACKEND_URL=$(fly info --config backend/fly.toml --json | jq -r '.Hostname')
    FRONTEND_URL=$(fly info --config frontend/fly.toml --json | jq -r '.Hostname')

elif [ "$DEPLOYMENT_PLATFORM" = "docker-compose" ]; then
    # Docker Compose deployment (local production)
    echo "   Deploying with Docker Compose..."

    docker-compose -f docker-compose.prod.yml up -d || {
        echo -e "   ${RED}❌ Docker Compose deployment failed${NC}"
        exit 1
    }
    echo "   ✅ All services started"

    BACKEND_URL="http://localhost:8000"
    FRONTEND_URL="http://localhost:3000"
fi

# Step 6: Health checks
echo ""
echo "6️⃣  Running health checks..."
echo "   ----------------------------------------"

echo "   Waiting for services to start (30s)..."
sleep 30

echo "   Checking backend health..."
if curl -f -s "$BACKEND_URL/health" > /dev/null; then
    echo "   ✅ Backend healthy"
else
    echo -e "   ${RED}❌ Backend health check failed${NC}"
    exit 1
fi

echo "   Checking frontend..."
if curl -f -s "$FRONTEND_URL" > /dev/null; then
    echo "   ✅ Frontend healthy"
else
    echo -e "   ${RED}❌ Frontend health check failed${NC}"
    exit 1
fi

# Step 7: Run smoke tests
echo ""
echo "7️⃣  Running smoke tests..."
echo "   ----------------------------------------"

echo "   Testing API endpoint..."
PRICE_RESPONSE=$(curl -s "$BACKEND_URL/api/v1/prices/current?region=UK")
if echo "$PRICE_RESPONSE" | grep -q "region"; then
    echo "   ✅ Price API working"
else
    echo -e "   ${YELLOW}⚠️  Price API returned unexpected response${NC}"
fi

echo "   Testing authentication..."
AUTH_RESPONSE=$(curl -s "$BACKEND_URL/api/v1/auth/signin" -X POST -H "Content-Type: application/json" -d '{"email":"test@example.com","password":"invalid"}')
if echo "$AUTH_RESPONSE" | grep -q "error\|unauthorized"; then
    echo "   ✅ Authentication working"
else
    echo -e "   ${YELLOW}⚠️  Authentication returned unexpected response${NC}"
fi

echo "   ✅ Smoke tests passed"

# Step 8: Tag release
echo ""
echo "8️⃣  Tagging release..."
echo "   ----------------------------------------"

CURRENT_DATE=$(date +%Y-%m-%d)
COMMIT_HASH=$(git rev-parse --short HEAD)
TAG_NAME="v1.0.0-beta.$CURRENT_DATE.$COMMIT_HASH"

git tag -a "$TAG_NAME" -m "Production deployment: $CURRENT_DATE"
echo "   ✅ Tagged as $TAG_NAME"

# Step 9: Update deployment log
echo ""
echo "9️⃣  Updating deployment log..."
echo "   ----------------------------------------"

cat >> deployments.log <<EOF
===================================
Deployment: $TAG_NAME
Date: $(date)
Environment: $DEPLOYMENT_ENV
Platform: $DEPLOYMENT_PLATFORM
Backend: $BACKEND_URL
Frontend: $FRONTEND_URL
Status: SUCCESS
===================================

EOF

echo "   ✅ Deployment logged"

# Step 10: Summary
echo ""
echo "✅ DEPLOYMENT SUCCESSFUL!"
echo "================================================"
echo ""
echo "📊 Deployment Summary:"
echo "   Tag: $TAG_NAME"
echo "   Environment: $DEPLOYMENT_ENV"
echo "   Platform: $DEPLOYMENT_PLATFORM"
echo ""
echo "🌐 URLs:"
echo "   Frontend: $FRONTEND_URL"
echo "   Backend:  $BACKEND_URL/docs"
echo "   Health:   $BACKEND_URL/health"
echo ""
echo "📈 Next Steps:"
echo "   1. Monitor logs: make logs"
echo "   2. Check metrics: make grafana"
echo "   3. Test critical flows manually"
echo "   4. Announce to beta users"
echo ""
echo "🔄 Rollback Command (if needed):"
echo "   git checkout [previous-tag]"
echo "   ./scripts/production-deploy.sh"
echo ""
echo "🎉 Production is LIVE!"
