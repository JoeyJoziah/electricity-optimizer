# =============================================================================
# Electricity Optimizer - Makefile
# =============================================================================
# Common commands for development, testing, and deployment
# Usage: make [command]
# =============================================================================

.PHONY: help build up down restart logs test lint format clean deploy backup restore health

# Default target
.DEFAULT_GOAL := help

# Colors for output
BLUE := \033[0;34m
GREEN := \033[0;32m
YELLOW := \033[1;33m
NC := \033[0m # No Color

# =============================================================================
# Help
# =============================================================================

help: ## Show this help message
	@echo ""
	@echo "$(BLUE)Electricity Optimizer - Available Commands$(NC)"
	@echo "============================================="
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(GREEN)%-15s$(NC) %s\n", $$1, $$2}'
	@echo ""

# =============================================================================
# Development
# =============================================================================

build: ## Build all Docker images
	@echo "$(BLUE)Building Docker images...$(NC)"
	docker compose build

build-prod: ## Build production Docker images
	@echo "$(BLUE)Building production Docker images...$(NC)"
	docker compose -f docker-compose.prod.yml build

up: ## Start all services in development mode
	@echo "$(BLUE)Starting development services...$(NC)"
	docker compose up -d
	@echo "$(GREEN)Services started!$(NC)"
	@echo "  Frontend:   http://localhost:3000"
	@echo "  Backend:    http://localhost:8000"
	@echo "  Grafana:    http://localhost:3001"

up-prod: ## Start all services in production mode
	@echo "$(BLUE)Starting production services...$(NC)"
	docker compose -f docker-compose.prod.yml up -d

down: ## Stop all services
	@echo "$(BLUE)Stopping all services...$(NC)"
	docker compose down

down-prod: ## Stop production services
	@echo "$(BLUE)Stopping production services...$(NC)"
	docker compose -f docker-compose.prod.yml down

restart: down up ## Restart all services

logs: ## View logs for all services
	docker compose logs -f

logs-backend: ## View backend logs
	docker compose logs -f backend

logs-frontend: ## View frontend logs
	docker compose logs -f frontend

# =============================================================================
# Testing
# =============================================================================

test: ## Run all tests
	@echo "$(BLUE)Running all tests...$(NC)"
	@$(MAKE) test-backend
	@$(MAKE) test-ml
	@$(MAKE) test-frontend
	@echo "$(GREEN)All tests completed!$(NC)"

test-backend: ## Run backend tests
	@echo "$(BLUE)Running backend tests...$(NC)"
	cd backend && pytest --cov=. --cov-report=term-missing -v

test-ml: ## Run ML tests
	@echo "$(BLUE)Running ML tests...$(NC)"
	cd ml && pytest --cov=. --cov-report=term-missing -v

test-frontend: ## Run frontend tests
	@echo "$(BLUE)Running frontend tests...$(NC)"
	cd frontend && npm test -- --coverage --watchAll=false

test-e2e: ## Run end-to-end tests
	@echo "$(BLUE)Running E2E tests...$(NC)"
	cd frontend && npx playwright test

test-docker: ## Run tests in Docker containers
	@echo "$(BLUE)Running tests in Docker...$(NC)"
	docker compose run --rm backend pytest --cov=. --cov-report=term-missing

# =============================================================================
# Code Quality
# =============================================================================

lint: ## Run linters on all code
	@echo "$(BLUE)Running linters...$(NC)"
	@$(MAKE) lint-backend
	@$(MAKE) lint-frontend
	@echo "$(GREEN)Linting completed!$(NC)"

lint-backend: ## Lint backend code
	@echo "$(BLUE)Linting backend...$(NC)"
	cd backend && ruff check . && mypy . --ignore-missing-imports

lint-frontend: ## Lint frontend code
	@echo "$(BLUE)Linting frontend...$(NC)"
	cd frontend && npm run lint

format: ## Format all code
	@echo "$(BLUE)Formatting code...$(NC)"
	@$(MAKE) format-backend
	@$(MAKE) format-frontend
	@echo "$(GREEN)Formatting completed!$(NC)"

format-backend: ## Format backend code
	@echo "$(BLUE)Formatting backend...$(NC)"
	cd backend && black . && isort .

format-frontend: ## Format frontend code
	@echo "$(BLUE)Formatting frontend...$(NC)"
	cd frontend && npm run format || npx prettier --write .

security-scan: ## Run security scans
	@echo "$(BLUE)Running security scans...$(NC)"
	cd backend && bandit -r . -f json -o bandit-report.json || true
	cd frontend && npm audit || true

# =============================================================================
# Database
# =============================================================================

db-migrate: ## Run database migrations
	@echo "$(BLUE)Running database migrations...$(NC)"
	docker compose exec backend alembic upgrade head

db-rollback: ## Rollback last database migration
	@echo "$(BLUE)Rolling back last migration...$(NC)"
	docker compose exec backend alembic downgrade -1

db-shell: ## Open PostgreSQL shell
	docker compose exec timescaledb psql -U postgres -d electricity

redis-shell: ## Open Redis CLI
	docker compose exec redis redis-cli -a $$REDIS_PASSWORD

# =============================================================================
# Deployment
# =============================================================================

deploy: ## Deploy to development environment
	@echo "$(BLUE)Deploying to development...$(NC)"
	./scripts/deploy.sh development

deploy-staging: ## Deploy to staging environment
	@echo "$(BLUE)Deploying to staging...$(NC)"
	./scripts/deploy.sh staging

deploy-prod: ## Deploy to production environment
	@echo "$(YELLOW)WARNING: Deploying to PRODUCTION$(NC)"
	./scripts/deploy.sh production

# =============================================================================
# Backup & Restore
# =============================================================================

backup: ## Create database backup
	@echo "$(BLUE)Creating backup...$(NC)"
	./scripts/backup.sh

backup-full: ## Create full backup (all databases)
	@echo "$(BLUE)Creating full backup...$(NC)"
	./scripts/backup.sh --full

restore: ## Restore from latest backup
	@echo "$(YELLOW)WARNING: This will overwrite existing data!$(NC)"
	./scripts/restore.sh

# =============================================================================
# Monitoring
# =============================================================================

health: ## Run health checks on all services
	@echo "$(BLUE)Running health checks...$(NC)"
	./scripts/health-check.sh

metrics: ## Open Prometheus metrics UI
	@echo "$(BLUE)Opening Prometheus...$(NC)"
	open http://localhost:9090

grafana: ## Open Grafana dashboard
	@echo "$(BLUE)Opening Grafana...$(NC)"
	open http://localhost:3001

# =============================================================================
# Cleanup
# =============================================================================

clean: ## Remove all containers, volumes, and images
	@echo "$(YELLOW)WARNING: This will remove ALL data!$(NC)"
	@read -p "Are you sure? (yes/no): " confirm && \
	if [ "$$confirm" = "yes" ]; then \
		docker compose down -v --rmi all; \
		docker system prune -af; \
		echo "$(GREEN)Cleanup completed!$(NC)"; \
	else \
		echo "$(BLUE)Cleanup cancelled$(NC)"; \
	fi

clean-cache: ## Clean Python and npm caches
	@echo "$(BLUE)Cleaning caches...$(NC)"
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "node_modules" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".next" -exec rm -rf {} + 2>/dev/null || true
	@echo "$(GREEN)Caches cleaned!$(NC)"

# =============================================================================
# Development Utilities
# =============================================================================

shell-backend: ## Open shell in backend container
	docker compose exec backend bash

shell-frontend: ## Open shell in frontend container
	docker compose exec frontend sh

install: ## Install all dependencies locally
	@echo "$(BLUE)Installing dependencies...$(NC)"
	cd backend && pip install -r requirements.txt
	cd frontend && npm install
	cd ml && pip install -r requirements.txt
	@echo "$(GREEN)Dependencies installed!$(NC)"

docs: ## Open API documentation
	@echo "$(BLUE)Opening API docs...$(NC)"
	open http://localhost:8000/docs

# =============================================================================
# CI/CD Utilities
# =============================================================================

ci-test: ## Run CI test suite (used in GitHub Actions)
	@echo "$(BLUE)Running CI tests...$(NC)"
	$(MAKE) lint
	$(MAKE) test
	$(MAKE) security-scan

ci-build: ## Build and push Docker images (used in CI)
	@echo "$(BLUE)Building for CI...$(NC)"
	docker compose -f docker-compose.prod.yml build
	docker compose -f docker-compose.prod.yml push

# =============================================================================
# Quick Start
# =============================================================================

setup: ## First-time setup (copy env, build, start)
	@echo "$(BLUE)Setting up Electricity Optimizer...$(NC)"
	@if [ ! -f .env ]; then \
		cp .env.example .env; \
		echo "$(YELLOW)Created .env file - please configure it!$(NC)"; \
	fi
	$(MAKE) build
	$(MAKE) up
	@echo ""
	@echo "$(GREEN)Setup complete!$(NC)"
	@echo "Please configure your .env file with real values."
	@echo ""
	$(MAKE) health
