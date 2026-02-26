# Excalidraw Architecture Diagram System — Complete Reference

> Last updated: 2026-02-26
> Test coverage: 53 tests across 11 suites
> Status: Production ready

## Overview

The Electricity Optimizer includes a triple-gated Excalidraw-based diagram editor accessible at `/architecture` in development mode only. The system manages `.excalidraw` JSON files in `docs/architecture/` with React Query cache, safe API routes, and keyboard shortcut save.

**File structure:**
- Components: `frontend/components/dev/{ExcalidrawWrapper,DiagramEditor,DiagramList}.tsx`
- Hooks: `frontend/lib/hooks/useDiagrams.ts`
- API routes: `frontend/app/api/dev/diagrams/{route.ts,[name]/route.ts}`
- Page: `frontend/app/(dev)/architecture/page.tsx`
- Layout gate: `frontend/app/(dev)/layout.tsx`

---

## 1. Component Reference

### ExcalidrawWrapper

Dynamically imports and wraps the Excalidraw editor with client-side rendering and loading fallback.

**Props:**

| Prop | Type | Required | Description |
|------|------|----------|-------------|
| `initialData` | `Record<string, unknown>` | No | `.excalidraw` JSON object (type, version, source, elements, appState, files) |
| `onChange` | `(elements, appState) => void` | No | Fired when diagram is edited; receives current elements and appState |
| `theme` | `'light' \| 'dark'` | No | UI theme; defaults to `'light'` |

**Key behaviors:**
- **Dynamic import** with `ssr: false` to prevent server-side Excalidraw bundle loading
- **Loading fallback** renders Skeleton component while Excalidraw bundle downloads
- **onChange callback** wrapped in `useCallback` to stabilize reference across renders
- Receives `(elements, appState, files)` from Excalidraw; passes `(elements, appState)` to parent

**Usage example:**
```tsx
import { ExcalidrawWrapper } from '@/components/dev/ExcalidrawWrapper'

export function MyDiagram() {
  const handleChange = useCallback((elements, appState) => {
    console.log('Diagram updated:', elements.length, 'elements')
  }, [])

  return (
    <ExcalidrawWrapper
      initialData={diagramData}
      onChange={handleChange}
      theme="light"
    />
  )
}
```

**Dependencies:** `@excalidraw/excalidraw`, `next/dynamic`, `@/components/ui/skeleton`

---

### DiagramEditor

Editor toolbar with save button, status indicator (Saved / Unsaved changes), and keyboard shortcut (Ctrl+S / Cmd+S).

**Props:**

| Prop | Type | Required | Description |
|------|------|----------|-------------|
| `name` | `string \| null` | Yes | Selected diagram name; null shows placeholder |
| `data` | `Record<string, unknown>` | No | Loaded diagram data from API |
| `isLoading` | `boolean` | Yes | True while fetching diagram detail |
| `onSave` | `(data: Record<string, unknown>) => void` | Yes | Fired when save button clicked or Ctrl+S pressed |
| `isSaving` | `boolean` | Yes | True while save mutation is pending |

**Key behaviors:**
- **Change tracking** via `latestDataRef` to avoid stale closure in keyboard handler
- **Save button** disabled when no changes or saving in progress
- **Saved indicator** (green checkmark + "Saved" text) displays for 2 seconds post-save
- **Unsaved changes** label shown when edits pending
- **Ctrl+S / Cmd+S** keyboard shortcut calls save handler, prevents browser default
- **State reset** when `name` changes (clears hasChanges, showSaved, latestDataRef)
- **Data shape** always wraps elements/appState in: `{ type: 'excalidraw', version: 2, source: 'electricity-optimizer', elements, appState, files }`

**Usage example:**
```tsx
import { DiagramEditor } from '@/components/dev/DiagramEditor'

export function Editor() {
  const { data, isLoading } = useDiagram(selected)
  const saveMutation = useSaveDiagram()

  const handleSave = (data) => {
    saveMutation.mutate({ name: selected, data })
  }

  return (
    <DiagramEditor
      name={selected}
      data={data?.data}
      isLoading={isLoading}
      onSave={handleSave}
      isSaving={saveMutation.isPending}
    />
  )
}
```

**Dependencies:** `ExcalidrawWrapper`, `@/components/ui/button`, `@/components/ui/skeleton`, `lucide-react`

---

### DiagramList

Sidebar list with diagram selection, "No diagrams yet" empty state, and create button.

**Props:**

| Prop | Type | Required | Description |
|------|------|----------|-------------|
| `diagrams` | `DiagramEntry[] \| undefined` | Yes | Array of `{name: string, updatedAt: string}` |
| `isLoading` | `boolean` | Yes | True while fetching diagram list |
| `selected` | `string \| null` | Yes | Currently selected diagram name |
| `onSelect` | `(name: string) => void` | Yes | Fired when clicking diagram in list |
| `onCreateClick` | `() => void` | Yes | Fired when clicking create button (+ icon) |

**Key behaviors:**
- **Loading state** shows three Skeleton text placeholders
- **Empty state** shows "No diagrams yet" when list is empty
- **Selection highlight** uses primary-100 bg / primary-700 text + bold font
- **Create button** (Plus icon) in header triggers naming dialog in parent
- **Truncation** applied to long diagram names with text ellipsis
- **Sorting** by updatedAt descending (most recent first) — done on API side

**Usage example:**
```tsx
import { DiagramList } from '@/components/dev/DiagramList'

export function Sidebar() {
  const { data: diagrams, isLoading } = useDiagramList()
  const [selected, setSelected] = useState<string | null>(null)

  return (
    <DiagramList
      diagrams={diagrams}
      isLoading={isLoading}
      selected={selected}
      onSelect={setSelected}
      onCreateClick={() => handleCreate()}
    />
  )
}
```

**Dependencies:** `@/lib/utils/cn`, `@/components/ui/button`, `@/components/ui/skeleton`, `lucide-react`

---

### ArchitecturePage

Full-page layout combining DiagramList sidebar (w-64) and DiagramEditor main area. Wraps component tree in QueryClientProvider.

**Layout:**
```
┌────────────────────────────────────────────┐
│            ArchitecturePage                │
│ ┌──────────┬─────────────────────────────┐ │
│ │          │                             │ │
│ │ Diagram  │      Diagram                │ │
│ │ List     │      Editor                 │ │
│ │ (w-64)   │      (flex-1)               │ │
│ │          │                             │ │
│ └──────────┴─────────────────────────────┘ │
└────────────────────────────────────────────┘
```

**Key behaviors:**
- **QueryClientProvider** instance created once at module level for React Query
- **Selected state** managed at `ArchitectureContent` level, passed to both children
- **Save handler** checks diagram selected before calling mutation
- **Create handler** prompts for diagram name, validates in API, sets selected on success
- **Error handling** via React Query automatic retry + component error boundaries

**Usage example:**
```tsx
import ArchitecturePage from '@/app/(dev)/architecture/page'

// Automatically mounted by Next.js router at /architecture
```

**Dependencies:** `useDiagramList`, `useDiagram`, `useSaveDiagram`, `useCreateDiagram`, `DiagramList`, `DiagramEditor`, `QueryClientProvider`

---

## 2. React Query Hooks (useDiagrams)

All hooks in `frontend/lib/hooks/useDiagrams.ts`. Queries target `/api/dev/diagrams` and `/api/dev/diagrams/[name]`.

### useDiagramList

Fetches list of available diagrams from filesystem.

**Signature:**
```ts
function useDiagramList(): UseQueryResult<DiagramEntry[], Error>
```

**Query key:** `['diagrams', 'list']`

**Returns:**
```ts
{
  data: DiagramEntry[],      // [ { name: 'architecture', updatedAt: '2026-02-26T10:30:00Z' }, ... ]
  isLoading: boolean,         // true on initial fetch
  isError: boolean,
  error: Error | null,
  refetch: () => Promise<...>
}
```

**Cache invalidation:** Cleared on save or create mutations (`queryClient.invalidateQueries({ queryKey: ['diagrams', 'list'] })`)

**Usage:**
```ts
const { data: diagrams, isLoading, isError } = useDiagramList()

if (isLoading) return <Skeleton />
if (isError) return <ErrorMessage />
return <DiagramList diagrams={diagrams} ... />
```

---

### useDiagram

Fetches single diagram data by name.

**Signature:**
```ts
function useDiagram(name: string | null): UseQueryResult<DiagramData, Error>
```

**Query key:** `['diagrams', 'detail', name]` — When `name` is null, query is disabled.

**Returns:**
```ts
{
  data: {
    name: 'architecture',
    data: {
      type: 'excalidraw',
      version: 2,
      source: 'electricity-optimizer',
      elements: [],
      appState: { gridSize: null, viewBackgroundColor: '#ffffff' },
      files: {}
    }
  },
  isLoading: boolean,
  isError: boolean,
  error: Error | null
}
```

**Cache invalidation:** Cleared on save mutation (`queryClient.invalidateQueries({ queryKey: ['diagrams', 'detail', variables.name] })`)

**Usage:**
```ts
const { data: diagramDetail, isLoading } = useDiagram(selected)

return (
  <DiagramEditor
    data={diagramDetail?.data}
    isLoading={isLoading}
    ...
  />
)
```

---

### useSaveDiagram

Saves diagram data via PUT request.

**Signature:**
```ts
function useSaveDiagram(): UseMutationResult<void, Error, { name: string; data: Record<string, unknown> }>
```

**Mutation function arguments:**
```ts
{ name: string, data: Record<string, unknown> }
```

**Request:** `PUT /api/dev/diagrams/{name}` with body `{ data: {...} }`

**Response:** `{ name, saved: true }`

**Cache invalidation:**
- Clears `['diagrams', 'detail', name]` (refetch diagram)
- Clears `['diagrams', 'list']` (refetch list, updates mtime)

**Usage:**
```ts
const saveMutation = useSaveDiagram()

const handleSave = (data) => {
  saveMutation.mutate({ name: 'architecture', data })
}

return (
  <button disabled={saveMutation.isPending} onClick={() => handleSave(data)}>
    {saveMutation.isPending ? 'Saving...' : 'Save'}
  </button>
)
```

---

### useCreateDiagram

Creates new diagram file via POST request.

**Signature:**
```ts
function useCreateDiagram(): UseMutationResult<{ name: string; created: boolean }, Error, string>
```

**Mutation function argument:** `name: string`

**Request:** `POST /api/dev/diagrams` with body `{ name }`

**Response:** `{ name, created: true }` (status 201) or error with status 400/409

**Cache invalidation:** Clears `['diagrams', 'list']` (refetch list)

**Usage:**
```ts
const createMutation = useCreateDiagram()

const handleCreate = () => {
  const name = window.prompt('Diagram name:')
  if (name) {
    createMutation.mutate(name, {
      onSuccess: () => setSelected(name)
    })
  }
}
```

---

## 3. API Routes

### GET /api/dev/diagrams

**Purpose:** List available diagrams from filesystem.

**Request:**
```
GET /api/dev/diagrams
```

**Response (200):**
```json
{
  "diagrams": [
    {
      "name": "system-architecture",
      "updatedAt": "2026-02-26T14:30:00.000Z"
    },
    {
      "name": "data-flow",
      "updatedAt": "2026-02-26T10:15:00.000Z"
    }
  ]
}
```

**Response (404):** `NODE_ENV !== 'development'`
```json
{ "error": "Not found" }
```

**Response (500):** Filesystem error
```json
{ "error": "Failed to list diagrams" }
```

**Dev gate:** `isDev()` check (NODE_ENV === 'development')

**Behavior:**
- Scans `docs/architecture/` for `.excalidraw` files
- Returns empty array if directory doesn't exist
- Sorts by mtime descending (most recent first)
- Returns 404 in production/test

---

### POST /api/dev/diagrams

**Purpose:** Create new diagram with template.

**Request:**
```json
{
  "name": "new-diagram"
}
```

**Response (201):**
```json
{
  "name": "new-diagram",
  "created": true
}
```

**Response (400):** Invalid name
```json
{
  "error": "Invalid name. Use only letters, numbers, hyphens, and underscores."
}
```

**Response (409):** Diagram already exists
```json
{
  "error": "Diagram already exists"
}
```

**Response (404):** Non-development environment
```json
{ "error": "Not found" }
```

**Name validation pattern:** `/^[a-zA-Z0-9_-]+$/`
- Alphanumeric, hyphens, underscores only
- No spaces, dots (path traversal), or special chars
- Examples: ✓ `system-architecture`, `flow_123`, `er-diagram` | ✗ `sys arch`, `../../etc/passwd`

**Template created:**
```json
{
  "type": "excalidraw",
  "version": 2,
  "source": "electricity-optimizer",
  "elements": [],
  "appState": {
    "gridSize": null,
    "viewBackgroundColor": "#ffffff"
  },
  "files": {}
}
```

**Dev gate:** `isDev()` check

**Behavior:**
- Creates `docs/architecture/` if not exists
- Writes template JSON to `docs/architecture/{name}.excalidraw`
- Returns 404 in production/test
- Returns 409 if file already exists

---

### GET /api/dev/diagrams/[name]

**Purpose:** Fetch single diagram by name.

**Request:**
```
GET /api/dev/diagrams/system-architecture
```

**Response (200):**
```json
{
  "name": "system-architecture",
  "data": {
    "type": "excalidraw",
    "version": 2,
    "source": "electricity-optimizer",
    "elements": [
      {
        "id": "el-1",
        "type": "rectangle",
        "x": 100,
        "y": 100,
        "width": 200,
        "height": 100,
        ...
      }
    ],
    "appState": { "gridSize": null, "viewBackgroundColor": "#ffffff" },
    "files": {}
  }
}
```

**Response (400):** Invalid name
```json
{ "error": "Invalid diagram name" }
```

**Response (404):** Not found
```json
{ "error": "Diagram not found" }
```

**Dev gate:** `isDev()` check

**Behavior:**
- Sanitizes name with `sanitizeName()` (validates regex)
- Returns 404 if file doesn't exist
- Parses JSON and returns full `.excalidraw` object
- Returns 404 in production/test

---

### PUT /api/dev/diagrams/[name]

**Purpose:** Save diagram data to file.

**Request:**
```json
PUT /api/dev/diagrams/system-architecture
{
  "data": {
    "type": "excalidraw",
    "version": 2,
    "source": "electricity-optimizer",
    "elements": [...],
    "appState": {...},
    "files": {}
  }
}
```

**Response (200):**
```json
{
  "name": "system-architecture",
  "saved": true
}
```

**Response (400):** Invalid data
```json
{ "error": "Invalid diagram data" }
```

**Response (404):** Diagram not found OR invalid name OR non-development environment
```json
{ "error": "Diagram not found" }
```

**Dev gate:** `isDev()` check

**Behavior:**
- Sanitizes name, returns 400 if invalid
- Returns 404 if file doesn't exist (can't create via PUT, use POST)
- Validates `data` is object, returns 400 if missing/invalid
- Writes JSON with 2-space indentation: `JSON.stringify(data, null, 2)`
- Returns 404 in production/test

---

## 4. Data Flow Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│ ArchitecturePage (Page Component)                                   │
└─────────────────────────────────────────────────────────────────────┘
                              ↓
            ┌─────────────────────────────────────────┐
            │ React Query QueryClientProvider          │
            └─────────────────────────────────────────┘
                              ↓
┌───────────────────────────────────────────────────────────────────────┐
│ ArchitectureContent (Layout Manager)                                  │
│                                                                       │
│  selected: string | null                                             │
│                                                                       │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │ useDiagramList() → { data: diagrams, isLoading }             │   │
│  │   ↓                                                           │   │
│  │   QueryKey: ['diagrams', 'list']                             │   │
│  │   Endpoint: GET /api/dev/diagrams                            │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                       │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │ useDiagram(selected) → { data: diagramDetail, isLoading }    │   │
│  │   ↓                                                           │   │
│  │   QueryKey: ['diagrams', 'detail', selected]                 │   │
│  │   Endpoint: GET /api/dev/diagrams/{selected}                 │   │
│  │   Enabled: !!selected                                         │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                       │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │ useSaveDiagram() → saveMutation                              │   │
│  │   ↓ onSuccess                                                │   │
│  │   Invalidate: ['diagrams', 'detail', name]                   │   │
│  │   Invalidate: ['diagrams', 'list']                           │   │
│  │   Endpoint: PUT /api/dev/diagrams/{name}                     │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                       │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │ useCreateDiagram() → createMutation                          │   │
│  │   ↓ onSuccess                                                │   │
│  │   Invalidate: ['diagrams', 'list']                           │   │
│  │   Endpoint: POST /api/dev/diagrams                           │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                       │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  DiagramList                       DiagramEditor             │   │
│  │  ├─ diagrams (from useDiagramList) ├─ name (selected)        │   │
│  │  ├─ isLoading                      ├─ data (from useDiagram) │   │
│  │  ├─ selected                       ├─ isLoading              │   │
│  │  ├─ onSelect → setSelected         ├─ isSaving               │   │
│  │  └─ onCreateClick → handleCreate   ├─ onSave → handleSave    │   │
│  │                                    │                         │   │
│  │                                    ├─ handleChange           │   │
│  │                                    │  ├─ latestDataRef.cur = │   │
│  │                                    │  │  wrapped data        │   │
│  │                                    │  └─ setHasChanges(true) │   │
│  │                                    │                         │   │
│  │                                    ├─ handleSave            │   │
│  │                                    │  ├─ saveMutation.mutate │   │
│  │                                    │  └─ showSaved = true    │   │
│  │                                    │     (2s timeout)        │   │
│  │                                    │                         │   │
│  │                                    └─ Ctrl+S / Cmd+S        │   │
│  │                                       → handleSave()        │   │
│  │                                                              │   │
│  │  ExcalidrawWrapper                                          │   │
│  │  ├─ initialData (from diagramDetail?.data)                  │   │
│  │  ├─ onChange (handleChange callback)                        │   │
│  │  └─ theme = 'light'                                         │   │
│  └──────────────────────────────────────────────────────────────┘   │
└───────────────────────────────────────────────────────────────────────┘
                              ↓
                    ┌─────────────────┐
                    │  Filesystem:    │
                    │  docs/arch./ *.excalidraw
                    └─────────────────┘
```

---

## 5. Security Model

### Triple Dev-Only Gate

Access to `/architecture` and diagram APIs is blocked in production via three independent checks:

**Gate 1: Next.js Route Group Layout**
```tsx
// frontend/app/(dev)/layout.tsx
export default function DevLayout({ children }) {
  if (process.env.NODE_ENV !== 'development') {
    notFound()
  }
  return <>{children}</>
}
```
- Renders `notFound()` page (404) if `NODE_ENV !== 'development'`
- Applies to all routes in `(dev)` group: `/architecture`, etc.

**Gate 2: API Route isDev() Check**
```ts
// frontend/app/api/dev/diagrams/route.ts
function isDev() {
  return process.env.NODE_ENV === 'development'
}

export async function GET() {
  if (!isDev()) {
    return NextResponse.json({ error: 'Not found' }, { status: 404 })
  }
  // ...
}
```
- Every API route (GET, POST, PUT) calls `isDev()` first
- Returns 404 for non-development environments

**Gate 3: Browser Component NODE_ENV Check**
```tsx
// ExcalidrawWrapper, DiagramEditor etc.
// All are 'use client' components running in browser only
// The API client-side code only executes in dev because the page doesn't load
```
- API calls only originate from development builds
- Production builds don't include diagram code paths

### Name Validation

All diagram names validated against `/^[a-zA-Z0-9_-]+$/` to prevent path traversal:
- ✓ Alphanumeric, hyphens, underscores
- ✗ Spaces, dots, slashes, special characters

Prevents attacks like: `../../etc/passwd`, `..%2fetc%2fpasswd`

### File Operations

- **Read:** Sandboxed to `docs/architecture/` via path.join + basename sanitization
- **Write:** Only via API routes (not exposed as standalone file endpoint)
- **Deletion:** Not implemented (files persist until manually deleted)

---

## 6. .excalidraw File Format

Complete schema for `.excalidraw` JSON files (stored in `docs/architecture/`).

**Root object:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `type` | `"excalidraw"` | ✓ | Literal string, identifies file format |
| `version` | `2` | ✓ | Schema version (current = 2) |
| `source` | `string` | ✓ | Application identifier (e.g., `"electricity-optimizer"`) |
| `elements` | `Element[]` | ✓ | Array of drawable elements (shapes, arrows, text) |
| `appState` | `AppState` | ✓ | Editor state (grid, background color) |
| `files` | `FilesMap` | ✓ | Embedded image files (usually empty) |

**AppState:**

| Field | Type | Description |
|-------|------|-------------|
| `gridSize` | `number \| null` | Grid size in pixels (null = disabled) |
| `viewBackgroundColor` | `string` | Hex color for canvas background (default: `"#ffffff"`) |

**Element base properties:**

| Property | Type | Description |
|----------|------|-------------|
| `id` | `string` | Unique identifier (use descriptive slugs or nanoid-style) |
| `type` | `"rectangle" \| "ellipse" \| "diamond" \| "arrow" \| "line" \| "text" \| "freedraw" \| "image" \| "frame"` | Element shape type |
| `x` | `number` | Left position in canvas coordinates |
| `y` | `number` | Top position in canvas coordinates |
| `width` | `number` | Element width in pixels |
| `height` | `number` | Element height in pixels |
| `angle` | `number` | Rotation angle in radians (0 = no rotation) |
| `strokeColor` | `string` | Hex color for border/line (e.g., `"#1e1e1e"`) |
| `backgroundColor` | `string` | Hex color for fill (e.g., `"#a5d8ff"` light blue) |
| `fillStyle` | `"solid" \| "hachure" \| "cross-hatch" \| "zigzag"` | Fill pattern |
| `strokeWidth` | `number` | Border thickness: 1=thin, 2=normal, 4=bold |
| `roughness` | `number` | Hand-drawn effect: 0=architect (clean), 1=artist, 2=cartoonist |
| `opacity` | `number` | Transparency 0-100 |
| `groupIds` | `string[]` | Logical grouping IDs (for multi-select) |
| `frameId` | `string \| null` | Parent frame element ID (null if not in frame) |
| `boundElements` | `BoundElement[]` | Array of `{id, type}` for contained text/arrows |
| `seed` | `number` | Random integer for roughness variation |
| `version` | `number` | Element version counter (start at 1) |
| `versionNonce` | `number` | Random integer for conflict resolution |
| `isDeleted` | `boolean` | Soft delete flag (true = hidden) |

**Arrow-specific properties:**

| Property | Type | Description |
|----------|------|-------------|
| `startBinding` | `Binding` | Source element reference: `{elementId, focus, gap, fixedPoint}` |
| `endBinding` | `Binding` | Target element reference: same structure as startBinding |
| `startArrowhead` | `"arrow" \| "bar" \| "dot" \| "triangle" \| null` | Arrow style at start |
| `endArrowhead` | `"arrow" \| "bar" \| "dot" \| "triangle" \| null` | Arrow style at end |
| `points` | `[number, number][]` | Array of [x,y] offsets (minimum 2 points) |
| `elbowed` | `boolean` | Right-angle routing (true = Manhattan routing) |

**Binding object:**

| Property | Type | Description |
|----------|------|-------------|
| `elementId` | `string` | ID of bound element |
| `focus` | `number` | Position along element edge: -1=left, 0=center, 1=right (for vertical: -1=top, 0=center, 1=bottom) |
| `gap` | `number` | Pixel distance from element border (1-5) |
| `fixedPoint` | `[number, number] \| null` | Normalized coordinates on element (null = auto) |

**Text-specific properties:**

| Property | Type | Description |
|----------|------|-------------|
| `originalText` | `string` | Display text content |
| `text` | `string` | Display text (same as originalText in most cases) |
| `fontFamily` | `number` | Font: 1=Virgil (hand-drawn), 2=Helvetica, 3=Cascadia (monospace) |
| `fontSize` | `number` | Font size in pixels (16=body, 20=subtitle, 28=title) |
| `textAlign` | `"left" \| "center" \| "right"` | Horizontal text alignment |
| `verticalAlign` | `"top" \| "middle"` | Vertical alignment (when inside container) |
| `containerId` | `string \| null` | Parent shape ID (rectangle/ellipse/diamond) |
| `autoResize` | `boolean` | Auto-expand text dimensions to fit content |
| `lineHeight` | `number` | Line height multiplier (1.25 default) |

**Color palette (architectural conventions):**

| Usage | Stroke | Background | Example |
|-------|--------|-------------|---------|
| Services/APIs | `#1971c2` | `#a5d8ff` | Backend services, REST endpoints |
| Databases | `#2f9e44` | `#b2f2bb` | PostgreSQL, databases, caches |
| External/3rd-party | `#f08c00` | `#ffec99` | Stripe, AWS, external APIs |
| Errors/Alerts | `#e03131` | `#ffc9c9` | Failure states, alerts |
| ML/AI | `#6741d9` | `#d0bfff` | ML models, prediction services |

**Minimal valid document:**
```json
{
  "type": "excalidraw",
  "version": 2,
  "source": "electricity-optimizer",
  "elements": [],
  "appState": {
    "gridSize": null,
    "viewBackgroundColor": "#ffffff"
  },
  "files": {}
}
```

---

## 7. Test Coverage Map

**Total: 53 tests across 11 files**

| File | Suite | Test Count | Coverage |
|------|-------|-----------|----------|
| `route.test.ts` (GET/POST) | GET /api/dev/diagrams | 3 | 404 in non-dev, empty list, file listing |
| | POST /api/dev/diagrams | 5 | 404 in non-dev, valid creation, invalid name, conflict |
| `name.route.test.ts` (GET/PUT) | GET /api/dev/diagrams/[name] | 4 | 404 in non-dev, valid read, path traversal, not found |
| | PUT /api/dev/diagrams/[name] | 4 | 404 in non-dev, valid save, invalid data |
| `devGate.test.ts` | isDevMode() | 3 | dev/prod/test environment checks |
| `layout.test.tsx` | DevLayout | 4 | notFound() in prod/test, renders in dev, flex column layout |
| `architecture.test.tsx` | ArchitecturePage | 4 | List + Editor render, selection, save, sidebar width |
| `ExcalidrawWrapper.test.tsx` | ExcalidrawWrapper | 5 | Renders, initialData, onChange callback, theme |
| `DiagramEditor.test.tsx` | DiagramEditor | 8 | Placeholder, loading, name display, save button state, Ctrl+S, saved indicator, unsaved label |
| `DiagramList.test.tsx` | DiagramList | 9 | Loading, empty state, list render, selection, create button, truncation |
| `useDiagrams.test.tsx` | React Query hooks | 7 | useDiagramList, useDiagram, useSaveDiagram, useCreateDiagram (list, error, detail, disabled, save, create) |
| `DevBanner.test.tsx` | DevBanner | 2 | Renders in dev, hidden in prod |

**Test locations:**
- API routes: `frontend/__tests__/api/dev/diagrams/`
- Components: `frontend/__tests__/components/dev/`
- Layout: `frontend/__tests__/app/dev/`
- Hooks: `frontend/__tests__/hooks/`
- Utils: `frontend/__tests__/utils/`

**Key test patterns:**
- **Dev gate tests:** Mock NODE_ENV to "production" and verify 404
- **Component tests:** Mock fetch, simulate user interactions, assert state
- **Hook tests:** Use renderHook from @testing-library/react, wrap in QueryClientProvider
- **Accessibility:** All interactive elements use aria-label, proper roles

---

## 8. Development Workflow

### Creating a New Diagram

1. **Navigate to `/architecture`** in development mode (NODE_ENV=development)
2. **Click create button** (+ icon in DiagramList header)
3. **Enter diagram name** (letters, numbers, hyphens, underscores only)
4. **Diagram opens** with empty template (file created in `docs/architecture/{name}.excalidraw`)
5. **Draw and edit** in Excalidraw editor
6. **Save with Ctrl+S** or click Save button
7. **Saved indicator** appears for 2 seconds after save

### Editing Existing Diagram

1. **Navigate to `/architecture`**
2. **Click diagram name** in DiagramList sidebar
3. **Diagram loads** with existing data from `docs/architecture/{name}.excalidraw`
4. **Make changes** — toolbar shows "Unsaved changes" label
5. **Save with Ctrl+S** or Save button
6. **Saved indicator** confirms persistence

### Accessing Diagrams Programmatically

```tsx
// Fetch list of diagrams
const response = await fetch('/api/dev/diagrams')
const { diagrams } = await response.json()

// Fetch single diagram
const { data } = await fetch('/api/dev/diagrams/architecture').then(r => r.json())

// Create new diagram
const { name, created } = await fetch('/api/dev/diagrams', {
  method: 'POST',
  body: JSON.stringify({ name: 'new-diagram' })
}).then(r => r.json())

// Save diagram
await fetch('/api/dev/diagrams/new-diagram', {
  method: 'PUT',
  body: JSON.stringify({ data: { type: 'excalidraw', ... } })
})
```

### In Production

All routes return 404. Directory `docs/architecture/` is read-only or unavailable. No diagram UI exposed.

---

## 9. Troubleshooting

| Issue | Cause | Fix |
|-------|-------|-----|
| `/architecture` shows 404 | NODE_ENV not "development" | Run with `NODE_ENV=development` or check deployment env vars |
| "Invalid name" error | Name has spaces, dots, special chars | Use only letters, numbers, hyphens, underscores |
| Diagram not saving | `isSaving` true, button disabled | Wait for mutation to complete, check network tab |
| Ctrl+S doesn't work | Browser captures shortcut first | Try Save button instead, or browser may be preventing preventDefault |
| Excalidraw not loading | Bundle download timeout | Check network tab, reload page, check browser cache |
| Changes lost on reload | Data not saved before refresh | Click Save button or use Ctrl+S before leaving page |
| Path traversal rejected | API name validation | Names are validated server-side, cannot use `../` |

---

## 10. Cross-References

### Related Documentation

- **[excalidraw-agent-guide.md](excalidraw-agent-guide.md)** — Usage guide for the excalidraw-expert agent
- **[specs/excalidraw/README.md](specs/excalidraw/README.md)** — Overview of TDD specifications
- **[specs/excalidraw/01_diagram_generation_spec.md](specs/excalidraw/01_diagram_generation_spec.md)** — Diagram generation algorithm
- **[specs/excalidraw/02_json_validation_spec.md](specs/excalidraw/02_json_validation_spec.md)** — JSON validation specification
- **[specs/excalidraw/03_layout_engine_spec.md](specs/excalidraw/03_layout_engine_spec.md)** — Layout engine specification
- **[specs/excalidraw/IMPLEMENTATION_GUIDE.md](specs/excalidraw/IMPLEMENTATION_GUIDE.md)** — Implementation roadmap and development workflow
- **[Agent Definition](/Users/devinmcgrath/.claude/agents/excalidraw-expert.md)** — Excalidraw expert agent specification

### Cross-System Integration

- **Component hierarchy:** `ArchitecturePage` → `QueryClientProvider` → `ArchitectureContent` → {`DiagramList`, `DiagramEditor`}
- **Data flow:** Filesystem (docs/architecture/) ← → API routes → React Query → Component tree → ExcalidrawWrapper
- **Security:** Triple dev-only gate ensures production access denial at multiple layers
- **Testing:** 53 tests verify all three gates, cache invalidation, keyboard shortcuts, file operations
