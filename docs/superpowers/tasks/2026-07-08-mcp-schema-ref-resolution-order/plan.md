# MCP Schema $ref Sibling-Order Fix — Regression Tests — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Lock in the fix for `TypeError: Cannot find Pydantic type $ref schema fragment` when an MCP tool's JSON Schema `$defs` map has a definition that references a sibling definition declared later in the same `$defs` object (the `assignBadges` / `BadgeAssignmentImportEntry` → `Ref` shape), with regression tests that fail on the old single-pass implementation and pass on the current two-pass implementation.

**Architecture:** `src/codemie/core/json_schema_utils.py::_process_definitions` already implements a two-pass fix (uncommitted, on branch `EPMCDME-13328_mcp-schema-ref-resolution-order`): pass 1 pre-registers every `$defs`/`definitions` key as `Any`; pass 2 builds each definition for real. This plan adds the missing regression tests and verifies (without production changes) that self-referential `$defs` entries are not newly broken by the fix.

**Tech Stack:** Python, pytest, Pydantic v2. No new dependencies.

## Global Constraints

- Ticket: `EPMCDME-13328`. Commit messages must use `EPMCDME-13328: Description`.
- Branch: `EPMCDME-13328_mcp-schema-ref-resolution-order` (already checked out).
- No production code changes are in scope unless Task 2 reveals an actual behavioral regression caused by the two-pass fix (see Task 2 Step 6 for the verification and the reasoning for why none is expected).
- Follow the existing per-scenario test-file convention under `tests/codemie/core/`.

---

### Task 1: Regression test for sibling-order `$defs` resolution (the reported bug)

**Files:**
- Modify: `tests/codemie/core/test_json_schema_ref_type.py` (append new schema constants + test function at end of file, after `test_json_schema_properties_ref_to_ref`)
- Read-only reference: `src/codemie/core/json_schema_utils.py:203-236` (`_process_definitions`, already fixed)

**Interfaces:**
- Consumes: `_create_model_from_schema(model_name: str, schema: dict, cache: Cache) -> type[BaseModel]` and `Cache` (both already imported in this file: `from codemie.core.json_schema_utils import _create_model_from_schema, Cache`). `get_type_hints` already imported from `typing`.
- Produces: nothing consumed by later tasks — this test is self-contained.

**Test-first: yes — the new test must raise `TypeError: Cannot find Pydantic type $ref schema fragment` when run against the pre-fix single-pass `_process_definitions`, and pass against the current two-pass implementation.**

- [ ] **Step 1: Append the regression test to `tests/codemie/core/test_json_schema_ref_type.py`**

Append this to the end of the file (after the existing `test_json_schema_properties_ref_to_ref` function, keeping one blank line of separation from the last line):

```python

JSON_SCHEMA_WITH_DEFS_FORWARD_SIBLING_REF = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "name": "assignBadges",
    "inputSchema": {
        "type": "object",
        "$defs": {
            "BadgeAssignmentImportEntry": {
                "type": "object",
                "required": ["assigner", "badge"],
                "properties": {
                    "assigner": {"$ref": "#/$defs/Ref"},
                    "badge": {"$ref": "#/$defs/Ref"},
                },
                "additionalProperties": False,
            },
            "Ref": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "url": {"type": "string"},
                },
                "additionalProperties": False,
            },
        },
        "properties": {
            "singleEntries": {
                "type": "array",
                "items": {"$ref": "#/$defs/BadgeAssignmentImportEntry"},
            }
        },
        "required": ["singleEntries"],
        "additionalProperties": False,
    },
}

JSON_SCHEMA_WITH_DEFS_FORWARD_SIBLING_REF_INPUT = {
    "singleEntries": [
        {
            "assigner": {"id": "u-1", "url": "https://example.com/u-1"},
            "badge": {"id": "b-1", "url": "https://example.com/b-1"},
        }
    ]
}


def test_json_schema_defs_sibling_ref_resolves_regardless_of_declaration_order():
    """BadgeAssignmentImportEntry (declared first in $defs) references Ref (declared
    second) via $ref -- must resolve without raising TypeError, regardless of dict
    iteration order. Reproduces the reported assignBadges MCP tool load failure."""
    cache = Cache()
    model = _create_model_from_schema(
        "Test", JSON_SCHEMA_WITH_DEFS_FORWARD_SIBLING_REF["inputSchema"], cache
    )

    data = model(**JSON_SCHEMA_WITH_DEFS_FORWARD_SIBLING_REF_INPUT)
    extracted = data.model_dump()
    assert json.dumps(extracted) == json.dumps(JSON_SCHEMA_WITH_DEFS_FORWARD_SIBLING_REF_INPUT)

    ref_model = cache.get_model_by_path("#/$defs/Ref")
    assert ref_model is not None, "Ref model not found in cache"

    entry_model = cache.get_model_by_path("#/$defs/BadgeAssignmentImportEntry")
    assert entry_model is not None, "BadgeAssignmentImportEntry model not found in cache"

    assigner_type = get_type_hints(entry_model)["assigner"]
    assert assigner_type is ref_model, "assigner should resolve to the Ref model, not Any or a raised error"
```

- [ ] **Step 2: Confirm the test fails against the pre-fix single-pass implementation (RED)**

Temporarily stash the already-applied fix (it is uncommitted, so this is safe and reversible):

```bash
git stash push -- src/codemie/core/json_schema_utils.py
pytest tests/codemie/core/test_json_schema_ref_type.py::test_json_schema_defs_sibling_ref_resolves_regardless_of_declaration_order -v
```

Expected: FAIL with `TypeError: Cannot find Pydantic type $ref schema fragment (name='...'): {'$ref': '#/$defs/Ref'}`.

- [ ] **Step 3: Restore the fix and confirm the test passes (GREEN)**

```bash
git stash pop
pytest tests/codemie/core/test_json_schema_ref_type.py::test_json_schema_defs_sibling_ref_resolves_regardless_of_declaration_order -v
```

Expected: PASS.

- [ ] **Step 4: Run the full test file to confirm no existing tests broke**

```bash
pytest tests/codemie/core/test_json_schema_ref_type.py -v
```

Expected: all 4 tests PASS (3 existing + 1 new).

- [ ] **Step 5: Commit**

```bash
git add tests/codemie/core/test_json_schema_ref_type.py
git commit -m "EPMCDME-13328: Add regression test for \$defs sibling forward-reference resolution"
```

(This task does not commit `src/codemie/core/json_schema_utils.py` yet — that happens in Task 3 alongside the second regression test, to keep the fix and its full test coverage in one reviewable unit. If you prefer committing the already-applied production fix now, do it in this step instead with message `EPMCDME-13328: Fix \$defs sibling forward-reference resolution order` — either grouping is acceptable, just be consistent with Task 3.)

---

### Task 2: Regression test for self-referential `$defs` entries (no mocking, real code path)

**Files:**
- Modify: `tests/codemie/core/test_json_schema_recursive.py` (update the import line, append new test function at end of file)

**Interfaces:**
- Consumes: `json_schema_to_model(schema: dict) -> type[BaseModel]` (add to the existing import line).
- Produces: nothing consumed by later tasks.

**Test-first: yes — this test exercises the real `json_schema_to_model` function (all 7 existing tests in this file mock it out entirely) to lock in current, correct behavior for self-referential `$defs` entries. It documents a known pre-existing limitation (see Step 1 docstring) that is unchanged by the two-pass fix — the test should pass immediately once written, with no production code change.**

- [ ] **Step 1: Update the import line in `tests/codemie/core/test_json_schema_recursive.py`**

Change line 21 from:

```python
from codemie.core.json_schema_utils import model_to_string
```

to:

```python
from codemie.core.json_schema_utils import json_schema_to_model, model_to_string
```

- [ ] **Step 2: Append the regression test to the end of the file**

```python

def test_self_referential_defs_entry_children_ref_resolves_via_real_code_path():
    """A $defs entry that references itself (TreeNode.children items -> #/$defs/TreeNode)
    exercises the two-pass _process_definitions fix against the real production code path
    (no mocking, unlike every other test in this file). Locks in the current, pre-existing
    behavior:
    - a reference to the self-referential def from OUTSIDE its own body (the top-level
      'root' property, resolved only after $defs processing fully completes) resolves to
      the real recursive model.
    - the reference INSIDE the def's own body (children items, resolved while that same
      def is still mid-construction) resolves to Any. This is a documented, pre-existing
      tradeoff of the placeholder-based cache -- identical in the old single-pass
      implementation (see the comment this fix's two-pass version carried forward) -- not
      a behavior introduced or changed by the two-pass fix.
    """
    tree_node_schema = {
        "type": "object",
        "$defs": {
            "TreeNode": {
                "type": "object",
                "required": ["name"],
                "properties": {
                    "name": {"type": "string"},
                    "children": {
                        "type": "array",
                        "items": {"$ref": "#/$defs/TreeNode"},
                    },
                },
            },
        },
        "properties": {
            "root": {"$ref": "#/$defs/TreeNode"},
        },
        "required": ["root"],
    }

    model = json_schema_to_model(tree_node_schema)

    tree_node_model = model.model_fields["root"].annotation
    assert tree_node_model is not Any, "root should resolve to the real TreeNode model"

    instance = model(root={"name": "root", "children": [{"name": "child", "children": []}]})
    assert instance.root.name == "root"
    # Known limitation (pre-existing, not introduced by the two-pass fix): the self-reference
    # inside TreeNode's own body is untyped (Any), so pydantic stores the raw dict rather than
    # coercing it into a TreeNode instance.
    assert isinstance(instance.root.children[0], dict)
    assert instance.root.children[0]["name"] == "child"
```

- [ ] **Step 3: Run the new test to confirm it passes as-is**

```bash
pytest tests/codemie/core/test_json_schema_recursive.py::test_self_referential_defs_entry_children_ref_resolves_via_real_code_path -v
```

Expected: PASS. If this fails instead, STOP — this would mean the two-pass fix changed self-reference behavior from what pre-fix code did; do not proceed to Step 4 without re-reading `_process_definitions` and `_handlers_after_primitive_types` to understand why, and consult before altering scope.

- [ ] **Step 4: Verify no regression versus the pre-fix implementation (confirms Global Constraints' "no production change expected")**

```bash
git stash push -- src/codemie/core/json_schema_utils.py
pytest tests/codemie/core/test_json_schema_recursive.py::test_self_referential_defs_entry_children_ref_resolves_via_real_code_path -v
git stash pop
```

Expected: PASS both before and after the stash (identical behavior pre- and post-fix, confirming this is a coverage-only addition, not a regression fix). If the pre-fix run instead fails or raises, the two behaviors differ — do not silently proceed; note the discrepancy and treat it as a plan deviation per Global Constraints before continuing.

- [ ] **Step 5: Run the full test file to confirm no existing tests broke**

```bash
pytest tests/codemie/core/test_json_schema_recursive.py -v
```

Expected: all 8 tests PASS (7 existing + 1 new).

- [ ] **Step 6: Commit the fix together with both regression tests**

```bash
git add src/codemie/core/json_schema_utils.py tests/codemie/core/test_json_schema_ref_type.py tests/codemie/core/test_json_schema_recursive.py
git commit -m "EPMCDME-13328: Fix \$defs sibling forward-reference resolution order"
```

(If Task 1 Step 5 already committed the production fix separately, `git add` here only the two test files and adjust the message to `EPMCDME-13328: Add regression test for self-referential \$defs real-code-path coverage`.)

---

### Task 3: Full-module verification

**Files:** none modified — verification only.

**Interfaces:** none.

**Test-first: no — verification step, no new test.**

- [ ] **Step 1: Run the full `json_schema_utils` test suite**

```bash
pytest tests/codemie/core/ -v -k json_schema
```

Expected: all tests PASS.

- [ ] **Step 2: Run the MCP toolkit tests that depend on `json_schema_to_model`**

```bash
pytest tests/codemie/service/mcp/test_toolkit_mcp_toolkit_creation.py tests/codemie/service/mcp/test_client.py -v
```

Expected: all tests PASS (these mock `json_schema_to_model`, so they only confirm the call sites still integrate correctly — no behavior change expected here).

- [ ] **Step 3: Confirm working tree is clean**

```bash
git status --porcelain src/codemie/core/json_schema_utils.py tests/codemie/core/test_json_schema_ref_type.py tests/codemie/core/test_json_schema_recursive.py
```

Expected: empty output (everything committed in Tasks 1–2).
