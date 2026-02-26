# Excalidraw Agent Usage Guide

Use the **excalidraw-expert** agent to create, edit, embed, and troubleshoot architectural diagrams programmatically.

## Overview

The excalidraw-expert agent specializes in:
- **Diagram generation**: Creating valid `.excalidraw` JSON with calculated positions, no overlaps, and correct arrow bindings
- **React/Next.js embedding**: Integrating Excalidraw with dynamic imports, hooks, and keyboard shortcuts
- **Architectural visualization**: Multi-layer system diagrams, data flow, dependencies, state machines
- **Schema validation**: Ensuring JSON complies with Excalidraw specification

**When to invoke**: You need a system diagram, integration in a new page, or arrow bindings fixed.

---

## Quick Start

### Generate a diagram

```bash
# Tell the agent to create an architecture diagram
Ask excalidraw-expert to create a diagram called "system-overview" with:
- 1 frontend box (light blue, #a5d8ff)
- 1 API service (light blue)
- 1 database (light green)
- arrows connecting frontend→API→database
```

The agent will save it to `/docs/architecture/system-overview.excalidraw`.

### Edit an existing diagram

```bash
# Read the current diagram and modify elements
excalidraw-expert: "Read docs/architecture/system-overview.excalidraw, add a message queue
element (light yellow) and connect API→queue→database with arrows"
```

### Embed in a new React component

```bash
# Ask the agent to set up a page using DiagramEditor
excalidraw-expert: "Create frontend/app/(dev)/mydiagrams/page.tsx that lists and edits
diagrams using ExcalidrawWrapper, DiagramEditor, and useDiagrams hooks"
```

---

## Agent Capabilities

### Element Types

| Type | Use Case | Example |
|------|----------|---------|
| `rectangle` | Services, modules, containers | Backend API, database, queue |
| `ellipse` | Start/end nodes, external systems | User, third-party API |
| `diamond` | Decision points, branching logic | "Payment approved?" |
| `arrow` | Data flow, dependencies, API calls | Request→response |
| `line` | Separators, group boundaries | Horizontal divider |
| `text` | Labels, annotations | Component names, notes |
| `frame` | Visual grouping | Layer grouping |

### Layout Algorithm

Positions are calculated to prevent overlaps:
- **Column spacing**: 250px between element centers horizontally
- **Row spacing**: 150px between element centers vertically
- **Gutter**: 50px minimum clearance between element edges
- **Arrow routing**: 60px horizontal clearance between columns
- **Grid pattern**: For N elements, use `cols = ceil(sqrt(N))`, arrange in grid

### Color Palette (Architecture)

| Element | Fill | Stroke | Use |
|---------|------|--------|-----|
| Service/API | `#a5d8ff` | `#1971c2` | Backend services |
| Database | `#b2f2bb` | `#2f9e44` | Persistent storage |
| External | `#ffec99` | `#f08c00` | 3rd-party systems |
| Error/Alert | `#ffc9c9` | `#e03131` | Failures, problems |
| ML/AI | `#d0bfff` | `#6741d9` | ML pipelines |

---

## Integration with electricity-optimizer

### Diagram Storage

All diagrams are stored as `.excalidraw` files in `/docs/architecture/`:

```
docs/architecture/
├── system-overview.excalidraw
├── data-flow.excalidraw
└── ml-pipeline.excalidraw
```

**Name validation**: `/^[a-zA-Z0-9_-]+$/` — letters, numbers, hyphens, underscores only.

### API Routes

The Next.js backend provides three endpoints:

**GET `/api/dev/diagrams`** — List all diagrams
```json
{
  "diagrams": [
    { "name": "system-overview", "updatedAt": "2026-02-26T10:00:00Z" }
  ]
}
```

**POST `/api/dev/diagrams`** — Create a new diagram
```json
// Request
{ "name": "new-diagram" }

// Response (201)
{ "name": "new-diagram", "created": true }
```

**GET `/api/dev/diagrams/[name]`** — Fetch diagram JSON
```json
{
  "name": "system-overview",
  "data": { "type": "excalidraw", "version": 2, ... }
}
```

**PUT `/api/dev/diagrams/[name]`** — Save changes
```json
// Request
{ "data": { "type": "excalidraw", "version": 2, ... } }

// Response
{ "name": "system-overview", "saved": true }
```

### Dev-Only Gate

Diagrams are only accessible in development mode:
- API routes check `NODE_ENV === 'development'` and return 404 in production
- `app/(dev)/` layout calls `notFound()` if not in dev mode
- Frontend components use `isDev()` check

### React Components

**ExcalidrawWrapper** (`frontend/components/dev/ExcalidrawWrapper.tsx`):
```tsx
<ExcalidrawWrapper
  initialData={diagramData}
  onChange={(elements, appState) => {
    // elements: readonly array of diagram elements
    // appState: { gridSize, viewBackgroundColor, ... }
  }}
  theme="light"
/>
```

**DiagramEditor** (`frontend/components/dev/DiagramEditor.tsx`):
- Wraps ExcalidrawWrapper with save UI
- Ctrl+S or Cmd+S keyboard shortcut
- Shows "Saved" indicator for 2 seconds
- Manages unsaved changes indicator

### React Query Hooks

In `frontend/lib/hooks/useDiagrams.ts`:

```tsx
// List all diagrams
const { data, isLoading } = useDiagramList()

// Load a single diagram
const { data: diagram } = useDiagram(selectedName)

// Save a diagram
const saveMutation = useSaveDiagram()
saveMutation.mutate({ name: 'system-overview', data: diagramData })

// Create a new diagram
const createMutation = useCreateDiagram()
createMutation.mutate('new-diagram')
```

### Architecture Page

At `frontend/app/(dev)/architecture/page.tsx`:
- Left sidebar (w-64) lists diagrams from `useDiagramList`
- Main area shows `DiagramEditor` with selected diagram
- "New Diagram" button triggers create mutation
- QueryClientProvider wraps both components

---

## .excalidraw JSON Schema

Minimal valid structure:

```json
{
  "type": "excalidraw",
  "version": 2,
  "source": "electricity-optimizer",
  "elements": [
    {
      "id": "rect-1",
      "type": "rectangle",
      "x": 100,
      "y": 100,
      "width": 160,
      "height": 80,
      "strokeColor": "#1971c2",
      "backgroundColor": "#a5d8ff",
      "fillStyle": "solid",
      "strokeWidth": 2,
      "roughness": 0,
      "opacity": 100,
      "groupIds": [],
      "frameId": null,
      "seed": 1234567890,
      "version": 1,
      "versionNonce": 9876543,
      "boundElements": [
        { "id": "text-label", "type": "text" },
        { "id": "arrow-1", "type": "arrow" }
      ]
    },
    {
      "id": "text-label",
      "type": "text",
      "x": 100,
      "y": 120,
      "width": 160,
      "height": 40,
      "text": "Backend API",
      "fontSize": 16,
      "fontFamily": 2,
      "textAlign": "center",
      "verticalAlign": "middle",
      "containerId": "rect-1",
      "seed": 1111111111,
      "version": 1,
      "versionNonce": 2222222,
      "boundElements": []
    },
    {
      "id": "rect-2",
      "type": "rectangle",
      "x": 350,
      "y": 100,
      "width": 160,
      "height": 80,
      "strokeColor": "#2f9e44",
      "backgroundColor": "#b2f2bb",
      "fillStyle": "solid",
      "strokeWidth": 2,
      "roughness": 0,
      "opacity": 100,
      "groupIds": [],
      "frameId": null,
      "seed": 3333333333,
      "version": 1,
      "versionNonce": 4444444,
      "boundElements": [
        { "id": "text-db", "type": "text" },
        { "id": "arrow-1", "type": "arrow" }
      ]
    },
    {
      "id": "text-db",
      "type": "text",
      "x": 350,
      "y": 120,
      "width": 160,
      "height": 40,
      "text": "PostgreSQL",
      "fontSize": 16,
      "fontFamily": 2,
      "textAlign": "center",
      "verticalAlign": "middle",
      "containerId": "rect-2",
      "seed": 5555555555,
      "version": 1,
      "versionNonce": 6666666,
      "boundElements": []
    },
    {
      "id": "arrow-1",
      "type": "arrow",
      "x": 260,
      "y": 140,
      "width": 90,
      "height": 0,
      "strokeColor": "#1e1e1e",
      "backgroundColor": "transparent",
      "fillStyle": "solid",
      "strokeWidth": 2,
      "roughness": 0,
      "opacity": 100,
      "groupIds": [],
      "seed": 7777777777,
      "version": 1,
      "versionNonce": 8888888,
      "points": [[0, 0], [90, 0]],
      "startBinding": {
        "elementId": "rect-1",
        "focus": 0.5,
        "gap": 1,
        "fixedPoint": null
      },
      "endBinding": {
        "elementId": "rect-2",
        "focus": -0.5,
        "gap": 1,
        "fixedPoint": null
      },
      "startArrowhead": null,
      "endArrowhead": "arrow",
      "elbowed": false,
      "boundElements": []
    }
  ],
  "appState": {
    "gridSize": null,
    "viewBackgroundColor": "#ffffff"
  },
  "files": {}
}
```

**Key fields**:
- `elements` array order = rendering order (later elements on top)
- Arrow bindings are **bidirectional**: both `startBinding`/`endBinding` AND parent element's `boundElements` must reference the arrow
- Text with `containerId` must be in parent's `boundElements`
- `seed` and `versionNonce` are random integers (prevent conflicts)

---

## Common Tasks

### Create Architecture Diagram

1. Define layers (frontend, API, DB, etc.)
2. List elements per layer with colors
3. Ask agent: "Create diagram 'my-arch' with X rectangles, Y arrows, layers positioned 250px apart"
4. Agent calculates positions, validates bindings, saves to `/docs/architecture/my-arch.excalidraw`
5. Verify in Excalidraw editor at `/architecture` (dev-only)

### Add Elements to Existing Diagram

1. Read the diagram JSON
2. Generate new element IDs, positions (avoid overlaps)
3. Update `boundElements` arrays for arrows
4. Use `useSaveDiagram()` or PUT to `/api/dev/diagrams/[name]`

### Fix Broken Arrow Bindings

Common issue: Arrow doesn't render or "floats" without connections.

**Check**:
```json
{
  "id": "arrow-1",
  "startBinding": { "elementId": "rect-1", ... },
  "endBinding": { "elementId": "rect-2", ... }
}
```

Then verify **both rectangles** have the arrow in `boundElements`:
```json
{
  "id": "rect-1",
  "boundElements": [
    { "id": "arrow-1", "type": "arrow" }
  ]
}

{
  "id": "rect-2",
  "boundElements": [
    { "id": "arrow-1", "type": "arrow" }
  ]
}
```

If missing, agent adds them back.

### Embed in a New Next.js Page

1. Create route: `frontend/app/(dev)/mypage/page.tsx`
2. Use pattern:
```tsx
'use client'
import { QueryClientProvider } from '@tanstack/react-query'
import { DiagramEditor } from '@/components/dev/DiagramEditor'
import { useDiagramList, useDiagram, useSaveDiagram } from '@/lib/hooks/useDiagrams'

export default function MyPage() {
  const [selected, setSelected] = useState<string | null>(null)
  const { data: list } = useDiagramList()
  const { data: diagram } = useDiagram(selected)
  const saveMutation = useSaveDiagram()

  return (
    <QueryClientProvider client={new QueryClient()}>
      {/* Sidebar with diagram list */}
      {/* Main editor with DiagramEditor */}
    </QueryClientProvider>
  )
}
```

3. Agent scaffolds the page with proper hooks, error handling, loading states

---

## Troubleshooting

### "SSR Error: `@excalidraw/excalidraw` not found"

**Cause**: ExcalidrawWrapper is not dynamic-imported with `ssr: false`.

**Fix**: Ensure wrapper uses:
```tsx
const Excalidraw = dynamic(
  () => import('@excalidraw/excalidraw').then((m) => m.Excalidraw),
  { ssr: false, loading: () => <Skeleton /> }
)
```

### Arrow doesn't render or is broken

**Cause**: Missing bidirectional binding or invalid element ID.

**Check**:
1. Arrow's `startBinding.elementId` and `endBinding.elementId` exist
2. Both target elements have arrow ID in their `boundElements` array
3. `points` array has at least 2 coordinates: `[[0,0], [dx, dy]]`

### Elements overlap or layout looks crowded

**Cause**: Manual positioning without spacing algorithm.

**Fix**: Use agent's layout algorithm:
- Column centers: `x = col * 250`
- Row centers: `y = row * 150`
- For N elements: `cols = ceil(sqrt(N))`
- Arrange in row-major order

### Diagram name rejected: "Invalid name"

**Cause**: Name contains spaces, special chars, or uppercase only.

**Valid**: `system-overview`, `data_flow_v2`, `MLPipeline`
**Invalid**: `System Overview`, `data flow!`, `123` (digits-only)

---

## Related Agents

- **frontend-developer**: Enhance ExcalidrawWrapper, add dark mode toggle, export buttons
- **nextjs-developer**: Create new diagram pages, API route patterns, query client setup
- **architect-reviewer**: Review system diagrams for accuracy and clarity
- **backend-architect**: Design data flow and service diagrams
- **technical-writer**: Add diagram descriptions and alt-text for accessibility

---

## Further Reading

- [Excalidraw Docs](https://excalidraw.com/) — Full library reference
- `/frontend/app/(dev)/architecture/page.tsx` — Live editor page
- `/frontend/components/dev/` — ExcalidrawWrapper, DiagramEditor source
- `/frontend/lib/hooks/useDiagrams.ts` — React Query integration

## Related Documentation

- **[excalidraw-reference.md](excalidraw-reference.md)** — Complete API & component reference
- **[specs/excalidraw/README.md](specs/excalidraw/README.md)** — TDD specifications (generation, validation, layout)
- **[Agent Definition](/Users/devinmcgrath/.claude/agents/excalidraw-expert.md)** — Excalidraw expert agent specification
