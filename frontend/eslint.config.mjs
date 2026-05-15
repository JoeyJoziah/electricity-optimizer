// ESLint 9 flat config for frontend.
//
// Replaces .eslintrc.json (legacy) after Next 16 removed the `next lint`
// subcommand and eslint-config-next 16 became flat-config-only. See
// conductor track ci-frontend-lint-workflow_20260515 for the full migration.
//
// eslint-config-next/core-web-vitals exports a native flat-config array.
// The @typescript-eslint plugin is registered within a TS-scoped block
// inside that config, so our overrides that reference @typescript-eslint/*
// rules must also be TS-scoped (flat config requires the plugin to be
// available in the same config object where its rules are referenced).

import nextCoreWebVitals from 'eslint-config-next/core-web-vitals'
import tsParser from '@typescript-eslint/parser'
import tsPlugin from '@typescript-eslint/eslint-plugin'

export default [
  {
    ignores: [
      '.next/**',
      'out/**',
      'node_modules/**',
      'public/**',
      'storybook-static/**',
      'coverage/**',
      'playwright-report/**',
      'test-results/**',
      'next-env.d.ts',
    ],
  },
  ...nextCoreWebVitals,
  // Project-wide custom rules (apply to JS + TS).
  {
    rules: {
      'no-console': ['warn', { allow: ['error', 'warn'] }],
      'react/jsx-no-target-blank': 'error',
      'prefer-const': 'error',
    },
  },
  // TypeScript-only custom rules. @typescript-eslint plugin must be
  // registered in the same config object where its rules are referenced.
  {
    files: ['**/*.{ts,tsx,mts,cts}'],
    languageOptions: {
      parser: tsParser,
    },
    plugins: {
      '@typescript-eslint': tsPlugin,
    },
    rules: {
      '@typescript-eslint/no-explicit-any': 'warn',
      '@typescript-eslint/no-unused-vars': [
        'error',
        {
          argsIgnorePattern: '^_',
          varsIgnorePattern: '^_',
        },
      ],
    },
  },
  // Test files: relax some rules.
  {
    files: ['**/__tests__/**', '**/*.test.{ts,tsx}', '**/*.spec.{ts,tsx}'],
    rules: {
      '@typescript-eslint/no-explicit-any': 'off',
      'no-console': 'off',
    },
  },
]
