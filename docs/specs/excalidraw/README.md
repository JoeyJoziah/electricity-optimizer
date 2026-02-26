# Excalidraw Specification Suite

Complete TDD specifications for programmatic diagram generation, JSON validation, and layout algorithms in the Electricity Optimizer project.

## Overview

Three modular specifications covering the full Excalidraw diagram generation pipeline, from structured input to validated, positioned .excalidraw JSON output.

**Project**: Electricity Optimizer
**Target**: Next.js 14 + TypeScript + Excalidraw library
**Status**: Ready for Implementation
**Last Updated**: 2026-02-26

---

## Specification Documents

### [01_diagram_generation_spec.md](01_diagram_generation_spec.md)
**Programmatic diagram generation from structured input**

- **Focus**: Converting DiagramSpec (nodes + edges) into valid .excalidraw JSON
- **Key Functions**:
  - `generateDiagram()` — Main orchestrator (inputs → full document)
  - `calculateNodePositions()` — Grid positioning algorithm
  - `gridLayoutPositions()` — Balanced grid (cols = ceil(sqrt(N)))
  - `createArrowElement()` — Arrow creation with binding system
  - `calculateBinding()` — Focus calculation (-1 to 1 range)
  - `calculateElbowedPath()` — Right-angle routing (HVH/VHV)
  - `createTextElement()` — Text placement within containers
  - `registerBinding()` — Bidirectional binding creation
- **Edge Cases**: 0 elements, 1 element, 50+ elements, circular deps, self-loops, long labels
- **TDD Anchors**: 12 test functions covering generation, bindings, layout, text placement
- **Lines**: ~480 pseudocode

### [02_json_validation_spec.md](02_json_validation_spec.md)
**Schema validation, binding integrity, and data consistency checking**

- **Focus**: Ensuring .excalidraw JSON correctness before storage/display
- **Key Functions**:
  - `validateExcalidrawDocument()` — 4-level validation orchestrator
  - `validateStructure()` — Root document fields
  - `validateElements()` — Element array and type checking
  - `validateElementType()` — Type-specific property validation
  - `validateArrowElement()` — Arrow bindings and points
  - `validateTextElement()` — Text content and font properties
  - `validateBindings()` — Cross-element reference integrity
  - `findDuplicateIds()` — ID uniqueness detection
- **Edge Cases**: Null document, missing fields, broken bindings, duplicate IDs, invalid colors, out-of-range values
- **TDD Anchors**: 24 test functions covering structure, elements, bindings, colors, semantics
- **Lines**: ~460 pseudocode

### [03_layout_engine_spec.md](03_layout_engine_spec.md)
**Auto-layout with zero overlaps, arrow routing, and frame grouping**

- **Focus**: Positioning elements without collisions, routing arrows, grouping with frames
- **Key Functions**:
  - `layoutDiagram()` — Main layout orchestrator (explicit + implicit positioning)
  - `gridLayout()` — Classic grid (sqrt-based columns)
  - `compactGridLayout()` — Compact grid (dynamic columns, 50+ elements)
  - `hierarchicalLayout()` — Layer-based flow (LTR/TTB)
  - `routeArrow()` — Arrow path calculation
  - `routeElbowedPath()` — Rectilinear routing with obstacle avoidance
  - `applyFrameGrouping()` — Automatic frame creation and nesting
  - `resolveCollisions()` — Iterative overlap resolution
  - `calculateElementWidth()` — Text width estimation
  - Geometry helpers: `rectsOverlap()`, `centerOfElement()`, `calculateShift()`
- **Edge Cases**: Single column, single row, asymmetric groups, long labels, self-loops, circular deps, complex obstacles
- **TDD Anchors**: 18 test functions covering layouts, routing, frames, collisions, sizing
- **Lines**: ~450 pseudocode

---

## Architecture Diagram

```
Input (DiagramSpec)
    │
    ├─→ 01_diagram_generation
    │   └─→ Elements (positioned) + Bindings
    │
    ├─→ 03_layout_engine
    │   └─→ Elements (with routing) + Frames
    │
    └─→ 02_json_validation
        └─→ Valid .excalidraw Document
```

## Key Concepts

### Grid Layout Formula
```
n = number of elements
cols = ceil(sqrt(n))        // Balanced square-ish grid
rows = ceil(n / cols)       // Rows needed

Spacing:
  colSpacing = 250px        // Horizontal center-to-center
  rowSpacing = 150px        // Vertical center-to-center
  gutterSize = 50px         // Minimum edge-to-edge clearance
```

### Arrow Binding System
```
Arrow (required bidirectional binding):
  ├─ startBinding { elementId, focus: [-1, 1], gap: 1-5px }
  ├─ endBinding { elementId, focus: [-1, 1], gap: 1-5px }
  └─ points: [[0,0], [dx, dy]]  // Relative path

Element (receives binding reference):
  └─ boundElements: [{ id: arrowId, type: "arrow" }]
```

### Element Sizing
```
Width Calculation:
  explicit width provided   → use as-is
  text element             → estimateTextWidth() + padding
  arrow                    → 0 (use points for sizing)
  shape (rect, ellipse...) → type-specific default

Default Widths:  rectangle=160, ellipse=120, diamond=120
Default Heights: rectangle=80, ellipse=80, diamond=100, text=auto
```

### Validation Levels
```
Level 1 (Structure)   → Root fields, type checking
Level 2 (Elements)    → Type constraints, required properties
Level 3 (Bindings)    → Cross-element references, bidirectional consistency
Level 4 (Semantic)    → Domain logic (no duplicate IDs, frame nesting)
```

## Implementation Roadmap

### Phase 1: Core Generation
1. Implement `generateDiagram()` and `gridLayout()`
2. Create element builders (rectangle, ellipse, arrow, text)
3. Build arrow binding system (focus calculation, bidirectional refs)
4. Write 15 unit tests (empty, single, grid, arrows, text)

### Phase 2: Validation
1. Implement `validateExcalidrawDocument()` and 4-level validators
2. Add error accumulation and reporting
3. Create validation test suite (24 tests)
4. Integrate with generation pipeline (fail fast on invalid output)

### Phase 3: Layout Engine
1. Implement layout modes (grid, compact, hierarchical)
2. Add arrow routing (straight, elbowed, with obstacle avoidance)
3. Implement frame grouping and nesting
4. Build collision detection and resolution
5. Write 18 layout tests

### Phase 4: Integration & Testing
1. Wire generation → layout → validation pipeline
2. Test end-to-end with 50+ element diagrams
3. Verify Excalidraw rendering accuracy
4. Performance testing (target: < 1s for 100 elements)

---

## Test Summary

**Total Test Anchors**: 54 tests across 3 specifications

| Module | Tests | Focus |
|--------|-------|-------|
| `01_diagram_generation_spec.md` | 12 | Generation, positioning, bindings, text |
| `02_json_validation_spec.md` | 24 | Schema, elements, bindings, colors, semantics |
| `03_layout_engine_spec.md` | 18 | Layouts, routing, frames, collisions, sizing |

Each test anchor includes:
- Clear GIVEN/EXPECT structure
- Edge case coverage
- Measurable assertions
- Language-agnostic pseudocode (JS/Python/etc. implementation-ready)

---

## Quick Reference

### Common Edge Cases Across All Specs

| Case | Gen | Val | Layout | Notes |
|------|-----|-----|--------|-------|
| Zero elements | ✓ | ✓ | ✓ | Valid empty diagram |
| Single element | ✓ | ✓ | ✓ | At origin, no arrows |
| Duplicate IDs | ✗ (error) | ✗ (error) | N/A | Generation detects, validation confirms |
| Self-loop arrow | ✓ | ✓ | ✓ | Elbowed path around element |
| Long labels | ✓ | ✓ | ✓ | Width expansion, potential overlap |
| Circular dependencies | ✓ | ✓ | ✗ (fallback to grid) | Detected in hierarchical layout |
| Missing node reference | ✓ (graceful) | ✗ (error) | ✓ | Arrow created, binding invalid |
| Broken binding | N/A | ✗ (error) | N/A | Caught by validation |

---

## File Locations in Codebase

```
/Users/devinmcgrath/projects/electricity-optimizer/
├── docs/
│   └── specs/
│       └── excalidraw/
│           ├── README.md                          (this file)
│           ├── 01_diagram_generation_spec.md
│           ├── 02_json_validation_spec.md
│           └── 03_layout_engine_spec.md
├── frontend/
│   ├── components/dev/
│   │   ├── ExcalidrawWrapper.tsx                 (dynamic import)
│   │   ├── DiagramEditor.tsx                     (Ctrl+S save)
│   │   └── DiagramList.tsx                       (sidebar)
│   ├── lib/hooks/
│   │   └── useDiagrams.ts                        (React Query hooks)
│   ├── app/api/dev/diagrams/
│   │   ├── route.ts                              (GET/POST)
│   │   └── [name]/route.ts                       (GET/PUT)
│   └── app/(dev)/architecture/
│       └── page.tsx                              (Triple dev gate)
└── docs/
    └── architecture/
        └── *.excalidraw                          (Diagram storage)
```

---

## Implementation Checklist

- [ ] Read all three specifications end-to-end
- [ ] Understand grid layout formula and binding system
- [ ] Implement Phase 1 (generation)
  - [ ] `generateDiagram()` function
  - [ ] Element builders
  - [ ] Binding registration
  - [ ] 15 unit tests
- [ ] Implement Phase 2 (validation)
  - [ ] 4-level validators
  - [ ] Error accumulation
  - [ ] 24 unit tests
- [ ] Implement Phase 3 (layout)
  - [ ] Layout modes
  - [ ] Arrow routing
  - [ ] Frame grouping
  - [ ] Collision resolution
  - [ ] 18 unit tests
- [ ] Integration testing
  - [ ] End-to-end pipeline
  - [ ] Performance benchmarks
  - [ ] Excalidraw rendering verification

---

## Related Documentation

### Documentation Stack
- **[User Guide](../../excalidraw-agent-guide.md)** — How to use excalidraw-expert agent
- **[API Reference](../../excalidraw-reference.md)** — Components, hooks, API routes, schemas
- **[Agent Definition](/Users/devinmcgrath/.claude/agents/excalidraw-expert.md)** — Excalidraw expert agent specification

### Implementation Files
- **Architecture Page**: `frontend/app/(dev)/architecture/page.tsx` (triple dev-only gate)
- **API Routes**: `frontend/app/api/dev/diagrams/` (filesystem-backed GET/POST/PUT)
- **Component Library**: ExcalidrawWrapper, DiagramEditor, DiagramList in `frontend/components/dev/`
- **React Query Hooks**: `frontend/lib/hooks/useDiagrams.ts`
- **Test Suite**: 53 tests across 10 files in `frontend/__tests__/`

---

## Questions & Decisions

### Q: Why grid positioning formula?
**A**: Balanced sqrt-based grid provides:
- Even distribution (no long rows/columns)
- Deterministic positioning (reproducible layouts)
- O(n log n) performance (acceptable for typical diagrams)

### Q: How are bindings created?
**A**: Every arrow binding must be bidirectional:
1. Arrow element has `startBinding.elementId` + `endBinding.elementId`
2. Both target elements have arrow.id in their `boundElements` array
3. Validation ensures consistency in Level 3

### Q: What happens with circular dependencies?
**A**: Handled gracefully:
- Grid layout: No special handling (each edge processed independently)
- Hierarchical layout: Cycle detection, fallback to grid
- Arrow routing: Self-loops create elbowed paths around the element

### Q: How is text sized?
**A**: Estimation-based:
- `estimateTextWidth(text, fontSize)` = text.length × (fontSize × 0.6)
- Added to element dimensions if text is contained
- Layout engine re-estimates and adjusts during positioning

---

## Contact & Questions

This specification suite is designed for implementation by the Electricity Optimizer team. For questions or clarifications:
- Review the pseudocode carefully
- Check the TDD anchors for expected behavior
- Refer to excalidraw-expert.md agent for orchestration patterns

---

**Specification Suite Status**: Ready for Implementation
**Total Lines**: ~1,400 pseudocode across 3 files
**Test Coverage**: 54 test anchors, language-agnostic
**Last Validated**: 2026-02-26
