# Excalidraw Layout Engine Specification

## Overview

Auto-layout algorithm for positioning diagram elements with zero overlaps, configurable spacing, intelligent arrow routing, and frame-based grouping. Supports grid layouts, hierarchical layouts, and compact arrangements for complex multi-layer diagrams.

**Target File Size**: < 500 lines
**Language**: Pseudocode (language-agnostic)
**Test Framework**: Jest/Vitest with geometry collision detection utilities

---

## Requirements

### Functional Requirements

1. **Grid Layout**
   - Deterministic grid positioning based on element count
   - Configurable column/row spacing and gutter
   - Support for explicit position overrides
   - Balanced grid: cols = ceil(sqrt(N)), rows = ceil(N/cols)

2. **Arrow Routing (Path Calculation)**
   - Rectilinear routing (horizontal-vertical-horizontal or VHV)
   - Avoid overlapping elements when possible
   - Elbowed paths for better readability
   - Minimum clearance zones around elements

3. **Frame Grouping**
   - Automatic frame sizing to contain children with padding
   - Nested frame support (frames within frames)
   - Child element positioning relative to frame origin
   - Proper frameId assignment and boundElements linking

4. **Collision Detection**
   - Detect overlapping rectangles in O(n log n) using sweep-line algorithm
   - Resolve overlaps by shifting elements
   - Report overlap metrics for debugging

5. **Dynamic Element Sizing**
   - Text width estimation based on font and content
   - Auto-grow element dimensions to fit labels
   - Aspect ratio preservation for geometric shapes
   - Min/max constraints on element sizes

### Layout Modes

```plaintext
Mode: grid
  - Classic grid layout (sqrt-based columns)
  - Best for: Hierarchical structures, balanced element count
  - Parameters: colSpacing, rowSpacing, gutterSize

Mode: grid-compact
  - Compact grid with tighter spacing and dynamic column count
  - Best for: Large diagrams (50+ elements), dense layouts
  - Parameters: maxWidth, aspect ratio optimization

Mode: hierarchical
  - Layer-based layout with flow direction (LTR, TTB)
  - Best for: Data flow diagrams, dependency graphs
  - Parameters: flowDirection, layerSpacing, nodeSpacing
```

---

## Pseudocode

### 1. Main Layout Engine

```
FUNCTION layoutDiagram(
  elements: Array<DiagramElement>,
  config: LayoutConfig
): Array<PositionedElement>

  INPUT: Elements to position, configuration
  OUTPUT: Same elements with calculated x, y positions

  result ← []

  // Separate explicit and implicit position elements
  explicit ← elements.filter(e → e.x IS NOT NULL AND e.y IS NOT NULL)
  implicit ← elements.filter(e → e.x IS NULL OR e.y IS NULL)

  // Process explicit positions first (preserved as-is)
  FOR element IN explicit
    positioned ← {
      ...element,
      x: element.x,
      y: element.y,
      width: calculateElementWidth(element),
      height: calculateElementHeight(element)
    }
    APPEND positioned TO result

  // Layout implicit elements based on mode
  IF config.layoutMode == "grid"
    implicitPositioned ← gridLayout(implicit, config)
  ELSE IF config.layoutMode == "grid-compact"
    implicitPositioned ← compactGridLayout(implicit, config)
  ELSE IF config.layoutMode == "hierarchical"
    implicitPositioned ← hierarchicalLayout(implicit, config)
  ELSE
    implicitPositioned ← gridLayout(implicit, config)  // Default

  EXTEND result WITH implicitPositioned

  // Apply frame grouping if specified
  IF config.groupByFrames
    result ← applyFrameGrouping(result, config)

  // Route arrows
  FOR element AT i IN result
    IF element.type == "arrow"
      routedElement ← routeArrow(element, result, i, config)
      result[i] ← routedElement

  // Collision detection and resolution (optional)
  IF config.resolveCollisions
    result ← resolveCollisions(result, config)

  RETURN result
END FUNCTION
```

### 2. Grid Layout Implementation

```
FUNCTION gridLayout(
  elements: Array<DiagramElement>,
  config: LayoutConfig
): Array<PositionedElement>

  OUTPUT: Elements positioned in grid pattern

  IF elements.length == 0 RETURN []

  colSpacing ← config.colSpacing || 250
  rowSpacing ← config.rowSpacing || 150
  gutterSize ← config.gutterSize || 50

  n ← elements.length
  cols ← ceil(sqrt(n))
  rows ← ceil(n / cols)

  // Calculate total canvas bounds for centering
  totalWidth ← (cols - 1) * (colSpacing + gutterSize) + 200
  totalHeight ← (rows - 1) * (rowSpacing + gutterSize) + 160

  // Origin offset to center grid on canvas
  originX ← -totalWidth / 2
  originY ← -totalHeight / 2

  result ← []
  index ← 0

  FOR row FROM 0 TO rows - 1
    FOR col FROM 0 TO cols - 1
      IF index >= elements.length BREAK

      element ← elements[index]
      width ← calculateElementWidth(element)
      height ← calculateElementHeight(element)

      // Cell center position
      cellX ← originX + col * (colSpacing + gutterSize)
      cellY ← originY + row * (rowSpacing + gutterSize)

      // Center element within cell
      x ← cellX - width / 2
      y ← cellY - height / 2

      positioned ← {
        ...element,
        x: x,
        y: y,
        width: width,
        height: height
      }

      APPEND positioned TO result
      index ← index + 1

  RETURN result
END FUNCTION
```

### 3. Compact Grid Layout

```
FUNCTION compactGridLayout(
  elements: Array<DiagramElement>,
  config: LayoutConfig
): Array<PositionedElement>

  OUTPUT: Compact grid with dynamic column count

  IF elements.length == 0 RETURN []

  maxWidth ← config.maxWidth || 2000
  colSpacing ← config.colSpacing || 250
  gutterSize ← config.gutterSize || 50

  // Estimate element dimensions
  elementsWithSize ← elements.map(e → {
    ...e,
    width: calculateElementWidth(e),
    height: calculateElementHeight(e)
  })

  // Calculate optimal column count based on max width
  avgWidth ← sum(elementsWithSize[*].width) / elements.length
  estimatedCols ← floor(maxWidth / (avgWidth + colSpacing))
  cols ← max(estimatedCols, 2)  // At least 2 columns

  rows ← ceil(elements.length / cols)

  result ← []
  index ← 0

  FOR row FROM 0 TO rows - 1
    FOR col FROM 0 TO cols - 1
      IF index >= elements.length BREAK

      element ← elementsWithSize[index]

      x ← col * (element.width + colSpacing + gutterSize)
      y ← row * (element.height + 150 + gutterSize)

      positioned ← {
        ...element,
        x: x,
        y: y
      }

      APPEND positioned TO result
      index ← index + 1

  RETURN result
END FUNCTION
```

### 4. Hierarchical Layout

```
FUNCTION hierarchicalLayout(
  elements: Array<DiagramElement>,
  config: LayoutConfig
): Array<PositionedElement>

  OUTPUT: Layer-based layout for flow diagrams

  flowDirection ← config.flowDirection || "LTR"  // LTR or TTB
  layerSpacing ← config.layerSpacing || 300
  nodeSpacing ← config.nodeSpacing || 150

  // Build dependency graph
  graph ← buildDependencyGraph(elements)

  // Topological sort for layer assignment
  layers ← assignLayers(elements, graph)

  // Position elements by layer
  result ← []

  FOR layer, layerElements IN layers
    layerHeight ← layerElements.length * nodeSpacing
    layerWidth ← max(layerElements[*].width)

    FOR element AT nodeIndex IN layerElements
      width ← calculateElementWidth(element)
      height ← calculateElementHeight(element)

      IF flowDirection == "LTR"
        x ← layer * layerSpacing
        y ← nodeIndex * nodeSpacing - layerHeight / 2
      ELSE IF flowDirection == "TTB"
        x ← nodeIndex * nodeSpacing - layerHeight / 2
        y ← layer * layerSpacing

      positioned ← {
        ...element,
        x: x,
        y: y,
        width: width,
        height: height
      }

      APPEND positioned TO result

  RETURN result
END FUNCTION
```

### 5. Arrow Routing (Rectilinear Paths)

```
FUNCTION routeArrow(
  arrow: DiagramElement,
  allElements: Array<DiagramElement>,
  arrowIndex: number,
  config: LayoutConfig
): DiagramElement

  INPUT: Arrow element, all elements (for collision detection), config
  OUTPUT: Arrow with updated points array (routing path)

  // Find source and target elements
  sourceElement ← findElementById(allElements, arrow.startBinding.elementId)
  targetElement ← findElementById(allElements, arrow.endBinding.elementId)

  IF sourceElement IS NULL OR targetElement IS NULL
    RETURN arrow  // Can't route without both endpoints

  // Calculate edge centers
  sourceCenter ← centerOfElement(sourceElement)
  targetCenter ← centerOfElement(targetElement)

  // Route based on configuration
  IF config.elbowed == true
    path ← routeElbowedPath(sourceElement, targetElement, allElements, config)
  ELSE
    path ← routeStraightPath(sourceElement, targetElement)

  // Update arrow points (relative to arrow origin)
  points ← calculateRelativePoints(path)

  routedArrow ← {
    ...arrow,
    points: points,
    x: sourceCenter.x,
    y: sourceCenter.y,
    width: abs(targetCenter.x - sourceCenter.x),
    height: abs(targetCenter.y - sourceCenter.y)
  }

  RETURN routedArrow
END FUNCTION
```

### 6. Elbowed Path Routing

```
FUNCTION routeElbowedPath(
  sourceElement: DiagramElement,
  targetElement: DiagramElement,
  allElements: Array<DiagramElement>,
  config: LayoutConfig
): Array<Point>

  OUTPUT: Waypoints for elbowed (rectilinear) path

  sourceCenter ← centerOfElement(sourceElement)
  targetCenter ← centerOfElement(targetElement)

  dx ← targetCenter.x - sourceCenter.x
  dy ← targetCenter.y - sourceCenter.y

  // Determine primary routing direction
  IF abs(dx) > abs(dy)  // Route horizontally first (HVH)
    // Horizontal segment to midpoint
    midX ← sourceCenter.x + dx / 2
    path ← [
      sourceCenter,
      { x: midX, y: sourceCenter.y },     // First horizontal segment
      { x: midX, y: targetCenter.y },     // Vertical segment
      targetCenter
    ]
  ELSE  // Route vertically first (VHV)
    midY ← sourceCenter.y + dy / 2
    path ← [
      sourceCenter,
      { x: sourceCenter.x, y: midY },     // First vertical segment
      { x: targetCenter.x, y: midY },     // Horizontal segment
      targetCenter
    ]

  // Check for collisions with other elements
  obstacles ← findIntersectingElements(path, allElements)

  IF obstacles.length > 0
    // Reroute around obstacles
    path ← rerouteAroundObstacles(path, obstacles, config)

  RETURN path
END FUNCTION
```

### 7. Collision Avoidance

```
FUNCTION findIntersectingElements(
  path: Array<Point>,
  allElements: Array<DiagramElement>
): Array<DiagramElement>

  OUTPUT: Elements whose bounds the path intersects

  obstacles ← []

  FOR element IN allElements
    IF element.type == "arrow" CONTINUE  // Arrows pass through each other

    IF pathIntersectsRect(path, element)
      APPEND element TO obstacles

  RETURN obstacles
END FUNCTION

FUNCTION pathIntersectsRect(
  path: Array<Point>,
  rect: DiagramElement
): bool

  OUTPUT: True if any segment of path intersects rectangle bounds

  rectBounds ← {
    minX: rect.x,
    maxX: rect.x + rect.width,
    minY: rect.y,
    maxY: rect.y + rect.height
  }

  FOR i FROM 0 TO path.length - 2
    p1 ← path[i]
    p2 ← path[i + 1]

    IF lineSegmentIntersectsRect(p1, p2, rectBounds)
      RETURN true

  RETURN false
END FUNCTION
```

### 8. Straight Path Routing

```
FUNCTION routeStraightPath(
  sourceElement: DiagramElement,
  targetElement: DiagramElement
): Array<Point>

  OUTPUT: Simple straight line from source to target

  sourceCenter ← centerOfElement(sourceElement)
  targetCenter ← centerOfElement(targetElement)

  path ← [
    sourceCenter,
    targetCenter
  ]

  RETURN path
END FUNCTION
```

### 9. Frame Grouping

```
FUNCTION applyFrameGrouping(
  elements: Array<PositionedElement>,
  config: LayoutConfig
): Array<PositionedElement>

  INPUT: Elements with positions, grouping configuration
  OUTPUT: Same elements with frameId assignments and new frame elements

  result ← []
  frameMap ← {}  // { groupId → frame element }

  // Group elements by groupId
  groupedElements ← groupBy(elements, e → e.groupId)

  FOR groupId, groupElements IN groupedElements
    IF groupId IS NULL
      // Ungrouped elements stay as-is
      EXTEND result WITH groupElements
    ELSE
      // Create frame for this group
      frame ← createFrameForGroup(groupId, groupElements, config)
      APPEND frame TO result
      frameMap[groupId] ← frame

      // Update elements with frameId
      FOR element IN groupElements
        element.frameId ← frame.id
        APPEND element TO result

  RETURN result
END FUNCTION

FUNCTION createFrameForGroup(
  groupId: string,
  groupElements: Array<PositionedElement>,
  config: LayoutConfig
): Frame

  OUTPUT: Frame element that contains all group elements

  framePadding ← config.framePadding || 20

  // Calculate frame bounds
  minX ← min(groupElements[*].x)
  minY ← min(groupElements[*].y)
  maxX ← max(groupElements[*].x + groupElements[*].width)
  maxY ← max(groupElements[*].y + groupElements[*].height)

  frameWidth ← maxX - minX + 2 * framePadding
  frameHeight ← maxY - minY + 2 * framePadding

  frame ← {
    id: "frame_" + groupId,
    type: "frame",
    x: minX - framePadding,
    y: minY - framePadding,
    width: frameWidth,
    height: frameHeight,
    name: groupId,
    backgroundColor: "transparent",
    strokeColor: "#6c63ff",
    strokeWidth: 2,
    roughness: 0,
    opacity: 100,
    seed: randomInt(0, 2000000000),
    version: 1,
    versionNonce: randomInt(0, 2000000000),
    boundElements: []
  }

  // Register children in boundElements
  FOR element IN groupElements
    APPEND { id: element.id, type: element.type } TO frame.boundElements

  RETURN frame
END FUNCTION
```

### 10. Collision Detection and Resolution

```
FUNCTION resolveCollisions(
  elements: Array<PositionedElement>,
  config: LayoutConfig
): Array<PositionedElement>

  INPUT: Positioned elements with potential overlaps
  OUTPUT: Elements shifted to resolve collisions

  maxIterations ← 10
  iteration ← 0

  WHILE iteration < maxIterations
    collisions ← detectCollisions(elements)

    IF collisions.length == 0
      BREAK  // No more collisions

    // Resolve each collision by shifting one element
    FOR collision IN collisions
      elem1 ← elements[collision.index1]
      elem2 ← elements[collision.index2]

      // Shift elem2 away from elem1
      shift ← calculateShift(elem1, elem2, config.gutterSize)
      elem2.x ← elem2.x + shift.dx
      elem2.y ← elem2.y + shift.dy

    iteration ← iteration + 1

  RETURN elements
END FUNCTION

FUNCTION detectCollisions(elements: Array<PositionedElement>): Array<CollisionReport>

  OUTPUT: List of overlapping element pairs

  collisions ← []

  FOR i FROM 0 TO elements.length - 2
    FOR j FROM i + 1 TO elements.length - 1
      IF rectsOverlap(elements[i], elements[j])
        collisions.append({
          index1: i,
          index2: j,
          overlap: calculateOverlapArea(elements[i], elements[j])
        })

  RETURN collisions
END FUNCTION
```

### 11. Element Sizing Calculation

```
FUNCTION calculateElementWidth(element: DiagramElement): number

  INPUT: Element (possibly with label)
  OUTPUT: Width in pixels

  // Explicit width provided
  IF element.width IS NOT NULL
    RETURN element.width

  // Infer from type and label
  IF element.type == "text"
    estimatedWidth ← estimateTextWidth(element.label || "", element.fontSize || 16)
    RETURN estimatedWidth + 10  // Padding

  ELSE IF element.type == "arrow"
    RETURN 0  // Arrows have zero width, use points for sizing

  ELSE IF element.type == "frame"
    RETURN element.width || 300  // Default frame width

  ELSE
    // Default shape widths
    defaultWidths ← {
      rectangle: 160,
      ellipse: 120,
      diamond: 120,
      line: 200
    }
    RETURN defaultWidths[element.type] || 160

END FUNCTION

FUNCTION estimateTextWidth(text: string, fontSize: number): number

  OUTPUT: Estimated pixel width

  // Rough estimation: average char width = fontSize * 0.6
  charWidth ← fontSize * 0.6
  estimatedWidth ← text.length * charWidth

  RETURN estimatedWidth
END FUNCTION
```

### 12. Helper Geometry Functions

```
FUNCTION rectsOverlap(rect1: PositionedElement, rect2: PositionedElement): bool
  OUTPUT: True if rectangles overlap

  RETURN NOT (
    rect1.x + rect1.width < rect2.x OR
    rect1.x > rect2.x + rect2.width OR
    rect1.y + rect1.height < rect2.y OR
    rect1.y > rect2.y + rect2.height
  )
END FUNCTION

FUNCTION centerOfElement(element: DiagramElement): Point
  OUTPUT: Center point of element bounds

  RETURN {
    x: element.x + element.width / 2,
    y: element.y + element.height / 2
  }
END FUNCTION

FUNCTION calculateShift(
  sourceRect: PositionedElement,
  targetRect: PositionedElement,
  gutter: number
): Shift

  OUTPUT: { dx, dy } shift vector

  // Direction from source to target
  dx ← targetRect.x - sourceRect.x
  dy ← targetRect.y - sourceRect.y

  // Normalize and scale by (gutter + element width/height)
  IF dx > 0  // Target is to the right
    shift_dx ← (sourceRect.width / 2) + (targetRect.width / 2) + gutter
  ELSE  // Target is to the left
    shift_dx ← -((sourceRect.width / 2) + (targetRect.width / 2) + gutter)

  IF dy > 0  // Target is below
    shift_dy ← (sourceRect.height / 2) + (targetRect.height / 2) + gutter
  ELSE  // Target is above
    shift_dy ← -((sourceRect.height / 2) + (targetRect.height / 2) + gutter)

  RETURN { dx: shift_dx, dy: shift_dy }
END FUNCTION
```

---

## Edge Cases

### 1. Single Column (N < sqrt(N))
- **Input**: 3 elements with very wide bounds
- **Output**: Layout adjusts to single column if width-constrained
- **Test**: `test_single_column_layout()`

### 2. Single Row (N = 1 or 2)
- **Input**: 2 elements
- **Output**: grid(cols=2, rows=1) layout
- **Test**: `test_single_row_layout()`

### 3. Asymmetric Groups
- **Input**: 10 elements: 6 in group A, 4 in group B
- **Output**: Frames sized appropriately to each group
- **Test**: `test_asymmetric_group_sizing()`

### 4. Very Long Labels Affecting Width
- **Input**: Element with label "This is an extremely long label..."
- **Output**: Element width expanded, adjacent elements shifted
- **Test**: `test_long_label_width_expansion()`

### 5. Self-Loop Arrow
- **Input**: Arrow from node A to node A
- **Output**: Elbowed path around the element
- **Test**: `test_self_loop_path_routing()`

### 6. Circular Dependencies in Hierarchical Layout
- **Input**: A→B→C→A
- **Output**: Cycle detected, fallback to grid layout
- **Test**: `test_circular_dependency_fallback()`

### 7. Very Close Elements (Minimal Spacing)
- **Input**: Two elements with positions < gutterSize apart
- **Output**: Collision resolution shifts elements further
- **Test**: `test_collision_resolution_spacing()`

### 8. Arrow Path Blocked by Many Elements
- **Input**: 10 elements in a line, arrow tries to route through them
- **Output**: Complex elbowed path that avoids all obstacles
- **Test**: `test_complex_obstacle_avoidance()`

### 9. Frame with No Children
- **Input**: Frame { groupId: "empty" } with no grouped elements
- **Output**: Frame sized to minimum (e.g., 200x150)
- **Test**: `test_empty_frame_sizing()`

### 10. Mixed Explicit and Implicit Positions
- **Input**: nodes [n1 with x,y, n2 without, n3 without]
- **Output**: n1 stays at explicit position, n2/n3 laid out in grid avoiding n1
- **Test**: `test_mixed_explicit_implicit_positions()`

---

## TDD Test Anchors

### Grid Layout Tests

```
test_grid_no_overlaps()
  GIVEN: 9 elements in 3x3 grid
  EXPECT: For all pairs (i,j), rectsOverlap(i,j) == false

test_grid_column_spacing()
  GIVEN: 4 elements with colSpacing=250
  EXPECT: Horizontal distance between columns == 250px (centers)

test_grid_row_spacing()
  GIVEN: 4 elements with rowSpacing=150
  EXPECT: Vertical distance between rows == 150px (centers)

test_single_element_at_origin()
  GIVEN: 1 element
  EXPECT: Element centered at approximately (0, 0)

test_grid_dimensions_large()
  GIVEN: 50 elements
  EXPECT: cols == ceil(sqrt(50)) == 8
  EXPECT: rows == ceil(50/8) == 7
```

### Arrow Routing Tests

```
test_arrow_avoids_elements()
  GIVEN: Arrow A→B, element C between them
  EXPECT: Path routing avoids C bounds
  EXPECT: No path segment intersects C

test_elbowed_path_creation()
  GIVEN: Arrow with elbowed=true
  EXPECT: points.length >= 3
  EXPECT: At least one horizontal + one vertical segment

test_self_loop_routing()
  GIVEN: Arrow A→A
  EXPECT: Path forms loop around A
  EXPECT: startBinding.elementId == endBinding.elementId

test_straight_path_routing()
  GIVEN: Arrow with elbowed=false
  EXPECT: points.length == 2
  EXPECT: Direct line from source to target
```

### Frame Grouping Tests

```
test_frame_contains_children()
  GIVEN: 5 elements with groupId="services"
  EXPECT: Frame.width >= max(children.width) + padding
  EXPECT: Frame.height >= max(children.height) + padding

test_frame_bounds_children()
  GIVEN: 3 children at various positions
  EXPECT: All children x,y within frame bounds

test_nested_frames()
  GIVEN: Elements grouped in frame A, frame A grouped in frame B
  EXPECT: Frame B contains frame A
  EXPECT: frameId chain is valid

test_empty_frame_sizing()
  GIVEN: Frame with no children
  EXPECT: Frame sized to minimum dimensions (200x150)
```

### Collision Detection Tests

```
test_collision_detection_accuracy()
  GIVEN: Overlapping rectangles
  EXPECT: detectCollisions returns true

test_no_collision_when_separated()
  GIVEN: Rectangles separated by > gutter distance
  EXPECT: detectCollisions returns false

test_collision_resolution_convergence()
  GIVEN: 10 overlapping elements
  EXPECT: resolveCollisions terminates in < 10 iterations
  EXPECT: Final state has no collisions

test_element_sizing_from_text()
  GIVEN: Element { label: "Service API" }
  EXPECT: calculateElementWidth returns > 80 pixels
  EXPECT: Width increases with label length
```

### Layout Mode Tests

```
test_grid_layout_mode()
  GIVEN: layoutMode="grid"
  EXPECT: cols = ceil(sqrt(N))

test_compact_grid_layout_mode()
  GIVEN: layoutMode="grid-compact"
  EXPECT: Dynamic column count based on maxWidth

test_hierarchical_layout_mode()
  GIVEN: layoutMode="hierarchical"
  EXPECT: Elements arranged in layers
  EXPECT: No topological order violations

test_hierarchical_ltr_direction()
  GIVEN: flowDirection="LTR"
  EXPECT: Layers progress left-to-right
  EXPECT: x increases with layer number

test_hierarchical_ttb_direction()
  GIVEN: flowDirection="TTB"
  EXPECT: Layers progress top-to-bottom
  EXPECT: y increases with layer number
```

---

## Implementation Notes

- **Performance**: For 50+ elements, use spatial indexing (R-tree or quad-tree) for collision detection
- **Determinism**: All calculations should produce same output for identical input
- **Overflow Handling**: Canvas positioning should handle negative coordinates naturally
- **Iterative Resolution**: Collision resolution may require multiple iterations; set reasonable max_iterations (10-20)
- **Path Simplification**: After routing, simplify paths by removing unnecessary waypoints
- **Frame Padding**: Default 20px padding provides visual breathing room around grouped elements
- **Clearance Zones**: Arrow paths should have 60px horizontal clearance between columns

---

## Related Specifications

- **[01_diagram_generation_spec.md](01_diagram_generation_spec.md)** — Element creation that feeds layout engine
- **[02_json_validation_spec.md](02_json_validation_spec.md)** — Validates positioned element properties
- **[README.md](README.md)** — Specification suite overview and architecture
- **[IMPLEMENTATION_GUIDE.md](IMPLEMENTATION_GUIDE.md)** — Development roadmap (Phase 3)

## Related Documentation

- **[User Guide](../../excalidraw-agent-guide.md)** — How to invoke excalidraw-expert agent
- **[API Reference](../../excalidraw-reference.md)** — Components, hooks, and API routes
- **[Agent Definition](/Users/devinmcgrath/.claude/agents/excalidraw-expert.md)** — Agent specification

---

**Authored**: 2026-02-26
**Version**: 1.0
**Status**: Ready for Implementation
