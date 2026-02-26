# Excalidraw Implementation Guide

Practical guide for implementing the three SPARC specifications with focus on module integration, testing strategy, and development workflow.

---

## Module Dependencies

```
03_layout_engine
    └─ 01_diagram_generation
        └─ 02_json_validation
            └─ Serialized .excalidraw file
```

### Dependency Details

**Generation → Validation**: Generator must produce JSON that passes all validators
- Spec 01 output type: `ExcalidrawDocument`
- Spec 02 input type: `ExcalidrawDocument`
- Validation MUST succeed before persisting to file

**Generation/Layout → Validation**: Both feed the validator
- Spec 01: Element creation (positions, bindings, text)
- Spec 03: Element positioning refinement, arrow routing
- Spec 02: Final integrity check before output

---

## Implementation Order

### Step 1: Implement Core Generation (Spec 01)
**Estimated**: 8-12 hours

```typescript
// Minimal viable implementation
class DiagramGenerator {
  generateDiagram(spec: DiagramSpec): ExcalidrawDocument {
    // Phase 1: Position nodes in grid
    const positions = this.calculateNodePositions(spec.nodes, spec.config)

    // Phase 2: Create arrow elements with bindings
    const arrowElements = this.createArrows(spec.edges, positions)

    // Phase 3: Create text labels
    const textElements = this.createTexts(spec.nodes, positions)

    // Combine and return
    return {
      type: "excalidraw",
      version: 2,
      source: "electricity-optimizer",
      elements: [...nodeElements, ...arrowElements, ...textElements],
      appState: { gridSize: null, viewBackgroundColor: "#ffffff" },
      files: {}
    }
  }

  // Core functions to implement
  calculateNodePositions(nodes, config): Map<string, Position> { }
  createArrows(edges, positions): ExcalidrawArrow[] { }
  createTexts(nodes, positions): ExcalidrawText[] { }
}
```

**Tests to Write** (15 total):
```
✓ test_empty_diagram()
✓ test_single_element()
✓ test_grid_layout_9_elements()
✓ test_arrow_bindings_bidirectional()
✓ test_text_in_container()
✓ test_no_overlaps_grid_layout()
✓ test_elbowed_arrow_routing()
✓ test_binding_focus_calculation()
✓ test_duplicate_node_ids_throws()
✓ test_invalid_node_type_throws()
✓ test_self_loop_creates_arrow()
✓ test_missing_target_node_graceful()
✓ test_large_grid_50_elements()
✓ test_all_elements_have_unique_ids()
✓ test_all_elements_have_valid_seed()
```

**Deliverable**: Generation module passes 15 unit tests, produces valid (but unvalidated) JSON

---

### Step 2: Implement Validation (Spec 02)
**Estimated**: 6-10 hours

```typescript
// Validation orchestrator
class DiagramValidator {
  validate(document: Record<string, any>): ValidationResult {
    const errors = []
    const warnings = []

    // Level 1: Structure
    errors.push(...this.validateStructure(document))
    if (errors.length > 0) return { isValid: false, errors, warnings }

    // Level 2: Elements
    errors.push(...this.validateElements(document.elements))

    // Level 3: Bindings
    errors.push(...this.validateBindings(document.elements))

    // Level 4: Semantics
    warnings.push(...this.validateSemantics(document.elements))

    return {
      isValid: errors.length === 0,
      errors,
      warnings
    }
  }

  // Core functions to implement
  validateStructure(doc): ValidationError[] { }
  validateElements(elements): ValidationError[] { }
  validateBindings(elements): ValidationError[] { }
  validateSemantics(elements): Warning[] { }
}
```

**Tests to Write** (24 total):
```
Structure (8):
✓ test_null_document_rejected()
✓ test_missing_type_field()
✓ test_invalid_type_value()
✓ test_valid_schema()
✓ test_missing_version()
✓ test_missing_elements()
✓ test_missing_appState()
✓ test_missing_files()

Elements (8):
✓ test_duplicate_element_ids()
✓ test_invalid_element_type()
✓ test_missing_element_positions()
✓ test_negative_dimensions()
✓ test_out_of_range_seed()
✓ test_invalid_opacity()
✓ test_invalid_strokeWidth()
✓ test_invalid_roughness()

Bindings (5):
✓ test_broken_arrow_binding()
✓ test_orphaned_bound_element()
✓ test_bidirectional_consistency()
✓ test_text_container_reference()
✓ test_frame_child_validation()

Colors & Types (3):
✓ test_valid_hex_colors()
✓ test_invalid_hex_colors()
✓ test_arrow_missing_bindings()
```

**Integration**: Run validator on Spec 01 output, fix any issues in generator

**Deliverable**: Validator passes 24 tests, Gen+Validation pipeline works end-to-end

---

### Step 3: Implement Layout Engine (Spec 03)
**Estimated**: 10-14 hours

```typescript
// Layout orchestrator
class LayoutEngine {
  layout(
    elements: DiagramElement[],
    config: LayoutConfig
  ): PositionedElement[] {
    // Separate explicit and implicit
    const explicit = elements.filter(e => e.x !== null && e.y !== null)
    const implicit = elements.filter(e => e.x === null || e.y === null)

    // Layout implicit elements
    let positioned = [...explicit]
    if (config.layoutMode === 'grid') {
      positioned.push(...this.gridLayout(implicit, config))
    } else if (config.layoutMode === 'hierarchical') {
      positioned.push(...this.hierarchicalLayout(implicit, config))
    }

    // Route arrows
    for (const element of positioned) {
      if (element.type === 'arrow') {
        element = this.routeArrow(element, positioned, config)
      }
    }

    // Apply frame grouping
    if (config.groupByFrames) {
      positioned = this.applyFrameGrouping(positioned, config)
    }

    // Resolve collisions (optional)
    if (config.resolveCollisions) {
      positioned = this.resolveCollisions(positioned, config)
    }

    return positioned
  }

  // Core functions to implement
  gridLayout(elements, config): PositionedElement[] { }
  hierarchicalLayout(elements, config): PositionedElement[] { }
  routeArrow(arrow, allElements, config): PositionedElement { }
  routeElbowedPath(source, target, obstacles): Point[] { }
  applyFrameGrouping(elements, config): PositionedElement[] { }
  resolveCollisions(elements, config): PositionedElement[] { }
}
```

**Tests to Write** (18 total):
```
Grid Layout (5):
✓ test_grid_no_overlaps()
✓ test_grid_column_spacing()
✓ test_grid_row_spacing()
✓ test_single_element_at_origin()
✓ test_grid_dimensions_large()

Arrow Routing (4):
✓ test_arrow_avoids_elements()
✓ test_elbowed_path_creation()
✓ test_self_loop_routing()
✓ test_straight_path_routing()

Frame Grouping (3):
✓ test_frame_contains_children()
✓ test_frame_bounds_children()
✓ test_nested_frames()

Collision Resolution (3):
✓ test_collision_detection_accuracy()
✓ test_no_collision_when_separated()
✓ test_collision_resolution_convergence()

Element Sizing (3):
✓ test_element_sizing_from_text()
✓ test_default_width_by_type()
✓ test_long_label_width_expansion()
```

**Integration**: Wire layout engine into generation pipeline post-element creation

**Deliverable**: Layout engine passes 18 tests, full pipeline (Gen + Layout + Val) works

---

## Testing Strategy

### Unit Testing Layer

```typescript
// Test structure (Jest/Vitest)
describe('DiagramGenerator', () => {
  let generator: DiagramGenerator

  beforeEach(() => {
    generator = new DiagramGenerator()
  })

  describe('generateDiagram', () => {
    it('test_empty_diagram', () => {
      const spec = { nodes: [], edges: [], config: {} }
      const doc = generator.generateDiagram(spec)

      expect(doc.elements).toHaveLength(0)
      expect(doc.type).toBe('excalidraw')
      expect(doc.version).toBe(2)
    })

    // ... 14 more tests
  })
})
```

### Integration Testing Layer

```typescript
describe('Full Pipeline', () => {
  let generator: DiagramGenerator
  let validator: DiagramValidator
  let layout: LayoutEngine

  beforeEach(() => {
    generator = new DiagramGenerator()
    validator = new DiagramValidator()
    layout = new LayoutEngine()
  })

  it('test_gen_layout_validation_pipeline', () => {
    // 1. Generate
    const spec = createTestDiagram(50) // 50 elements
    const generated = generator.generateDiagram(spec)

    // 2. Layout
    const layoutConfig = { layoutMode: 'grid', colSpacing: 250 }
    const positioned = layout.layout(generated.elements, layoutConfig)

    // 3. Validate
    const result = validator.validate({
      ...generated,
      elements: positioned
    })

    expect(result.isValid).toBe(true)
    expect(result.errors).toHaveLength(0)
  })
})
```

### Performance Testing Layer

```typescript
describe('Performance', () => {
  it('test_50_elements_layout_under_1s', () => {
    const spec = createTestDiagram(50)
    const start = performance.now()

    const doc = fullPipeline(spec)

    const duration = performance.now() - start
    expect(duration).toBeLessThan(1000) // 1 second
  })

  it('test_100_elements_layout_under_2s', () => {
    const spec = createTestDiagram(100)
    const start = performance.now()

    const doc = fullPipeline(spec)

    const duration = performance.now() - start
    expect(duration).toBeLessThan(2000) // 2 seconds
  })
})
```

---

## Development Workflow

### Day 1-2: Setup & Generation
```bash
# Create test fixtures
frontend/__tests__/specs/excalidraw/fixtures.ts

# Create generator module
frontend/lib/excalidraw/generator.ts
frontend/__tests__/excalidraw/generator.test.ts

# Run tests, fix issues
npm test -- generator.test.ts --watch

# 15 tests passing ✓
```

### Day 3-4: Validation
```bash
# Create validator module
frontend/lib/excalidraw/validator.ts
frontend/__tests__/excalidraw/validator.test.ts

# Test against generated output
npm test -- validator.test.ts --watch

# 24 tests passing ✓
```

### Day 5-7: Layout Engine
```bash
# Create layout module
frontend/lib/excalidraw/layout.ts
frontend/__tests__/excalidraw/layout.test.ts

# Integration tests
frontend/__tests__/excalidraw/pipeline.test.ts

# Full pipeline: 18 + 5 = 23 tests ✓
```

### Day 8: Polish & Documentation
```bash
# Performance testing
npm test -- performance.test.ts

# Integration with DiagramEditor component
frontend/components/dev/DiagramEditor.tsx (hook into pipeline)

# Update architecture diagram via API
# Test end-to-end in browser
```

---

## Code Organization

```typescript
// frontend/lib/excalidraw/

generator.ts          // Spec 01 implementation
├─ DiagramGenerator class
├─ calculateNodePositions()
├─ createArrowElement()
├─ createTextElement()
└─ registerBinding()

validator.ts          // Spec 02 implementation
├─ DiagramValidator class
├─ validateStructure()
├─ validateElements()
├─ validateBindings()
└─ validateSemantics()

layout.ts             // Spec 03 implementation
├─ LayoutEngine class
├─ gridLayout()
├─ routeArrow()
├─ applyFrameGrouping()
└─ resolveCollisions()

types.ts              // Shared types
├─ DiagramSpec
├─ ExcalidrawDocument
├─ ValidationResult
├─ LayoutConfig
└─ PositionedElement

utils.ts              // Helpers
├─ generateId()
├─ estimateTextWidth()
├─ rectsOverlap()
├─ centerOfElement()
└─ isValidHexColor()
```

---

## Integration with Existing Codebase

### DiagramEditor Hook-In

```typescript
// frontend/components/dev/DiagramEditor.tsx

// Add to handleChange callback:
const handleChange = useCallback(
  (elements: readonly any[], appState: Record<string, unknown>) => {
    // Current flow (cosmetic changes):
    // latestDataRef.current = { elements, appState, ... }

    // Enhanced flow (with generation/layout/validation):
    const validator = new DiagramValidator()
    const layout = new LayoutEngine()

    const layoutedElements = layout.layout(elements, { layoutMode: 'grid' })
    const validationResult = validator.validate({
      type: 'excalidraw',
      version: 2,
      source: 'electricity-optimizer',
      elements: layoutedElements,
      appState,
      files: {}
    })

    if (!validationResult.isValid) {
      console.warn('Validation errors:', validationResult.errors)
    }

    latestDataRef.current = { elements: layoutedElements, appState, ... }
  },
  []
)
```

### API Route Hook-In

```typescript
// frontend/app/api/dev/diagrams/[name]/route.ts (PUT)

// Add to PUT handler:
const body = await request.json()
const { data } = body

// Validate incoming data
const validator = new DiagramValidator()
const validationResult = validator.validate(data)

if (!validationResult.isValid) {
  return NextResponse.json(
    { error: 'Invalid diagram data', details: validationResult.errors },
    { status: 400 }
  )
}

// Save validated data
fs.writeFileSync(filePath, JSON.stringify(data, null, 2))
```

---

## Testing Checklist

- [ ] Create test fixtures (empty, single, grid, arrows, text, etc.)
- [ ] Unit tests for generator (15 tests)
- [ ] Unit tests for validator (24 tests)
- [ ] Unit tests for layout engine (18 tests)
- [ ] Integration tests (Gen → Layout → Validation pipeline)
- [ ] Performance tests (50, 100, 200+ elements)
- [ ] Component integration (DiagramEditor)
- [ ] API integration (GET/POST/PUT endpoints)
- [ ] E2E test with Playwright
  - Create diagram
  - Edit and save
  - Verify Excalidraw renders correctly

---

## Common Pitfalls & Solutions

### Pitfall 1: Binding Registration Order
**Problem**: Arrow created but element boundElements not updated
**Solution**: Call `registerBinding()` immediately after creating arrow, before returning

```typescript
const arrow = createArrowElement(edge, positions)
registerBinding(elements, sourceElement, arrow.id, 'start')
registerBinding(elements, targetElement, arrow.id, 'end')
```

### Pitfall 2: Element Position Centering
**Problem**: Elements positioned at x,y instead of centered at those coords
**Solution**: Subtract width/2 and height/2 in grid calculation

```typescript
// WRONG:
x = col * colSpacing
// RIGHT:
x = col * colSpacing - width / 2
```

### Pitfall 3: Validation Too Strict
**Problem**: Valid diagrams fail validation (false negatives)
**Solution**: Distinguish errors (required fields) from warnings (best practices)

```typescript
// Level 3 (binding integrity): MUST PASS
// Level 4 (semantic validation): WARNING OK
```

### Pitfall 4: Arrow Routing Infinite Loops
**Problem**: Collision resolution or path-finding gets stuck
**Solution**: Set max iterations and fallback behavior

```typescript
for (let i = 0; i < MAX_ITERATIONS; i++) {
  if (collisions.length === 0) break
  // resolve...
}
// If still collisions after max iterations, accept small overlap
```

### Pitfall 5: Text Width Estimation
**Problem**: Text clipped or overflowing container
**Solution**: Add generous padding and re-estimate after scaling

```typescript
const estimatedWidth = estimateTextWidth(text, fontSize)
const paddedWidth = estimatedWidth + 20 // 10px on each side
```

---

## Performance Targets

| Metric | Target | Notes |
|--------|--------|-------|
| 10 elements | < 100ms | Simple grid |
| 50 elements | < 500ms | Medium grid |
| 100 elements | < 1s | Large grid |
| 200 elements | < 2s | Compact grid with layout optimization |

**Optimization Techniques**:
- Use spatial indexing (R-tree) for collision detection once > 50 elements
- Memoize grid calculations
- Lazy-load Excalidraw component (already done via dynamic import)
- Batch DOM updates

---

## Validation Checkpoints

```
Stage 1: Unit Tests
└─ 15 generation tests
└─ 24 validation tests
└─ 18 layout tests

Stage 2: Integration Tests
└─ Gen → Layout → Validation pipeline
└─ Excalidraw rendering accuracy
└─ Performance benchmarks

Stage 3: Component Integration
└─ DiagramEditor save flow
└─ API route validation
└─ E2E browser testing

Stage 4: Production Readiness
└─ Error boundary handling
└─ Graceful degradation
└─ Documentation complete
└─ Team code review approved
```

---

## Related Specifications & Documentation

- **[README.md](README.md)** — Specification suite overview and key concepts
- **[01_diagram_generation_spec.md](01_diagram_generation_spec.md)** — Phase 1 implementation details
- **[02_json_validation_spec.md](02_json_validation_spec.md)** — Phase 2 implementation details
- **[03_layout_engine_spec.md](03_layout_engine_spec.md)** — Phase 3 implementation details
- **[TEST_ANCHORS.md](TEST_ANCHORS.md)** — Complete test reference (54 tests)
- **[User Guide](../../excalidraw-agent-guide.md)** — How to use excalidraw-expert agent
- **[API Reference](../../excalidraw-reference.md)** — Components and APIs

---

**Implementation Guide Status**: Ready for Development
**Estimated Total Time**: 30-40 hours
**Team Size**: 1-2 developers recommended
**Code Review Points**: Binding logic, collision detection, validation strictness

---
