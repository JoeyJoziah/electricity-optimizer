# Excalidraw Diagram Generation Specification

## Overview

Programmatic generation of valid .excalidraw JSON files from structured input (nodes + edges). Covers element positioning, arrow binding creation, text label placement, and comprehensive edge case handling.

**Target File Size**: < 500 lines
**Language**: Pseudocode (language-agnostic)
**Test Framework**: Jest/Vitest with mock Excalidraw schema validation

---

## Requirements

### Functional Requirements

1. **Generate Valid .excalidraw JSON**
   - Input: `DiagramSpec { nodes: Node[], edges: Edge[], config?: Config }`
   - Output: Complete .excalidraw document with all required root fields
   - Schema compliance: `{ type, version, source, elements, appState, files }`
   - All elements must have unique IDs, valid seed, and version >= 1

2. **Element Positioning Algorithm**
   - Grid layout with configurable spacing (250px cols, 150px rows, 50px gutters)
   - Support for multiple layout modes: grid, grid-compact, hierarchical
   - Zero element overlap guarantee
   - Deterministic positioning for reproducibility

3. **Arrow Binding System**
   - Bidirectional references: arrow.startBinding → element.boundElements, arrow.endBinding → element.boundElements
   - Focus calculation for arrow placement on element edges (-1 to 1 range)
   - Gap calculation for arrowhead clearance (1-5px typical)
   - Support for elbowed routing (right-angle connectors)

4. **Text Label Placement**
   - Automatic centering within container elements
   - containerId linking between text and parent shape
   - boundElements registration on parent
   - Multi-line text support with auto-resize

5. **Color and Style Application**
   - Architectural color conventions: services/APIs (blue), databases (green), external (yellow), errors (red), ML (violet)
   - Consistent strokeColor, backgroundColor, fillStyle, roughness
   - Support for element grouping via groupIds

### Input Specification

```plaintext
DiagramSpec:
  nodes: Array<Node>
    - id: string (unique, alphanumeric + underscore)
    - type: 'rectangle' | 'ellipse' | 'diamond' | 'text' | 'frame'
    - label: string (optional, auto-wrapped)
    - category: 'service' | 'database' | 'external' | 'error' | 'ml' | 'generic'
    - width: number (default: inferred from label or 160)
    - height: number (default: inferred from label or 80)
    - x: number (optional, explicit position)
    - y: number (optional, explicit position)
    - groupId: string (optional, for grouping)

  edges: Array<Edge>
    - id: string (unique, alphanumeric + underscore)
    - source: string (node id)
    - target: string (node id)
    - label: string (optional, placed on arrow or as separate text element)
    - arrowheadStart: 'arrow' | 'bar' | 'dot' | 'triangle' | null
    - arrowheadEnd: 'arrow' | 'bar' | 'dot' | 'triangle' | null
    - elbowed: boolean (default: false, true = right-angle routing)

  config: {
    colSpacing: number (default: 250),
    rowSpacing: number (default: 150),
    gutterSize: number (default: 50),
    gridSize: number | null (default: null),
    layoutMode: 'grid' | 'grid-compact' | 'hierarchical' (default: 'grid'),
    theme: 'light' | 'dark' (default: 'light'),
  }
```

### Output Specification

```plaintext
ExcalidrawDocument:
  type: "excalidraw" (literal)
  version: 2 (current schema)
  source: "electricity-optimizer"
  elements: Array<ExcalidrawElement>
    - rectangle, ellipse, diamond, arrow, text elements with full properties
  appState:
    gridSize: number | null
    viewBackgroundColor: "#ffffff" | "#1a1a1a"
  files: {} (empty object, no embedded images in generated diagrams)
```

---

## Pseudocode

### 1. Main Generation Function

```
FUNCTION generateDiagram(spec: DiagramSpec): ExcalidrawDocument
  INPUT: DiagramSpec with nodes, edges, and optional config
  OUTPUT: Valid .excalidraw JSON document

  config ← mergeWithDefaults(spec.config)
  elements ← []
  nodeMap ← {} // { nodeId → { x, y, width, height } }

  // Phase 1: Position all nodes
  positions ← calculateNodePositions(spec.nodes, config)
  FOR each node IN spec.nodes
    nodeMap[node.id] ← positions[node.id]
    element ← createNodeElement(node, positions[node.id], config)
    APPEND element TO elements

  // Phase 2: Create arrows and bindings
  FOR each edge IN spec.edges
    sourceNode ← findNode(spec.nodes, edge.source)
    targetNode ← findNode(spec.nodes, edge.target)
    sourcePos ← nodeMap[edge.source]
    targetPos ← nodeMap[edge.target]

    arrowElement ← createArrowElement(
      edge,
      sourcePos,
      targetPos,
      config
    )
    APPEND arrowElement TO elements

    // Register bindings bidirectionally
    registerBinding(
      elements,
      findElement(elements, edge.source),
      arrowElement.id,
      "start"
    )
    registerBinding(
      elements,
      findElement(elements, edge.target),
      arrowElement.id,
      "end"
    )

    // Add arrow label if present
    IF edge.label EXISTS
      labelElement ← createTextElement(
        edge.label,
        midpoint(sourcePos, targetPos),
        config
      )
      APPEND labelElement TO elements

  RETURN {
    type: "excalidraw",
    version: 2,
    source: "electricity-optimizer",
    elements: elements,
    appState: {
      gridSize: config.gridSize,
      viewBackgroundColor: config.theme == "dark" ? "#1a1a1a" : "#ffffff"
    },
    files: {}
  }
END FUNCTION
```

### 2. Node Positioning Algorithm

```
FUNCTION calculateNodePositions(
  nodes: Array<Node>,
  config: Config
): Map<string, Position>

  OUTPUT: { nodeId → { x, y, width, height } }

  // Handle explicit positions first
  explicitNodes ← nodes WHERE node.x IS NOT NULL AND node.y IS NOT NULL
  implicitNodes ← nodes WHERE node.x IS NULL OR node.y IS NULL

  positions ← {}
  FOR each node IN explicitNodes
    positions[node.id] ← {
      x: node.x,
      y: node.y,
      width: node.width || DEFAULT_WIDTHS[node.type],
      height: node.height || DEFAULT_HEIGHTS[node.type]
    }

  // Grid layout for implicit nodes
  IF config.layoutMode == "grid"
    gridPositions ← gridLayoutPositions(
      implicitNodes,
      config.colSpacing,
      config.rowSpacing,
      config.gutterSize
    )
    FOR each nodeId, pos IN gridPositions
      positions[nodeId] ← pos

  ELSE IF config.layoutMode == "grid-compact"
    gridPositions ← compactGridLayout(implicitNodes, config)
    FOR each nodeId, pos IN gridPositions
      positions[nodeId] ← pos

  ELSE IF config.layoutMode == "hierarchical"
    hierarchyPositions ← hierarchicalLayout(implicitNodes, config)
    FOR each nodeId, pos IN hierarchyPositions
      positions[nodeId] ← pos

  RETURN positions
END FUNCTION
```

### 3. Grid Layout Implementation

```
FUNCTION gridLayoutPositions(
  nodes: Array<Node>,
  colSpacing: number,
  rowSpacing: number,
  gutterSize: number
): Map<string, Position>

  OUTPUT: Deterministic grid positions with no overlaps

  n ← nodes.length
  IF n == 0 RETURN {}
  IF n == 1 RETURN { nodes[0].id → { x: 0, y: 0, ... } }

  // Calculate grid dimensions
  cols ← ceil(sqrt(n))  // Balanced square-ish grid
  rows ← ceil(n / cols)

  positions ← {}
  index ← 0

  FOR row FROM 0 TO rows - 1
    FOR col FROM 0 TO cols - 1
      IF index >= n BREAK

      node ← nodes[index]
      width ← node.width || DEFAULT_WIDTHS[node.type]
      height ← node.height || DEFAULT_HEIGHTS[node.type]

      // Calculate position with centered alignment
      x ← col * (colSpacing + gutterSize)
      y ← row * (rowSpacing + gutterSize)

      // Center element within grid cell
      x ← x - width / 2
      y ← y - height / 2

      positions[node.id] ← {
        x: x,
        y: y,
        width: width,
        height: height
      }

      index ← index + 1

  RETURN positions
END FUNCTION
```

### 4. Arrow Binding Creation

```
FUNCTION createArrowElement(
  edge: Edge,
  sourcePos: Position,
  targetPos: Position,
  config: Config
): ExcalidrawArrow

  OUTPUT: Valid arrow element with bidirectional bindings

  arrowId ← generateId()

  // Calculate arrow endpoints on element edges
  sourceBinding ← calculateBinding(sourcePos, targetPos, "source")
  targetBinding ← calculateBinding(targetPos, sourcePos, "target")

  // Calculate arrow path points
  IF edge.elbowed == true
    points ← calculateElbowedPath(
      sourcePos,
      targetPos,
      config.gutterSize
    )
  ELSE
    points ← [[0, 0], [targetPos.x - sourcePos.x, targetPos.y - sourcePos.y]]

  arrowElement ← {
    type: "arrow",
    id: arrowId,
    x: sourcePos.x,
    y: sourcePos.y,
    width: abs(targetPos.x - sourcePos.x),
    height: abs(targetPos.y - sourcePos.y),
    points: points,
    startBinding: sourceBinding,
    endBinding: targetBinding,
    startArrowhead: edge.arrowheadStart || "arrow",
    endArrowhead: edge.arrowheadEnd || null,
    strokeColor: "#1971c2",  // Default blue
    backgroundColor: "transparent",
    fillStyle: "solid",
    strokeWidth: 2,
    roughness: 0,  // Architecture (clean lines)
    opacity: 100,
    seed: randomInt(0, 2000000000),
    version: 1,
    versionNonce: randomInt(0, 2000000000),
    groupIds: [],
    frameId: null,
    boundElements: []  // Will be filled by registry
  }

  RETURN arrowElement
END FUNCTION
```

### 5. Binding Focus Calculation

```
FUNCTION calculateBinding(
  sourcePos: Position,
  targetPos: Position,
  direction: "source" | "target"
): Binding

  OUTPUT: { elementId, focus, gap, fixedPoint }

  // Determine which edge of source element the arrow connects to
  // Based on relative position of target
  dx ← targetPos.x - sourcePos.x
  dy ← targetPos.y - sourcePos.y
  angle ← atan2(dy, dx)

  // Focus: -1 (left/top) to 1 (right/bottom), 0 = center
  // For top/bottom edges: focus based on x offset
  // For left/right edges: focus based on y offset
  IF angle is in range [-π/4, π/4]  // Right
    focus ← (targetPos.y - sourcePos.y) / sourcePos.height
  ELSE IF angle is in range [π/4, 3π/4]  // Bottom
    focus ← (targetPos.x - sourcePos.x) / sourcePos.width
  ELSE IF angle is in range [3π/4, 5π/4] OR angle < -3π/4  // Left
    focus ← (targetPos.y - sourcePos.y) / sourcePos.height
  ELSE  // Top
    focus ← (targetPos.x - sourcePos.x) / sourcePos.width

  // Clamp focus to [-1, 1]
  focus ← clamp(focus, -1, 1)

  binding ← {
    elementId: sourceElement.id,
    focus: focus,
    gap: 2,  // Standard arrowhead gap
    fixedPoint: null  // Auto-calculated by Excalidraw
  }

  RETURN binding
END FUNCTION
```

### 6. Elbowed Arrow Path Calculation

```
FUNCTION calculateElbowedPath(
  sourcePos: Position,
  targetPos: Position,
  arrowSpacing: number
): Array<[number, number]>

  OUTPUT: Points array for right-angle routing

  // Start at source, end at target
  dx ← targetPos.x - sourcePos.x
  dy ← targetPos.y - sourcePos.y

  // Determine if we route horizontally or vertically first
  IF abs(dx) > abs(dy)  // Route right/left first
    midX ← sourcePos.x + dx / 2
    points ← [
      [0, 0],                      // Start at source
      [midX - sourcePos.x, 0],     // Horizontal to midpoint
      [midX - sourcePos.x, dy]     // Vertical to target
    ]
  ELSE  // Route up/down first
    midY ← sourcePos.y + dy / 2
    points ← [
      [0, 0],                      // Start at source
      [0, midY - sourcePos.y],     // Vertical to midpoint
      [dx, midY - sourcePos.y]     // Horizontal to target
    ]

  RETURN points
END FUNCTION
```

### 7. Text Label Placement in Container

```
FUNCTION createTextElement(
  text: string,
  container: ExcalidrawElement | Position,
  config: Config
): ExcalidrawText

  OUTPUT: Text element with containerId if within a shape

  textId ← generateId()

  // Determine size needed for text
  estimatedWidth ← estimateTextWidth(text, 16)  // fontSize 16
  estimatedHeight ← estimateTextHeight(text, 16)

  // Center within container or at explicit position
  IF container IS ExcalidrawElement
    x ← container.x + container.width / 2 - estimatedWidth / 2
    y ← container.y + container.height / 2 - estimatedHeight / 2
    containerId ← container.id
  ELSE
    x ← container.x - estimatedWidth / 2
    y ← container.y - estimatedHeight / 2
    containerId ← null

  textElement ← {
    type: "text",
    id: textId,
    x: x,
    y: y,
    width: estimatedWidth,
    height: estimatedHeight,
    text: text,
    originalText: text,
    fontFamily: 2,  // Helvetica (clean)
    fontSize: 16,
    textAlign: "center",
    verticalAlign: "middle",
    containerId: containerId,
    autoResize: true,
    lineHeight: 1.25,
    strokeColor: "#1e1e1e",
    backgroundColor: "transparent",
    fillStyle: "solid",
    strokeWidth: 1,
    roughness: 0,
    opacity: 100,
    seed: randomInt(0, 2000000000),
    version: 1,
    versionNonce: randomInt(0, 2000000000),
    groupIds: [],
    frameId: null,
    boundElements: []
  }

  RETURN textElement
END FUNCTION
```

### 8. Bidirectional Binding Registration

```
FUNCTION registerBinding(
  elements: Array<ExcalidrawElement>,
  containerElement: ExcalidrawElement,
  childId: string,
  bindingType: "start" | "end"
): VOID

  MODIFIES: elements array in-place, updating containerElement.boundElements

  // Add arrow reference to container's boundElements
  boundEntry ← {
    id: childId,
    type: "arrow"  // or "text" depending on childId type
  }

  // Check if binding already exists (avoid duplicates)
  IF NOT containerElement.boundElements.find(b → b.id == childId)
    APPEND boundEntry TO containerElement.boundElements

END FUNCTION
```

---

## Edge Cases

### 1. Zero Elements
- **Input**: `{ nodes: [], edges: [] }`
- **Output**: Valid empty diagram with default appState
- **Test**: `test_empty_diagram()`
- **Handling**: Return template document with empty elements array

### 2. Single Element
- **Input**: `{ nodes: [{ id: "n1", type: "rectangle" }], edges: [] }`
- **Output**: Single rectangle at origin (0, 0) with no arrows
- **Test**: `test_single_element()`
- **Handling**: Bypass grid calculation, place at (0, 0) - width/2, (0, 0) - height/2

### 3. Large Grid (50+ Elements)
- **Input**: `{ nodes: [... 50+ nodes ...], edges: [] }`
- **Output**: Multi-row grid layout with no overlaps
- **Test**: `test_large_grid_layout()`
- **Handling**: cols = ceil(sqrt(50)) = 8, rows = 7, verify spacing

### 4. Circular Dependencies
- **Input**: `{ nodes: [n1, n2, n3], edges: [e1→e2, e2→e3, e3→e1] }`
- **Output**: All arrows created, no infinite loop
- **Test**: `test_circular_dependencies()`
- **Handling**: No special logic needed; each edge is processed independently

### 5. Missing Node References
- **Input**: `{ nodes: [{id: "n1"}], edges: [{source: "n1", target: "n999"}] }`
- **Output**: Arrow created but endBinding references non-existent node (graceful degradation)
- **Test**: `test_missing_target_node()`
- **Handling**: Create arrow anyway; Excalidraw will render broken binding visually

### 6. Duplicate Node IDs
- **Input**: `{ nodes: [{id: "n1"}, {id: "n1"}] }`
- **Output**: Error or last-wins behavior
- **Test**: `test_duplicate_node_ids()` (should throw)
- **Handling**: Validate input, throw `DuplicateNodeError` before generation

### 7. Very Long Labels
- **Input**: `{ nodes: [{id: "n1", label: "This is an extremely long label that will wrap..."}] }`
- **Output**: Text width calculated correctly, may affect grid spacing
- **Test**: `test_long_label_text_wrapping()`
- **Handling**: Estimate width, adjust node dimensions upward if needed

### 8. Overlapping Explicit Positions
- **Input**: `{ nodes: [{id: "n1", x: 0, y: 0}, {id: "n2", x: 50, y: 50}] }`
- **Output**: Elements placed at exact coordinates, no overlap correction
- **Test**: `test_explicit_overlaps_allowed()`
- **Handling**: Trust user input for explicit positions; no auto-spacing

### 9. Arrow to Same Node (Self-Loop)
- **Input**: `{ edges: [{source: "n1", target: "n1"}] }`
- **Output**: Self-referencing arrow with elbowed path
- **Test**: `test_self_loop_arrow()`
- **Handling**: Create loop path (right-angle around element), both bindings reference same element

### 10. Elbowed Arrow with Minimal Space
- **Input**: Two nodes very close together with elbowed=true
- **Output**: Elbowed path calculated anyway, may overlap other elements
- **Test**: `test_elbowed_minimal_spacing()`
- **Handling**: No collision detection; path calculation proceeds as-is

---

## TDD Test Anchors

### Core Functionality Tests

```
test_empty_diagram()
  EXPECT: elements.length == 0
  EXPECT: appState.gridSize == null
  EXPECT: type == "excalidraw"

test_single_element()
  EXPECT: elements.length == 1
  EXPECT: elements[0].type == "rectangle"
  EXPECT: elements[0].x < 0 AND elements[0].y < 0  // Centered

test_arrow_bindings_bidirectional()
  GIVEN: nodes [n1, n2], edges [e1 → e2]
  EXPECT: arrowElement.startBinding.elementId == n1.id
  EXPECT: arrowElement.endBinding.elementId == n2.id
  EXPECT: n1.boundElements.find(b → b.id == arrowElement.id)
  EXPECT: n2.boundElements.find(b → b.id == arrowElement.id)

test_no_overlaps_grid_layout()
  GIVEN: 9 nodes in grid (3x3)
  EXPECT: For all pairs (i, j), rects[i] does not overlap rects[j]
  EXPECT: Column spacing >= 250px
  EXPECT: Row spacing >= 150px

test_text_in_container()
  GIVEN: Rectangle node with label "Service A"
  EXPECT: textElement.containerId == rectangleElement.id
  EXPECT: textElement.x approximately inside rectangleElement.x bounds
  EXPECT: rectangleElement.boundElements includes textId

test_large_grid_layout()
  GIVEN: 50 nodes
  EXPECT: elements.length >= 50
  EXPECT: cols = ceil(sqrt(50)) = 8
  EXPECT: rows = ceil(50/8) = 7
  EXPECT: Maximum y position = 6 * 150

test_elbowed_arrow_routing()
  GIVEN: Arrow with elbowed=true
  EXPECT: points.length >= 3
  EXPECT: Horizontal segment then vertical (or vice versa)

test_binding_focus_calculation()
  GIVEN: Source at (0,0), Target at (300, 0) [right]
  EXPECT: binding.focus is close to 0 [center vertical edge]

  GIVEN: Source at (0,0), Target at (0, 300) [bottom]
  EXPECT: binding.focus is close to 0 [center horizontal edge]
```

### Validation Tests

```
test_all_elements_have_unique_ids()
  EXPECT: No duplicates in elements[*].id

test_all_elements_have_valid_seed()
  EXPECT: All elements[*].seed is integer in [0, 2000000000]

test_all_elements_have_version_gte_1()
  EXPECT: All elements[*].version >= 1

test_arrows_have_bidirectional_refs()
  FOR each arrow element:
    EXPECT: sourceBinding.elementId exists in elements
    EXPECT: targetBinding.elementId exists in elements
    EXPECT: Both target elements have arrow.id in boundElements

test_schema_compliance()
  EXPECT: document.type == "excalidraw"
  EXPECT: document.version == 2
  EXPECT: document.source == "electricity-optimizer"
  EXPECT: document.elements IS array
  EXPECT: document.appState HAS gridSize, viewBackgroundColor
  EXPECT: document.files IS empty object
```

### Error Handling Tests

```
test_duplicate_node_ids_throws()
  EXPECT: Throws DuplicateNodeIdError

test_invalid_node_type_throws()
  GIVEN: node.type = "invalid"
  EXPECT: Throws InvalidNodeTypeError

test_self_loop_creates_arrow()
  GIVEN: source == target
  EXPECT: Arrow created successfully
  EXPECT: Both bindings reference same element

test_missing_target_node_creates_arrow_anyway()
  GIVEN: target node doesn't exist
  EXPECT: Arrow created
  EXPECT: endBinding.elementId set to non-existent ID (graceful)
```

---

## Implementation Notes

- **Determinism**: Use seed values and consistent ordering to ensure same input produces same output (for caching)
- **ID Generation**: Prefer descriptive slugs over random IDs (e.g., "service_api_element" not "x7a2k9")
- **Position Calculations**: Store intermediate calculations to enable debugging and visualization
- **Binding Integrity**: Always verify bidirectional consistency before returning document
- **Performance**: For 50+ elements, grid calculation is O(n log n) due to sorting; acceptable for typical diagrams
- **Error Recovery**: Catch JSON serialization errors and provide clear messages

---

## Related Specifications

- **[02_json_validation_spec.md](02_json_validation_spec.md)** — Schema validation after generation
- **[03_layout_engine_spec.md](03_layout_engine_spec.md)** — Advanced layout algorithms and optimization
- **[README.md](README.md)** — Specification suite overview and architecture
- **[IMPLEMENTATION_GUIDE.md](IMPLEMENTATION_GUIDE.md)** — Development roadmap (Phase 1)

## Related Documentation

- **[User Guide](../../excalidraw-agent-guide.md)** — How to invoke excalidraw-expert agent
- **[API Reference](../../excalidraw-reference.md)** — Components, hooks, and API routes
- **[Agent Definition](/Users/devinmcgrath/.claude/agents/excalidraw-expert.md)** — Agent specification

---

**Authored**: 2026-02-26
**Version**: 1.0
**Status**: Ready for Implementation
