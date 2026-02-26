# Excalidraw Specification - Complete Test Anchor Reference

Master list of all 54 test anchors across three specifications, organized by module with cross-references.

---

## Module 01: Diagram Generation (12 Tests)

### Core Functionality

#### test_empty_diagram
**File**: 01_diagram_generation_spec.md → Edge Cases → Zero Elements
**Input**: `{ nodes: [], edges: [] }`
**Expectations**:
- `elements.length === 0`
- `appState.gridSize === null`
- `type === "excalidraw"`
- `version === 2`
- `files === {}`

#### test_single_element
**File**: 01_diagram_generation_spec.md → Edge Cases → Single Element
**Input**: `{ nodes: [{ id: "n1", type: "rectangle" }], edges: [] }`
**Expectations**:
- `elements.length === 1`
- `elements[0].type === "rectangle"`
- Element x < 0 AND y < 0 (centered at origin)
- `elements[0].width > 0 AND elements[0].height > 0`

#### test_arrow_bindings_bidirectional
**File**: 01_diagram_generation_spec.md → Pseudocode → Arrow Binding Creation
**Input**: `{ nodes: [n1, n2], edges: [{ source: "n1", target: "n2" }] }`
**Setup**: Generate diagram with one arrow
**Expectations**:
- `arrowElement.startBinding.elementId === "n1"`
- `arrowElement.endBinding.elementId === "n2"`
- `n1.boundElements` contains `{id: arrowElement.id, type: "arrow"}`
- `n2.boundElements` contains `{id: arrowElement.id, type: "arrow"}`
- Both target elements have **matching arrow entry** (bidirectional consistency)

#### test_no_overlaps_grid_layout
**File**: 01_diagram_generation_spec.md → Edge Cases → Grid Layout
**Input**: 9 nodes arranged in 3×3 grid
**Setup**: Call `calculateNodePositions()` with colSpacing=250, rowSpacing=150
**Expectations**:
- For all pairs (i, j): `rectsOverlap(elements[i], elements[j]) === false`
- Column spacing >= 250px (center-to-center)
- Row spacing >= 150px (center-to-center)
- Maximum x position = `2 * 250 + width/2`
- Maximum y position = `2 * 150 + height/2`

#### test_text_in_container
**File**: 01_diagram_generation_spec.md → Pseudocode → Text Label Placement
**Input**: Rectangle node with label "Service A"
**Setup**: Generate diagram with rectangle and text child
**Expectations**:
- `textElement.containerId === rectangleElement.id`
- `textElement.x` approximately centered within rectangle bounds
- `textElement.y` approximately centered within rectangle bounds
- `rectangleElement.boundElements` includes `{id: textId, type: "text"}`
- Text width + padding <= rectangle width

#### test_large_grid_layout
**File**: 01_diagram_generation_spec.md → Edge Cases → Large Grid (50+ Elements)
**Input**: 50 nodes, no explicit positions
**Setup**: `generateDiagram({ nodes: [50 elements], edges: [], config: {} })`
**Expectations**:
- `elements.length >= 50` (nodes + arrows + text if any)
- `cols = ceil(sqrt(50)) === 8`
- `rows = ceil(50/8) === 7`
- Grid dimensions correct: max_x = 7 * 250, max_y = 6 * 150
- No element overlaps

### Arrow Routing

#### test_elbowed_arrow_routing
**File**: 01_diagram_generation_spec.md → Pseudocode → Elbowed Path Calculation
**Input**: Arrow with `elbowed: true`, source at (0, 0), target at (300, 200)
**Setup**: Call `calculateElbowedPath(sourcePos, targetPos)`
**Expectations**:
- `points.length >= 3` (at least 3 waypoints)
- At least one horizontal segment (constant y)
- At least one vertical segment (constant x)
- Path starts at [0, 0] and ends at [dx, dy]

#### test_binding_focus_calculation
**File**: 01_diagram_generation_spec.md → Pseudocode → Binding Focus Calculation
**Input 1**: Source (0,0), Target (300, 0) [directly right]
**Expectations 1**:
- `binding.focus ≈ 0` (centered on vertical edge)

**Input 2**: Source (0,0), Target (0, 300) [directly below]
**Expectations 2**:
- `binding.focus ≈ 0` (centered on horizontal edge)

**Input 3**: Source (0,0), Target (300, 100) [diagonal]
**Expectations 3**:
- `binding.focus` clamped to [-1, 1]

---

## Module 02: JSON Validation (24 Tests)

### Structural Validation (8 Tests)

#### test_null_document_rejected
**File**: 02_json_validation_spec.md → Pseudocode → Main Validation
**Input**: `null`
**Expectations**:
- `validationResult.isValid === false`
- `errors` contains "Document must be a JSON object"
- `errors.length >= 1`

#### test_missing_type_field
**File**: 02_json_validation_spec.md → Pseudocode → Structural Validation
**Input**: `{ version: 2, source: "...", elements: [], appState: {}, files: {} }`
**Expectations**:
- `errors` contains "Missing required field: type"
- `isValid === false`

#### test_invalid_type_value
**File**: 02_json_validation_spec.md → Pseudocode → Structural Validation
**Input**: `{ type: "foobar", ... }`
**Expectations**:
- `errors` contains "Invalid type. Expected 'excalidraw'"
- `errors.length >= 1`

#### test_valid_schema
**File**: 02_json_validation_spec.md → Pseudocode → Structural Validation
**Input**: Valid minimal document:
```json
{
  "type": "excalidraw",
  "version": 2,
  "source": "electricity-optimizer",
  "elements": [],
  "appState": { "gridSize": null, "viewBackgroundColor": "#ffffff" },
  "files": {}
}
```
**Expectations**:
- `validationResult.isValid === true`
- `errors.length === 0`
- `warnings.length === 0`

#### test_missing_version
**File**: 02_json_validation_spec.md → Edge Cases
**Expectations**: Error about missing/invalid version

#### test_missing_elements
**File**: 02_json_validation_spec.md → Edge Cases
**Expectations**: Error about missing elements array

#### test_missing_appState
**File**: 02_json_validation_spec.md → Edge Cases
**Expectations**: Error about missing appState

#### test_missing_files
**File**: 02_json_validation_spec.md → Edge Cases
**Expectations**: Error about missing files object

### Element Validation (8 Tests)

#### test_duplicate_element_ids
**File**: 02_json_validation_spec.md → Edge Cases → Duplicate Node IDs
**Input**: `elements: [{id: "n1"}, {id: "n1"}]`
**Expectations**:
- `errors` contains "Duplicate element ID: 'n1'"
- Indicates both element indices (0 and 1)

#### test_invalid_element_type
**File**: 02_json_validation_spec.md → Pseudocode → Element Type Validation
**Input**: `{ type: "invalid_type" }`
**Expectations**:
- `errors` contains "invalid type: 'invalid_type'"
- Lists valid types

#### test_missing_element_positions
**File**: 02_json_validation_spec.md → Edge Cases
**Input**: Rectangle without x, y, width, height
**Expectations**:
- 4 errors: one for each missing field
- All 4 errors collected (not fast-fail)

#### test_negative_dimensions
**File**: 02_json_validation_spec.md → Pseudocode → Element Common Fields
**Input**: `{ width: -100 }`
**Expectations**:
- `errors` contains "width cannot be negative"
- Same for height

#### test_out_of_range_seed
**File**: 02_json_validation_spec.md → Edge Cases
**Input**: `{ seed: 3000000000 }`
**Expectations**:
- `errors` contains "seed must be integer in [0, 2000000000]"

#### test_invalid_opacity
**File**: 02_json_validation_spec.md → Pseudocode → Element Common Fields
**Input**: `{ opacity: 150 }`
**Expectations**:
- `errors` contains "opacity must be number in [0, 100]"

#### test_invalid_strokeWidth
**File**: 02_json_validation_spec.md → Edge Cases
**Input**: `{ strokeWidth: -5 }`
**Expectations**:
- `errors` contains "strokeWidth must be non-negative"

#### test_invalid_roughness
**File**: 02_json_validation_spec.md → Edge Cases
**Input**: `{ roughness: 5 }`
**Expectations**:
- `errors` contains "roughness must be number in [0, 3]"

### Binding Validation (5 Tests)

#### test_broken_arrow_binding
**File**: 02_json_validation_spec.md → Pseudocode → Binding Integrity Checker
**Input**: Arrow with `startBinding: { elementId: "nonexistent" }`
**Expectations**:
- `errors` contains "startBinding references non-existent element 'nonexistent'"

#### test_orphaned_bound_element
**File**: 02_json_validation_spec.md → Edge Cases
**Input**: Rectangle with `boundElements: [{id: "ghost_arrow"}]`
**Expectations**:
- `errors` contains "boundElements references non-existent element 'ghost_arrow'"

#### test_bidirectional_consistency
**File**: 02_json_validation_spec.md → Pseudocode → Binding Integrity Checker
**Input**:
```json
{
  "elements": [
    {id: "a1", type: "arrow", startBinding: {elementId: "r1"}},
    {id: "r1", type: "rectangle", boundElements: [{id: "a1", type: "arrow"}]}
  ]
}
```
**Expectations**:
- `isValid === true`
- No binding consistency errors

#### test_text_container_reference
**File**: 02_json_validation_spec.md → Edge Cases
**Input**: Text with `containerId: "nonexistent"`
**Expectations**:
- `errors` contains "containerId references non-existent element 'nonexistent'"

#### test_frame_child_validation
**File**: 02_json_validation_spec.md → Edge Cases
**Input**: Element with `frameId: "nonexistent"`
**Expectations**:
- `errors` contains "frameId references non-existent frame element 'nonexistent'"

### Color & Type Validation (3 Tests)

#### test_valid_hex_colors
**File**: 02_json_validation_spec.md → Edge Cases
**Input**: `#1971c2`, `#a5d8ff`, `#FFFFFF`, `#1971c2aa` (RGBA)
**Expectations**:
- All pass validation (no errors for these colors)

#### test_invalid_hex_colors
**File**: 02_json_validation_spec.md → Pseudocode → Helper Functions
**Input**: `"red"`, `"#GGG"`, `"#1971"`, `"#GGGGGG"`
**Expectations**:
- Each invalid color generates error
- Error mentions valid hex format (#RRGGBB)

#### test_arrow_missing_bindings
**File**: 02_json_validation_spec.md → Pseudocode → Arrow Element Validation
**Input**: Arrow without `startBinding`
**Expectations**:
- `errors` contains "missing required field: startBinding"

---

## Module 03: Layout Engine (18 Tests)

### Grid Layout (5 Tests)

#### test_grid_no_overlaps
**File**: 03_layout_engine_spec.md → Edge Cases → Zero Elements
**Input**: 9 elements in 3×3 grid
**Setup**: Call `gridLayout(elements, config)` with default spacing
**Expectations**:
- For all pairs (i,j): `rectsOverlap(elements[i], elements[j]) === false`
- No element boundary intersections

#### test_grid_column_spacing
**File**: 03_layout_engine_spec.md → Pseudocode → Grid Layout
**Input**: 4 elements with `colSpacing: 250`
**Expectations**:
- Horizontal distance between column centers = 250px
- Actual distance: `col1_x + col1_width/2 - (col2_x - col2_width/2) ≈ 250`

#### test_grid_row_spacing
**File**: 03_layout_engine_spec.md → Pseudocode → Grid Layout
**Input**: 4 elements with `rowSpacing: 150`
**Expectations**:
- Vertical distance between row centers = 150px

#### test_single_element_at_origin
**File**: 03_layout_engine_spec.md → Edge Cases → Single Element
**Input**: 1 element
**Expectations**:
- Element positioned near (0, 0)
- Centered at approximate origin

#### test_grid_dimensions_large
**File**: 03_layout_engine_spec.md → Edge Cases → Large Grid (50+ Elements)
**Input**: 50 elements
**Expectations**:
- `cols = ceil(sqrt(50)) = 8`
- `rows = ceil(50/8) = 7`
- Max x position consistent with 8-column layout
- Max y position consistent with 7-row layout

### Arrow Routing (4 Tests)

#### test_arrow_avoids_elements
**File**: 03_layout_engine_spec.md → Pseudocode → Arrow Routing
**Input**: Arrow A→B, element C positioned between them
**Setup**: `routeArrow(arrowElement, allElements, config)`
**Expectations**:
- Routed path avoids C
- No path segment intersects C.bounds

#### test_elbowed_path_creation
**File**: 03_layout_engine_spec.md → Pseudocode → Elbowed Path Routing
**Input**: Arrow with `elbowed: true`
**Expectations**:
- `points.length >= 3`
- At least one horizontal segment (dy = 0)
- At least one vertical segment (dx = 0)

#### test_self_loop_routing
**File**: 03_layout_engine_spec.md → Edge Cases → Arrow to Same Node
**Input**: Arrow where `source === target`
**Expectations**:
- Path forms loop around element
- `startBinding.elementId === endBinding.elementId`
- Path is elbowed (4+ waypoints for loop)

#### test_straight_path_routing
**File**: 03_layout_engine_spec.md → Pseudocode → Straight Path Routing
**Input**: Arrow with `elbowed: false`
**Expectations**:
- `points.length === 2` (simple start→end)
- Direct line from source to target

### Frame Grouping (3 Tests)

#### test_frame_contains_children
**File**: 03_layout_engine_spec.md → Pseudocode → Frame Grouping
**Input**: 5 elements with `groupId: "services"`
**Expectations**:
- `frame.width >= max(children.width) + 2*padding`
- `frame.height >= max(children.height) + 2*padding`
- Frame left edge <= min(children.x) - padding
- Frame top edge <= min(children.y) - padding

#### test_frame_bounds_children
**File**: 03_layout_engine_spec.md → Edge Cases → Asymmetric Groups
**Input**: 3 child elements at various positions
**Expectations**:
- All children x, y within frame bounds
- All children (x + width) within frame bounds
- All children (y + height) within frame bounds

#### test_nested_frames
**File**: 03_layout_engine_spec.md → Edge Cases → Frame with No Children
**Input**: Elements grouped in frame A, frame A grouped in frame B
**Expectations**:
- `frameB.frameId === null` (root frame)
- `frameA.frameId === null` (root frame, can't contain other frames in this spec)
- All children have correct frameId

### Collision Detection (3 Tests)

#### test_collision_detection_accuracy
**File**: 03_layout_engine_spec.md → Pseudocode → Collision Detection
**Input**: Two overlapping rectangles
**Expectations**:
- `detectCollisions(elements)` returns collision report
- `collision.index1` and `collision.index2` identify overlapping pair
- `collision.overlap` > 0

#### test_no_collision_when_separated
**File**: 03_layout_engine_spec.md → Pseudocode → Collision Detection
**Input**: Two rectangles separated by > gutter distance
**Expectations**:
- `detectCollisions(elements)` returns empty array
- `rectsOverlap()` returns false

#### test_collision_resolution_convergence
**File**: 03_layout_engine_spec.md → Pseudocode → Collision Resolution
**Input**: 10 overlapping elements
**Setup**: Call `resolveCollisions(elements, { maxIterations: 10 })`
**Expectations**:
- Algorithm terminates in < 10 iterations
- Final state has zero collisions
- All elements shifted away from overlaps by at least gutter distance

### Element Sizing (3 Tests)

#### test_element_sizing_from_text
**File**: 03_layout_engine_spec.md → Pseudocode → Element Sizing
**Input**: Element with `label: "Service API"`
**Expectations**:
- `calculateElementWidth(element) > 80` pixels
- Width increases with label length
- "A" → ~50px, "Service API" → ~100px

#### test_default_width_by_type
**File**: 03_layout_engine_spec.md → Pseudocode → Element Sizing
**Input**: Elements of each type (no explicit width)
**Expectations**:
- rectangle → 160px
- ellipse → 120px
- diamond → 120px
- text → auto (based on label)

#### test_long_label_width_expansion
**File**: 03_layout_engine_spec.md → Edge Cases
**Input**: Element with very long label
**Setup**: `calculateElementWidth()` with long text
**Expectations**:
- Width calculated to fit text + padding
- Element dimensions expanded accordingly
- Adjacent elements may be shifted to avoid overlap

---

## Cross-Module Dependencies

### Generation → Validation
- **test_empty_diagram** → **test_valid_schema**: Empty diagram is valid
- **test_single_element** → Element validation tests: Single element passes validation
- **test_arrow_bindings_bidirectional** → **test_bidirectional_consistency**: Bindings must be bidirectional

### Generation → Layout
- **test_grid_layout_9_elements** (Gen) → **test_grid_no_overlaps** (Layout): Grid positions must have no overlaps
- **test_elbowed_arrow_routing** (Gen) → **test_elbowed_path_creation** (Layout): Elbowed paths must have 3+ points

### Layout → Validation
- **test_collision_resolution_convergence** → **test_no_overlaps_grid_layout**: Resolved layout must pass overlap check
- All layout output must pass **test_valid_schema** validation

---

## Test Execution Order (Recommended)

### Phase 1: Generation Tests
1. test_empty_diagram
2. test_single_element
3. test_no_overlaps_grid_layout
4. test_large_grid_layout
5. test_arrow_bindings_bidirectional
6. test_text_in_container
7. test_elbowed_arrow_routing
8. test_binding_focus_calculation
9. test_duplicate_node_ids_throws
10. test_invalid_node_type_throws
11. test_self_loop_creates_arrow
12. test_missing_target_node_creates_arrow_anyway

### Phase 2: Validation Tests
1. test_null_document_rejected
2. test_valid_schema
3. test_missing_type_field
4. test_invalid_type_value
5. test_missing_version
6. test_missing_elements
7. test_missing_appState
8. test_missing_files
9. test_duplicate_element_ids
10. test_invalid_element_type
11. test_missing_element_positions
12. test_negative_dimensions
13. test_out_of_range_seed
14. test_invalid_opacity
15. test_invalid_strokeWidth
16. test_invalid_roughness
17. test_broken_arrow_binding
18. test_orphaned_bound_element
19. test_bidirectional_consistency
20. test_text_container_reference
21. test_frame_child_validation
22. test_valid_hex_colors
23. test_invalid_hex_colors
24. test_arrow_missing_bindings

### Phase 3: Layout Tests
1. test_grid_no_overlaps
2. test_grid_column_spacing
3. test_grid_row_spacing
4. test_single_element_at_origin
5. test_grid_dimensions_large
6. test_arrow_avoids_elements
7. test_elbowed_path_creation
8. test_self_loop_routing
9. test_straight_path_routing
10. test_frame_contains_children
11. test_frame_bounds_children
12. test_nested_frames
13. test_collision_detection_accuracy
14. test_no_collision_when_separated
15. test_collision_resolution_convergence
16. test_element_sizing_from_text
17. test_default_width_by_type
18. test_long_label_width_expansion

---

## Quick Test Count Summary

| Module | Count | Status |
|--------|-------|--------|
| 01_diagram_generation_spec.md | 12 | Ready |
| 02_json_validation_spec.md | 24 | Ready |
| 03_layout_engine_spec.md | 18 | Ready |
| **TOTAL** | **54** | **Ready for Implementation** |

---

**Test Anchor Reference Status**: Complete
**Last Updated**: 2026-02-26
**Ready for TDD Implementation**: Yes
