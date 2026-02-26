# Excalidraw JSON Validation Specification

## Overview

Schema validation, binding integrity checking, and data consistency verification for .excalidraw JSON documents. Ensures all generated and imported diagrams meet Excalidraw specification requirements before serialization or display.

**Target File Size**: < 500 lines
**Language**: Pseudocode (language-agnostic)
**Test Framework**: Jest/Vitest with JSON schema mock validation

---

## Requirements

### Functional Requirements

1. **Schema Validation**
   - Verify document structure: required root fields (type, version, source, elements, appState, files)
   - Validate element types: rectangle, ellipse, diamond, arrow, text, line, freedraw, image, frame
   - Check required element properties: id, type, x, y, width, height, version, seed
   - Enforce type constraints: x/y/width/height are numbers, id is string, version is integer >= 1

2. **Element Type Checking**
   - Validate element-specific properties (e.g., arrows must have startBinding/endBinding)
   - Verify text elements have text/originalText fields
   - Check frame elements have proper boundaries
   - Validate color fields are hex strings (format: #RRGGBB)

3. **Binding Integrity**
   - Every arrow.startBinding.elementId must exist in elements array
   - Every arrow.endBinding.elementId must exist in elements array
   - Every boundElements reference must point to a valid element ID
   - Bidirectional consistency: if arrow A binds to element B, then B.boundElements must include A.id

4. **Duplicate Detection**
   - Identify duplicate element IDs (must be unique per document)
   - Detect orphaned boundElements references (point to non-existent elements)
   - Check for circular boundElements references (A→B→C→A)

5. **Data Consistency**
   - Validate appState fields: gridSize (number|null), viewBackgroundColor (hex string)
   - Verify files object maps imageId → valid file entry
   - Ensure no elements reference non-existent frameId
   - Check opacity values are in range [0, 100]

### Validation Scopes

```plaintext
Level 1: Structural Validation (Schema)
  - Document shape (root fields)
  - Array bounds
  - Type checking

Level 2: Element Validation (Element Properties)
  - All required fields present
  - Value ranges and formats
  - Type-specific constraints

Level 3: Binding Validation (Cross-Element References)
  - Arrow bindings reference valid elements
  - BoundElements consistency
  - No orphaned references

Level 4: Semantic Validation (Domain Logic)
  - No duplicate IDs
  - No circular dependencies in frames
  - Consistent color palette
```

---

## Pseudocode

### 1. Main Validation Function

```
FUNCTION validateExcalidrawDocument(
  document: Record<string, any>
): ValidationResult

  INPUT: Parsed .excalidraw JSON document
  OUTPUT: ValidationResult { isValid: bool, errors: Error[], warnings: Warning[] }

  errors ← []
  warnings ← []

  // Level 1: Structural validation
  structuralErrors ← validateStructure(document)
  EXTEND errors WITH structuralErrors

  IF errors.length > 0
    RETURN { isValid: false, errors, warnings }

  // Level 2: Element validation
  elementErrors ← validateElements(document.elements)
  EXTEND errors WITH elementErrors

  // Level 3: Binding validation
  bindingErrors ← validateBindings(document.elements)
  EXTEND errors WITH bindingErrors

  // Level 4: Semantic validation
  semanticWarnings ← validateSemantics(document.elements)
  EXTEND warnings WITH semanticWarnings

  isValid ← errors.length == 0

  RETURN {
    isValid: isValid,
    errors: errors,
    warnings: warnings
  }
END FUNCTION
```

### 2. Structural Validation

```
FUNCTION validateStructure(document: Record<string, any>): Array<ValidationError>

  OUTPUT: List of structural validation errors

  errors ← []

  // Check root fields
  IF document IS NULL OR document IS NOT object
    APPEND ValidationError("Document must be a JSON object") TO errors
    RETURN errors

  IF NOT hasProperty(document, "type")
    APPEND ValidationError("Missing required field: type") TO errors
  ELSE IF document.type != "excalidraw"
    APPEND ValidationError("Invalid type. Expected 'excalidraw', got '" + document.type + "'") TO errors

  IF NOT hasProperty(document, "version")
    APPEND ValidationError("Missing required field: version") TO errors
  ELSE IF document.version != 2
    APPEND ValidationError("Unsupported version. Expected 2, got " + document.version) TO errors

  IF NOT hasProperty(document, "source")
    APPEND ValidationError("Missing required field: source") TO errors
  ELSE IF typeof document.source != "string"
    APPEND ValidationError("Field 'source' must be a string") TO errors

  // Validate elements array
  IF NOT hasProperty(document, "elements")
    APPEND ValidationError("Missing required field: elements") TO errors
  ELSE IF NOT isArray(document.elements)
    APPEND ValidationError("Field 'elements' must be an array") TO errors

  // Validate appState
  IF NOT hasProperty(document, "appState")
    APPEND ValidationError("Missing required field: appState") TO errors
  ELSE
    appStateErrors ← validateAppState(document.appState)
    EXTEND errors WITH appStateErrors

  // Validate files
  IF NOT hasProperty(document, "files")
    APPEND ValidationError("Missing required field: files") TO errors
  ELSE IF typeof document.files != "object" OR isArray(document.files)
    APPEND ValidationError("Field 'files' must be a JSON object") TO errors

  RETURN errors
END FUNCTION
```

### 3. App State Validation

```
FUNCTION validateAppState(appState: Record<string, any>): Array<ValidationError>

  OUTPUT: List of appState-specific errors

  errors ← []

  IF typeof appState != "object"
    APPEND ValidationError("appState must be a JSON object") TO errors
    RETURN errors

  // gridSize validation: number | null
  IF hasProperty(appState, "gridSize")
    IF appState.gridSize IS NOT NULL AND typeof appState.gridSize != "number"
      APPEND ValidationError("appState.gridSize must be number or null") TO errors

  // viewBackgroundColor validation: hex string
  IF hasProperty(appState, "viewBackgroundColor")
    IF NOT isValidHexColor(appState.viewBackgroundColor)
      APPEND ValidationError("appState.viewBackgroundColor must be valid hex (#RRGGBB)") TO errors

  RETURN errors
END FUNCTION
```

### 4. Element Validation

```
FUNCTION validateElements(elements: Array<any>): Array<ValidationError>

  OUTPUT: List of element-level validation errors

  errors ← []

  IF NOT isArray(elements)
    APPEND ValidationError("elements must be an array") TO errors
    RETURN errors

  elementIds ← Set()

  FOR each element AT index IN elements
    // Basic structure
    IF typeof element != "object"
      APPEND ValidationError("Element[" + index + "] must be a JSON object") TO errors
      CONTINUE

    // ID validation
    elementErrors ← validateElementId(element, index)
    EXTEND errors WITH elementErrors

    IF hasProperty(element, "id") AND typeof element.id == "string"
      IF elementIds.contains(element.id)
        APPEND ValidationError(
          "Duplicate element ID: '" + element.id + "' at index " + index
        ) TO errors
      ELSE
        elementIds.add(element.id)

    // Type and type-specific validation
    IF NOT hasProperty(element, "type")
      APPEND ValidationError("Element[" + index + "] missing required field: type") TO errors
      CONTINUE

    elementTypeErrors ← validateElementType(element, index)
    EXTEND errors WITH elementTypeErrors

  RETURN errors
END FUNCTION
```

### 5. Element ID Validation

```
FUNCTION validateElementId(element: Record<string, any>, index: number): Array<ValidationError>

  OUTPUT: ID-specific validation errors

  errors ← []

  IF NOT hasProperty(element, "id")
    APPEND ValidationError("Element[" + index + "] missing required field: id") TO errors
  ELSE
    IF typeof element.id != "string"
      APPEND ValidationError("Element[" + index + "].id must be string, got " + typeof element.id) TO errors
    ELSE IF element.id.length == 0
      APPEND ValidationError("Element[" + index + "].id cannot be empty string") TO errors
    ELSE IF NOT matchesPattern(element.id, "^[a-zA-Z0-9_-]+$")
      APPEND ValidationError(
        "Element[" + index + "].id contains invalid characters. Use alphanumeric, underscore, hyphen only."
      ) TO errors

  RETURN errors
END FUNCTION
```

### 6. Element Type Validation

```
FUNCTION validateElementType(element: Record<string, any>, index: number): Array<ValidationError>

  OUTPUT: Type-specific validation errors

  errors ← []
  elementType ← element.type

  // Validate type is known
  validTypes ← ["rectangle", "ellipse", "diamond", "arrow", "text", "line", "freedraw", "image", "frame"]
  IF NOT validTypes.contains(elementType)
    APPEND ValidationError("Element[" + index + "] invalid type: '" + elementType + "'") TO errors
    RETURN errors

  // Validate common required fields
  commonErrors ← validateElementCommonFields(element, index)
  EXTEND errors WITH commonErrors

  // Type-specific validation
  IF elementType == "arrow"
    arrowErrors ← validateArrowElement(element, index)
    EXTEND errors WITH arrowErrors
  ELSE IF elementType == "text"
    textErrors ← validateTextElement(element, index)
    EXTEND errors WITH textErrors
  ELSE IF elementType == "image"
    imageErrors ← validateImageElement(element, index)
    EXTEND errors WITH imageErrors
  ELSE IF elementType == "frame"
    frameErrors ← validateFrameElement(element, index)
    EXTEND errors WITH frameErrors

  RETURN errors
END FUNCTION
```

### 7. Common Element Fields Validation

```
FUNCTION validateElementCommonFields(
  element: Record<string, any>,
  index: number
): Array<ValidationError>

  OUTPUT: Validation errors for fields all elements share

  errors ← []

  // Position and size (not required for text in containers)
  IF element.type != "text" OR NOT hasProperty(element, "containerId")
    FOR field IN ["x", "y", "width", "height"]
      IF NOT hasProperty(element, field)
        APPEND ValidationError("Element[" + index + "] missing required field: " + field) TO errors
      ELSE IF typeof element[field] != "number"
        APPEND ValidationError("Element[" + index + "]." + field + " must be number") TO errors
      ELSE IF element[field] < 0 AND field IN ["width", "height"]
        APPEND ValidationError("Element[" + index + "]." + field + " cannot be negative") TO errors

  // Version
  IF NOT hasProperty(element, "version")
    APPEND ValidationError("Element[" + index + "] missing required field: version") TO errors
  ELSE IF typeof element.version != "number" OR element.version < 1
    APPEND ValidationError("Element[" + index + "].version must be integer >= 1") TO errors

  // Seed
  IF NOT hasProperty(element, "seed")
    APPEND ValidationError("Element[" + index + "] missing required field: seed") TO errors
  ELSE IF typeof element.seed != "number" OR element.seed < 0 OR element.seed > 2000000000
    APPEND ValidationError("Element[" + index + "].seed must be integer in [0, 2000000000]") TO errors

  // Optional numeric fields with range constraints
  IF hasProperty(element, "opacity")
    IF typeof element.opacity != "number" OR element.opacity < 0 OR element.opacity > 100
      APPEND ValidationError("Element[" + index + "].opacity must be number in [0, 100]") TO errors

  IF hasProperty(element, "strokeWidth")
    IF typeof element.strokeWidth != "number" OR element.strokeWidth < 0
      APPEND ValidationError("Element[" + index + "].strokeWidth must be non-negative number") TO errors

  IF hasProperty(element, "roughness")
    IF typeof element.roughness != "number" OR element.roughness < 0 OR element.roughness > 3
      APPEND ValidationError("Element[" + index + "].roughness must be number in [0, 3]") TO errors

  // Color validation
  IF hasProperty(element, "strokeColor")
    IF NOT isValidHexColor(element.strokeColor)
      APPEND ValidationError("Element[" + index + "].strokeColor must be valid hex (#RRGGBB)") TO errors

  IF hasProperty(element, "backgroundColor")
    IF element.backgroundColor != "transparent" AND NOT isValidHexColor(element.backgroundColor)
      APPEND ValidationError("Element[" + index + "].backgroundColor must be 'transparent' or valid hex") TO errors

  RETURN errors
END FUNCTION
```

### 8. Arrow Element Validation

```
FUNCTION validateArrowElement(element: Record<string, any>, index: number): Array<ValidationError>

  OUTPUT: Arrow-specific validation errors

  errors ← []

  // Required fields
  FOR field IN ["startBinding", "endBinding"]
    IF NOT hasProperty(element, field)
      APPEND ValidationError("Arrow element[" + index + "] missing required field: " + field) TO errors
    ELSE
      IF typeof element[field] != "object" OR element[field] IS NULL
        APPEND ValidationError("Arrow element[" + index + "]." + field + " must be an object") TO errors
      ELSE
        IF NOT hasProperty(element[field], "elementId")
          APPEND ValidationError("Binding[" + field + "] missing elementId") TO errors
        ELSE IF typeof element[field].elementId != "string"
          APPEND ValidationError("Binding[" + field + "].elementId must be string") TO errors

        IF hasProperty(element[field], "focus")
          IF typeof element[field].focus != "number" OR element[field].focus < -1 OR element[field].focus > 1
            APPEND ValidationError("Binding[" + field + "].focus must be number in [-1, 1]") TO errors

        IF hasProperty(element[field], "gap")
          IF typeof element[field].gap != "number" OR element[field].gap < 0
            APPEND ValidationError("Binding[" + field + "].gap must be non-negative number") TO errors

  // Points array
  IF hasProperty(element, "points")
    IF NOT isArray(element.points)
      APPEND ValidationError("Arrow element[" + index + "].points must be array") TO errors
    ELSE IF element.points.length < 2
      APPEND ValidationError("Arrow element[" + index + "].points must have at least 2 points") TO errors
    ELSE
      FOR point AT i IN element.points
        IF NOT isArray(point) OR point.length != 2
          APPEND ValidationError("Points[" + i + "] must be [x, y] pair") TO errors
        ELSE IF typeof point[0] != "number" OR typeof point[1] != "number"
          APPEND ValidationError("Points[" + i + "] coordinates must be numbers") TO errors

  RETURN errors
END FUNCTION
```

### 9. Text Element Validation

```
FUNCTION validateTextElement(element: Record<string, any>, index: number): Array<ValidationError>

  OUTPUT: Text-specific validation errors

  errors ← []

  // Text content (one required)
  hasText ← hasProperty(element, "text") AND typeof element.text == "string"
  hasOriginalText ← hasProperty(element, "originalText") AND typeof element.originalText == "string"

  IF NOT hasText AND NOT hasOriginalText
    APPEND ValidationError("Text element[" + index + "] must have 'text' or 'originalText' field") TO errors

  // Font properties
  IF hasProperty(element, "fontFamily")
    IF typeof element.fontFamily != "number" OR element.fontFamily < 1 OR element.fontFamily > 3
      APPEND ValidationError("Text element[" + index + "].fontFamily must be 1-3 (Virgil, Helvetica, Cascadia)") TO errors

  IF hasProperty(element, "fontSize")
    IF typeof element.fontSize != "number" OR element.fontSize <= 0
      APPEND ValidationError("Text element[" + index + "].fontSize must be positive number") TO errors

  // Text alignment
  IF hasProperty(element, "textAlign")
    validAligns ← ["left", "center", "right"]
    IF NOT validAligns.contains(element.textAlign)
      APPEND ValidationError("Text element[" + index + "].textAlign must be 'left', 'center', or 'right'") TO errors

  IF hasProperty(element, "verticalAlign")
    validVAligns ← ["top", "middle", "bottom"]
    IF NOT validVAligns.contains(element.verticalAlign)
      APPEND ValidationError("Text element[" + index + "].verticalAlign must be 'top', 'middle', or 'bottom'") TO errors

  // Container linking
  IF hasProperty(element, "containerId") AND element.containerId IS NOT NULL
    IF typeof element.containerId != "string" OR element.containerId.length == 0
      APPEND ValidationError("Text element[" + index + "].containerId must be valid element ID string or null") TO errors

  RETURN errors
END FUNCTION
```

### 10. Binding Integrity Checker

```
FUNCTION validateBindings(elements: Array<Record<string, any>>): Array<ValidationError>

  OUTPUT: Cross-element binding validation errors

  errors ← []

  // Build ID lookup map
  elementIdMap ← {}
  FOR element IN elements
    IF hasProperty(element, "id")
      elementIdMap[element.id] ← element

  // Validate arrow bindings
  FOR element IN elements
    IF element.type == "arrow"
      IF hasProperty(element, "startBinding") AND hasProperty(element.startBinding, "elementId")
        sourceId ← element.startBinding.elementId
        IF NOT elementIdMap.hasKey(sourceId)
          APPEND ValidationError(
            "Arrow '" + element.id + "' startBinding references non-existent element '" + sourceId + "'"
          ) TO errors

      IF hasProperty(element, "endBinding") AND hasProperty(element.endBinding, "elementId")
        targetId ← element.endBinding.elementId
        IF NOT elementIdMap.hasKey(targetId)
          APPEND ValidationError(
            "Arrow '" + element.id + "' endBinding references non-existent element '" + targetId + "'"
          ) TO errors

  // Validate bidirectional consistency
  FOR element IN elements
    IF hasProperty(element, "boundElements") AND isArray(element.boundElements)
      FOR boundRef IN element.boundElements
        IF NOT hasProperty(boundRef, "id")
          APPEND ValidationError("BoundElements entry missing 'id' field") TO errors
        ELSE
          refId ← boundRef.id
          IF NOT elementIdMap.hasKey(refId)
            APPEND ValidationError(
              "Element '" + element.id + "' boundElements references non-existent element '" + refId + "'"
            ) TO errors

  // Validate text containerId references
  FOR element IN elements
    IF element.type == "text" AND hasProperty(element, "containerId") AND element.containerId IS NOT NULL
      containerId ← element.containerId
      IF NOT elementIdMap.hasKey(containerId)
        APPEND ValidationError(
          "Text element '" + element.id + "' containerId references non-existent element '" + containerId + "'"
        ) TO errors

  // Validate frameId references (not required, but if present must be valid)
  FOR element IN elements
    IF hasProperty(element, "frameId") AND element.frameId IS NOT NULL
      frameId ← element.frameId
      IF NOT elementIdMap.hasKey(frameId)
        APPEND ValidationError(
          "Element '" + element.id + "' frameId references non-existent frame element '" + frameId + "'"
        ) TO errors

  RETURN errors
END FUNCTION
```

### 11. Duplicate Element ID Detector

```
FUNCTION findDuplicateIds(elements: Array<Record<string, any>>): Array<DuplicateIdReport>

  OUTPUT: List of duplicate ID reports (informational, not errors)

  idMap ← {}  // { id → [index1, index2, ...] }

  FOR element AT index IN elements
    IF hasProperty(element, "id")
      id ← element.id
      IF NOT idMap.hasKey(id)
        idMap[id] ← []
      idMap[id].append(index)

  duplicates ← []
  FOR id, indices IN idMap
    IF indices.length > 1
      duplicates.append({
        id: id,
        count: indices.length,
        elementIndices: indices
      })

  RETURN duplicates
END FUNCTION
```

### 12. Helper Functions

```
FUNCTION isValidHexColor(color: string): bool
  // Valid hex: #RRGGBB or #RRGGBBAA
  RETURN matchesPattern(color, "^#[0-9a-fA-F]{6}([0-9a-fA-F]{2})?$")
END FUNCTION

FUNCTION isArray(value: any): bool
  RETURN typeof value == "object" AND value IS NOT NULL AND value.length >= 0
END FUNCTION

FUNCTION hasProperty(obj: Record<string, any>, prop: string): bool
  RETURN prop IN obj AND obj[prop] IS NOT UNDEFINED
END FUNCTION

FUNCTION matchesPattern(str: string, pattern: string): bool
  // Uses regex matching, language-specific implementation
  RETURN REGEX(pattern).test(str)
END FUNCTION
```

---

## Edge Cases

### 1. Null Document
- **Input**: `null`
- **Output**: Error "Document must be a JSON object"
- **Test**: `test_null_document_rejected()`

### 2. Missing All Required Fields
- **Input**: `{}`
- **Output**: 6 errors (type, version, source, elements, appState, files)
- **Test**: `test_missing_all_required_fields()`

### 3. Valid Minimal Document
- **Input**: `{ type: "excalidraw", version: 2, source: "app", elements: [], appState: { gridSize: null, viewBackgroundColor: "#ffffff" }, files: {} }`
- **Output**: Valid, no errors
- **Test**: `test_minimal_valid_document()`

### 4. Broken Arrow Binding
- **Input**: Arrow with startBinding.elementId = "nonexistent"
- **Output**: Error "Arrow ... startBinding references non-existent element"
- **Test**: `test_broken_arrow_binding()`

### 5. Orphaned BoundElements Reference
- **Input**: Rectangle with boundElements: [{id: "ghost_arrow"}]
- **Output**: Error "boundElements references non-existent element"
- **Test**: `test_orphaned_bound_element()`

### 6. Bidirectional Binding Mismatch
- **Input**: Arrow {id: "a1", startBinding: {elementId: "r1"}}, Rectangle {id: "r1", boundElements: []}
- **Output**: Warning (soft error, depends on validator strictness)
- **Test**: `test_bidirectional_mismatch_warning()`

### 7. Circular Frame References
- **Input**: Frame1.frameId = Frame2.id, Frame2.frameId = Frame1.id
- **Output**: Warning about circular nesting (not an error, but invalid)
- **Test**: `test_circular_frame_nesting()`

### 8. Invalid Hex Colors
- **Input**: `{ strokeColor: "red" }` or `{ backgroundColor: "#GGG" }`
- **Output**: Error "must be valid hex (#RRGGBB)"
- **Test**: `test_invalid_hex_colors()`

### 9. Out-of-Range Opacity
- **Input**: `{ opacity: 150 }`
- **Output**: Error "opacity must be number in [0, 100]"
- **Test**: `test_out_of_range_opacity()`

### 10. Multiple Errors in Single Element
- **Input**: Element with missing id, invalid type, negative width, invalid opacity
- **Output**: All 4 errors collected
- **Test**: `test_multiple_errors_single_element()`

---

## TDD Test Anchors

### Structural Tests

```
test_null_document_rejected()
  GIVEN: null
  EXPECT: ValidationResult.isValid == false
  EXPECT: errors contains "Document must be a JSON object"

test_missing_type_field()
  GIVEN: document without 'type' field
  EXPECT: errors contains "Missing required field: type"

test_invalid_type_value()
  GIVEN: { type: "foobar" }
  EXPECT: errors contains "Invalid type. Expected 'excalidraw'"

test_valid_schema()
  GIVEN: valid minimal document
  EXPECT: ValidationResult.isValid == true
  EXPECT: errors.length == 0
```

### Element Validation Tests

```
test_duplicate_element_ids()
  GIVEN: elements [{id: "n1"}, {id: "n1"}]
  EXPECT: errors contains "Duplicate element ID: 'n1'"

test_invalid_element_type()
  GIVEN: { type: "invalid_type" }
  EXPECT: errors contains "invalid type: 'invalid_type'"

test_missing_element_positions()
  GIVEN: Rectangle without x, y, width, height
  EXPECT: 4 errors (one per field)

test_negative_dimensions()
  GIVEN: { width: -100 }
  EXPECT: errors contains "width cannot be negative"

test_out_of_range_seed()
  GIVEN: { seed: 3000000000 }
  EXPECT: errors contains "seed must be integer in [0, 2000000000]"
```

### Binding Tests

```
test_broken_arrow_binding()
  GIVEN: Arrow { startBinding: { elementId: "nonexistent" } }
  EXPECT: errors contains "startBinding references non-existent element 'nonexistent'"

test_orphaned_bound_element()
  GIVEN: Rectangle { boundElements: [{id: "ghost"}] }
  EXPECT: errors contains "boundElements references non-existent element 'ghost'"

test_bidirectional_consistency()
  GIVEN: Arrow {id: "a1"}, Rectangle {id: "r1"}
    Arrow.startBinding.elementId = "r1"
    Rectangle.boundElements = [{id: "a1"}]
  EXPECT: isValid == true
  EXPECT: No binding consistency errors

test_arrow_to_self_loop()
  GIVEN: Arrow { id: "a1", startBinding: {elementId: "a1"}, endBinding: {elementId: "a1"} }
  EXPECT: errors empty (self-loop valid)
```

### Type-Specific Tests

```
test_arrow_missing_bindings()
  GIVEN: Arrow without startBinding
  EXPECT: errors contains "missing required field: startBinding"

test_text_missing_content()
  GIVEN: Text { text: undefined, originalText: undefined }
  EXPECT: errors contains "must have 'text' or 'originalText'"

test_text_valid_alignment()
  GIVEN: Text { textAlign: "center" }
  EXPECT: No alignment errors

test_text_invalid_alignment()
  GIVEN: Text { textAlign: "justified" }
  EXPECT: errors contains "textAlign must be 'left', 'center', or 'right'"

test_image_element_validation()
  GIVEN: Image element with valid fileId reference
  EXPECT: (if fileId exists in document.files) validation passes
```

### Color and Style Tests

```
test_valid_hex_colors()
  GIVEN: #1971c2, #a5d8ff, #FFFFFF
  EXPECT: All pass validation

test_invalid_hex_colors()
  GIVEN: "red", "#GGG", "#1971", "#GGGGGG"
  EXPECT: errors for each invalid color

test_transparent_background()
  GIVEN: { backgroundColor: "transparent" }
  EXPECT: No validation error

test_opacity_edge_cases()
  GIVEN: opacity = 0, 50, 100
  EXPECT: All valid
  GIVEN: opacity = -1, 101
  EXPECT: Both invalid
```

### Semantic Tests

```
test_frame_child_validation()
  GIVEN: Element with frameId referencing non-existent frame
  EXPECT: errors contains "frameId references non-existent frame"

test_text_container_validation()
  GIVEN: Text { containerId: "nonexistent" }
  EXPECT: errors contains "containerId references non-existent element"

test_no_circular_frame_nesting()
  GIVEN: Frame1 nested in Frame2 nested in Frame1
  EXPECT: Warning (depends on validator level)
```

---

## Implementation Notes

- **Error Accumulation**: Collect all errors before returning, not just first error (batch reporting)
- **Validation Levels**: Can be strict (all errors) or lenient (stop on first critical error)
- **Hex Color Regex**: `^#[0-9a-fA-F]{6}([0-9a-fA-F]{2})?$` (supports RGB and RGBA)
- **ID Pattern**: `^[a-zA-Z0-9_-]+$` (alphanumeric, underscore, hyphen only)
- **Context Preservation**: Include element indices and field names in error messages for debugging
- **Recovery**: Validator doesn't modify input; only reports findings
- **Extensibility**: Can add custom validators via plugin interface

---

## Related Specifications

- **[01_diagram_generation_spec.md](01_diagram_generation_spec.md)** — Generator that produces validated JSON
- **[03_layout_engine_spec.md](03_layout_engine_spec.md)** — Layout-specific constraints and validation
- **[README.md](README.md)** — Specification suite overview and architecture
- **[IMPLEMENTATION_GUIDE.md](IMPLEMENTATION_GUIDE.md)** — Development roadmap (Phase 2)

## Related Documentation

- **[User Guide](../../excalidraw-agent-guide.md)** — How to invoke excalidraw-expert agent
- **[API Reference](../../excalidraw-reference.md)** — Components, hooks, and API routes
- **[Agent Definition](/Users/devinmcgrath/.claude/agents/excalidraw-expert.md)** — Agent specification

---

**Authored**: 2026-02-26
**Version**: 1.0
**Status**: Ready for Implementation
