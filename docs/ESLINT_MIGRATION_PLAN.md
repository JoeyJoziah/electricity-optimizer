# ESLint Migration Plan: v8 → v9 Flat Config

**Status**: Planned (not started)
**Priority**: P2 — non-blocking, quality improvement
**Created**: 2026-03-17

## Current State

- ESLint **8.56.0** with legacy `.eslintrc.json`
- `eslint-config-next` 16.1.6 (transitively brings `typescript-eslint` v8.46+)
- No explicit `@typescript-eslint/*` packages in `package.json` (resolved via eslint-config-next)
- 5 custom rules + 1 test override in `.eslintrc.json`
- `.npmrc` has `legacy-peer-deps=true` for ESLint 8 compat with eslint-config-next 16.x

## Target State

- ESLint **9.x** with flat config (`eslint.config.mjs`)
- `eslint-config-next` compatible version (16.x already supports flat config)
- Explicit `typescript-eslint` v8 in `package.json`
- Remove `legacy-peer-deps=true` from `.npmrc` if no longer needed

## Why Not ESLint 10?

ESLint 10 (released early 2026) drops `.eslintrc` support entirely. Migrating to v9 flat config first is the safe path — v10 upgrade becomes trivial afterward.

## Migration Steps

### Phase 1: Flat Config Migration (estimate: 2-3 hours)

1. Create `eslint.config.mjs` equivalent of current `.eslintrc.json`:
   ```js
   import nextConfig from 'eslint-config-next/flat'
   import tseslint from 'typescript-eslint'

   export default [
     ...nextConfig,
     ...tseslint.configs.recommended,
     {
       rules: {
         '@typescript-eslint/no-explicit-any': 'warn',
         '@typescript-eslint/no-unused-vars': ['error', {
           argsIgnorePattern: '^_',
           varsIgnorePattern: '^_',
         }],
         'no-console': ['warn', { allow: ['error', 'warn'] }],
         'react/jsx-no-target-blank': 'error',
         'prefer-const': 'error',
       },
     },
     {
       files: ['**/__tests__/**', '**/*.test.{ts,tsx}', '**/*.spec.{ts,tsx}'],
       rules: {
         '@typescript-eslint/no-explicit-any': 'off',
         'no-console': 'off',
       },
     },
   ]
   ```
2. Install explicit deps: `npm i -D typescript-eslint@^8 eslint@^9`
3. Run `npx eslint .` — fix any new warnings/errors
4. Delete `.eslintrc.json`
5. Update CI lint step if needed

### Phase 2: Cleanup (estimate: 1 hour)

1. Check if `legacy-peer-deps=true` can be removed from `.npmrc`
2. Resolve remaining 10 TS errors (separate from ESLint but related cleanup)
3. Consider adding `eslint-plugin-testing-library` for test file linting

### Phase 3: ESLint 10 Upgrade (future, after v9 stable)

1. `npm i -D eslint@^10` — should work with flat config already in place
2. Verify all plugins compatible with v10

## Risks

- **Low**: eslint-config-next flat config support is mature in v16
- **Low**: Custom rules are simple, direct translation to flat config
- **Medium**: Some ESLint plugins may need updates for v9 compat
- `legacy-peer-deps` removal may surface other dep conflicts

## Dependencies

- None — can be done independently
- Recommended: do after all current audit remediation work is complete

## Conductor Track

Create via: `/conductor:new-track` → type: chore → "ESLint v9 flat config migration"
