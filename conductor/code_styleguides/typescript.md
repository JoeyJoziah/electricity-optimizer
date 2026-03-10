# TypeScript Style Guide

Based on existing ESLint config (`.eslintrc.json`) and project conventions.

## Extends

- `next/core-web-vitals`
- `@typescript-eslint` plugin

## Core Rules

### Type Safety

- **No explicit `any`**: Use `unknown` or proper types. ESLint warns on `any` (relaxed in test files).
- **No unused variables**: Error-level. Prefix intentionally unused params/vars with `_`.
- **Prefer `const`**: Always use `const` for variables that aren't reassigned.

```typescript
// Good
const userId = session.user.id;
const _unusedParam = "intentional";

// Bad
let userId = session.user.id;  // never reassigned
const data: any = fetchData();  // use proper type
```

### Imports

- Use named imports over default imports where possible
- Group: React/Next.js > external libs > internal modules > types
- No circular imports

```typescript
import { useState, useEffect } from "react";
import { useQuery } from "@tanstack/react-query";

import { fetchAlerts } from "@/lib/api/alerts";
import type { Alert } from "@/types";
```

### Components

- Use function declarations for page components, arrow functions for small helpers
- Props interfaces named `{ComponentName}Props`
- Colocate types with components unless shared

```typescript
interface AlertFormProps {
  onSubmit: (data: AlertConfig) => void;
  initialValues?: Partial<AlertConfig>;
}

export function AlertForm({ onSubmit, initialValues }: AlertFormProps) {
  // ...
}
```

### Console Usage

- `console.error` and `console.warn` allowed
- `console.log` triggers a warning (disabled in test files)
- Never use `console.log` in production code

### Security

- `react/jsx-no-target-blank`: Error-level. Always use `rel="noopener noreferrer"` with `target="_blank"`.

## Naming Conventions

| Entity | Convention | Example |
|--------|-----------|---------|
| Components | PascalCase | `AlertForm`, `DashboardContent` |
| Hooks | camelCase, `use` prefix | `useAlerts`, `useConnections` |
| Utils/helpers | camelCase | `isSafeRedirect`, `formatPrice` |
| Constants | UPPER_SNAKE_CASE | `API_BASE_URL`, `MAX_RETRIES` |
| Types/Interfaces | PascalCase | `AlertConfig`, `SessionData` |
| Files (components) | PascalCase | `AlertForm.tsx` |
| Files (utils) | camelCase | `alerts.ts`, `useAlerts.ts` |

## Testing

- Test files: `__tests__/` directories or `*.test.{ts,tsx}`
- `any` allowed in test files
- `console.log` allowed in test files
- Use `jest-axe` for accessibility assertions
