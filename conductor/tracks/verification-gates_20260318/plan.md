# Implementation Plan: Verification & Integration Quality Gates

**Track ID:** verification-gates_20260318
**Spec:** spec.md
**Created:** 2026-03-18
**Status:** [x] Complete

## Overview

5 phases implementing local developer quality gates: pre-commit hooks, pre-push gates, conductor track verification, API contract validation, and continuous-verify hardening.

## Phase 1: Pre-Commit Hooks (4 tasks)

### Tasks

- [x] 1.1: Add lint-staged, prettier, husky devDependencies to frontend/package.json
- [x] 1.2: Create frontend/.lintstagedrc.json — eslint --fix + prettier --write for TS/TSX, prettier for CSS/JSON/MD
- [x] 1.3: Create frontend/.husky/pre-commit calling npx lint-staged
- [x] 1.4: Create .pre-commit-config.yaml at repo root with ruff format --check + ruff lint + lint-staged local hook, install pre-commit in .venv

### Verification

- [x] pre-commit install succeeds, hooks registered for pre-commit and pre-push stages
- [x] lint-staged config validated

## Phase 2: Pre-Push Gate (3 tasks)

### Tasks

- [x] 2.1: Create scripts/pre-push-verify.sh wrapping loki-verify.sh --quick with SKIP_VERIFY escape hatch
- [x] 2.2: Add --help and --dry-run flags to pre-push-verify.sh
- [x] 2.3: Wire as git pre-push hook via pre-commit config (local hook, pre-push stage)

### Verification

- [x] --dry-run shows loki-verify.sh --quick would be called
- [x] --help prints usage information

## Phase 3: Conductor Track Completion Verifier (3 tasks)

### Tasks

- [x] 3.1: Create scripts/verify-track-completion.sh — per-phase checkbox counting, metadata validation
- [x] 3.2: Create scripts/verify-all-tracks.sh — iterate tracks.md, summary table output
- [x] 3.3: Add --help and --dry-run flags to both scripts

### Verification

- [x] Run against perf-optimization_20260316 — reports 20/20 complete, detects metadata mismatch
- [x] --help flags work on both scripts

## Phase 4: API Contract Validation (3 tasks)

### Tasks

- [x] 4.1: Create scripts/api-contract-check.py — Pydantic model parser (AST-based)
- [x] 4.2: Add TypeScript interface parser (regex-based) and type mapping logic
- [x] 4.3: Add --help, --dry-run, --exclude, --verbose flags

### Verification

- [x] --dry-run lists 75+ Python files and 27+ TypeScript files
- [x] Full scan: 126 Python models, 144 TS interfaces, 30 matched pairs, detects real mismatches

## Phase 5: Continuous-Verify Hook Hardening (4 tasks)

### Tasks

- [x] 5.1: Lower MIN_EDITS from 5 to 3, MIN_SECONDS from 120 to 60
- [x] 5.2: Remove cross-category requirement — any 3 edits trigger verification
- [x] 5.3: Add fallback to direct pytest/jest if loki-verify.sh missing
- [x] 5.4: Log verification results to .claude/logs/verification-summary.log

### Verification

- [x] Script structure validates (thresholds correct, fallback logic present, summary logging added)
- [x] Non-blocking behavior preserved (always exits 0)
