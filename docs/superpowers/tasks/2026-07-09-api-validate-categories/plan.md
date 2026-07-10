# API Validate Categories Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add API-level validation to enforce presence of categories when publishing assistants to marketplace, ensuring consistency between UI and API behavior.

**Architecture:** Mirror the workflow marketplace validation pattern: (1) Pydantic `Field(min_length=1, max_length=3)` constraint on `PublishToMarketplaceRequest.categories` for structural validation (HTTP 422); (2) Category ID existence check in `_validate_publish_marketplace()` helper wrapping `category_service.validate_category_ids()` in `ValidationException` (HTTP 400); (3) Same validation for sub-assistant publishing path in `_apply_sub_assistant_settings()`.

**Tech Stack:** FastAPI, Pydantic, pytest, SQLModel

---

## File Structure

**Modified Files:**
- `src/codemie/rest_api/routers/assistant.py` — Update `PublishToMarketplaceRequest` model, add validation helper, fix sub-assistant path
- `tests/codemie/rest_api/routers/test_assistant_marketplace.py` — Add three test cases for categories validation

**No new files created.** This is a targeted validation addition to existing code.

---

### Task 1: Add Test for Missing Categories Field

**Files:**
- Modify: `tests/codemie/rest_api/routers/test_assistant_marketplace.py` (end of file, after existing tests)

**Test-first: yes — Test that publishing without categories field returns HTTP 422**

- [ ] **Step 1: Write the failing test**

Add this test at the end of `test_assistant_marketplace.py`:

```python
@pytest.mark.asyncio
async def test_publish_returns_422_when_categories_field_absent():
    """Test that publishing without categories field returns 422."""
    assistant_id = "456"
    
    assistant_mock = MagicMock()
    assistant_mock.id = assistant_id
    assistant_mock.assistant_ids = []
    
    with (
        patch("codemie.rest_api.routers.assistant.Assistant.find_by_id", return_value=assistant_mock),
        patch("codemie.core.ability.Ability.can", return_value=True),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as ac:
            response = await ac.post(
                f"/v1/assistants/{assistant_id}/marketplace/publish",
                json={},  # No categories field
                headers={"Authorization": "Bearer testtoken"},
            )
        
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        result = response.json()
        assert "categories" in str(result).lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/codemie/rest_api/routers/test_assistant_marketplace.py::test_publish_returns_422_when_categories_field_absent -v`

Expected: FAIL — test passes (returns 200 or different status) because categories validation doesn't exist yet

- [ ] **Step 3: Commit the failing test**

```bash
git add tests/codemie/rest_api/routers/test_assistant_marketplace.py
git commit -m "EPMCDME-10198: Add test for missing categories field"
```

---

### Task 2: Add Test for Empty Categories List

**Files:**
- Modify: `tests/codemie/rest_api/routers/test_assistant_marketplace.py` (after Task 1 test)

**Test-first: yes — Test that publishing with empty categories list returns HTTP 422**

- [ ] **Step 1: Write the failing test**

Add this test immediately after the previous test:

```python
@pytest.mark.asyncio
async def test_publish_returns_422_when_categories_is_empty_list():
    """Test that publishing with empty categories list returns 422."""
    assistant_id = "456"
    
    assistant_mock = MagicMock()
    assistant_mock.id = assistant_id
    assistant_mock.assistant_ids = []
    
    with (
        patch("codemie.rest_api.routers.assistant.Assistant.find_by_id", return_value=assistant_mock),
        patch("codemie.core.ability.Ability.can", return_value=True),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as ac:
            response = await ac.post(
                f"/v1/assistants/{assistant_id}/marketplace/publish",
                json={"categories": []},
                headers={"Authorization": "Bearer testtoken"},
            )
        
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        result = response.json()
        assert "categories" in str(result).lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/codemie/rest_api/routers/test_assistant_marketplace.py::test_publish_returns_422_when_categories_is_empty_list -v`

Expected: FAIL — test passes because empty list is currently accepted

- [ ] **Step 3: Commit the failing test**

```bash
git add tests/codemie/rest_api/routers/test_assistant_marketplace.py
git commit -m "EPMCDME-10198: Add test for empty categories list"
```

---

### Task 3: Add Test for Invalid Category IDs

**Files:**
- Modify: `tests/codemie/rest_api/routers/test_assistant_marketplace.py` (after Task 2 test)

**Test-first: yes — Test that publishing with non-existent category IDs returns HTTP 400**

- [ ] **Step 1: Write the failing test**

Add this test immediately after the previous test:

```python
@pytest.mark.asyncio
async def test_publish_returns_400_when_categories_contain_invalid_ids():
    """Test that publishing with invalid category IDs returns 400."""
    assistant_id = "456"
    invalid_category_ids = ["non-existent-1", "non-existent-2"]
    
    assistant_mock = MagicMock()
    assistant_mock.id = assistant_id
    assistant_mock.assistant_ids = []
    
    with (
        patch("codemie.rest_api.routers.assistant.Assistant.find_by_id", return_value=assistant_mock),
        patch("codemie.core.ability.Ability.can", return_value=True),
        patch("codemie.repository.category_repository.CategoryRepository.get_by_ids", return_value=[]),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as ac:
            response = await ac.post(
                f"/v1/assistants/{assistant_id}/marketplace/publish",
                json={"categories": invalid_category_ids},
                headers={"Authorization": "Bearer testtoken"},
            )
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        result = response.json()
        assert "invalid category" in str(result).lower()
        assert "non-existent-1" in str(result) or "non-existent-2" in str(result)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/codemie/rest_api/routers/test_assistant_marketplace.py::test_publish_returns_400_when_categories_contain_invalid_ids -v`

Expected: FAIL — test passes or returns different status because ID validation doesn't exist yet

- [ ] **Step 3: Commit the failing test**

```bash
git add tests/codemie/rest_api/routers/test_assistant_marketplace.py
git commit -m "EPMCDME-10198: Add test for invalid category IDs"
```

---

### Task 4: Update PublishToMarketplaceRequest Model

**Files:**
- Modify: `src/codemie/rest_api/routers/assistant.py:136-140`

**Test-first: yes — Implementing to pass Tasks 1 and 2 (missing/empty categories tests)**

- [ ] **Step 1: Update the categories field constraint**

In `assistant.py`, find the `PublishToMarketplaceRequest` class (around line 136) and change:

```python
class PublishToMarketplaceRequest(BaseModel):
    """Request model for publishing assistant to marketplace"""

    categories: Optional[list[str]] = None
```

To:

```python
class PublishToMarketplaceRequest(BaseModel):
    """Request model for publishing assistant to marketplace"""

    categories: list[str] = Field(
        min_length=1,
        max_length=3,
        description="Category IDs for marketplace classification (1-3 required)"
    )
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `pytest tests/codemie/rest_api/routers/test_assistant_marketplace.py::test_publish_returns_422_when_categories_field_absent -v`

Expected: PASS

Run: `pytest tests/codemie/rest_api/routers/test_assistant_marketplace.py::test_publish_returns_422_when_categories_is_empty_list -v`

Expected: PASS

- [ ] **Step 3: Commit the model update**

```bash
git add src/codemie/rest_api/routers/assistant.py
git commit -m "EPMCDME-10198: Enforce required non-empty categories in PublishToMarketplaceRequest"
```

---

### Task 5: Add Category ID Validation Helper

**Files:**
- Modify: `src/codemie/rest_api/routers/assistant.py:1606-1616`

**Test-first: yes — Implementing to pass Task 3 (invalid category IDs test)**

- [ ] **Step 1: Add validation helper method**

In `assistant.py`, locate the `_validate_publish_marketplace()` function (around line 1606). Add a new helper function immediately before it:

```python
def _validate_categories(category_ids: list[str]) -> None:
    """
    Validate that category IDs exist in the database.
    
    Raises:
        ValidationException: If any category IDs are invalid
    """
    if not category_ids:
        raise ValidationException("At least one category is required")
    
    found_categories = _category_repository.get_by_ids(category_ids)
    found_ids = {cat.id for cat in found_categories}
    invalid_ids = [cid for cid in category_ids if cid not in found_ids]
    if invalid_ids:
        raise ValidationException(f"Invalid category IDs: {invalid_ids}")


def _validate_publish_marketplace(assistant, user):
```

- [ ] **Step 2: Import category repository at top of file**

At the top of `assistant.py`, find the imports section and add:

```python
from codemie.repository.category_repository import category_repository as _category_repository
```

(Check if this import already exists; if so, skip this step)

- [ ] **Step 3: Update _validate_publish_marketplace to call the helper**

In `_validate_publish_marketplace()` function (around line 1606), update it to:

```python
def _validate_publish_marketplace(assistant, user, categories: list[str]):
    """
    Validate that an assistant can be published to the marketplace.

    This function checks:
    - User has write access to the assistant
    - Remote entities (e.g., Bedrock agents) exist if applicable
    - Categories are valid and exist in the database
    """
    _check_user_can_access_assistant(user, assistant, "write", Action.WRITE)
    _validate_remote_entities_and_raise(assistant)
    _validate_categories(categories)
```

- [ ] **Step 4: Update the publish endpoint call**

Find the `publish_assistant_to_marketplace` endpoint (around line 1324) and locate the call to `_validate_publish_marketplace`. Update it from:

```python
_validate_publish_marketplace(assistant, user)
```

To:

```python
_validate_publish_marketplace(assistant, user, request.categories)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/codemie/rest_api/routers/test_assistant_marketplace.py::test_publish_returns_400_when_categories_contain_invalid_ids -v`

Expected: PASS

- [ ] **Step 6: Commit the validation implementation**

```bash
git add src/codemie/rest_api/routers/assistant.py
git commit -m "EPMCDME-10198: Add category ID existence validation in publish flow"
```

---

### Task 6: Fix Sub-Assistant Categories Validation

**Files:**
- Modify: `src/codemie/rest_api/routers/assistant.py:1491-1492`

**Test-first: yes — Add test first for sub-assistant categories validation**

- [ ] **Step 1: Write the failing test**

Add this test to `test_assistant_marketplace.py`:

```python
@pytest.mark.asyncio
async def test_publish_validates_sub_assistant_categories():
    """Test that sub-assistant categories are validated when publishing."""
    assistant_id = "456"
    sub_assistant_id = "sub1"
    valid_category_ids = ["cat-1", "cat-2"]
    
    assistant_mock = MagicMock()
    assistant_mock.id = assistant_id
    assistant_mock.assistant_ids = [sub_assistant_id]
    
    sub_assistant_mock = MagicMock()
    sub_assistant_mock.id = sub_assistant_id
    sub_assistant_mock.categories = []
    
    category_mock = MagicMock()
    category_mock.id = "cat-1"
    category_mock2 = MagicMock()
    category_mock2.id = "cat-2"
    
    with (
        patch("codemie.rest_api.routers.assistant.Assistant.find_by_id") as mock_find,
        patch("codemie.core.ability.Ability.can", return_value=True),
        patch("codemie.repository.category_repository.CategoryRepository.get_by_ids", return_value=[category_mock, category_mock2]),
        patch("codemie.rest_api.routers.assistant._validate_remote_entities_and_raise"),
        patch.object(assistant_mock, "update"),
        patch("codemie.rest_api.routers.assistant._index_marketplace_assistant"),
    ):
        def find_side_effect(aid):
            if aid == assistant_id:
                return assistant_mock
            if aid == sub_assistant_id:
                return sub_assistant_mock
            return None
        
        mock_find.side_effect = find_side_effect
        
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as ac:
            response = await ac.post(
                f"/v1/assistants/{assistant_id}/marketplace/publish",
                json={
                    "categories": valid_category_ids,
                    "sub_assistants_settings": [
                        {
                            "assistant_id": sub_assistant_id,
                            "is_global": True,
                            "categories": valid_category_ids
                        }
                    ]
                },
                headers={"Authorization": "Bearer testtoken"},
            )
        
        # Should succeed because categories are valid
        assert response.status_code == status.HTTP_200_OK
        # Verify sub-assistant categories were set
        assert sub_assistant_mock.categories == valid_category_ids
```

- [ ] **Step 2: Run test to verify current behavior**

Run: `pytest tests/codemie/rest_api/routers/test_assistant_marketplace.py::test_publish_validates_sub_assistant_categories -v`

Expected: Test should pass (validation doesn't block invalid categories yet in sub-assistant path)

- [ ] **Step 3: Update _apply_sub_assistant_settings to validate categories**

In `assistant.py`, find `_apply_sub_assistant_settings()` function (around line 1463) and update the categories section:

Change from:

```python
    # Update categories if provided
    if settings.categories:
        sub_assistant.categories = settings.categories
```

To:

```python
    # Update categories if provided
    if settings.categories:
        _validate_categories(settings.categories)
        sub_assistant.categories = settings.categories
```

- [ ] **Step 4: Run test to verify it still passes**

Run: `pytest tests/codemie/rest_api/routers/test_assistant_marketplace.py::test_publish_validates_sub_assistant_categories -v`

Expected: PASS

- [ ] **Step 5: Add negative test for invalid sub-assistant categories**

Add this test to `test_assistant_marketplace.py`:

```python
@pytest.mark.asyncio
async def test_publish_rejects_invalid_sub_assistant_categories():
    """Test that invalid sub-assistant categories are rejected."""
    assistant_id = "456"
    sub_assistant_id = "sub1"
    valid_category_ids = ["cat-1"]
    invalid_sub_category_ids = ["invalid-cat"]
    
    assistant_mock = MagicMock()
    assistant_mock.id = assistant_id
    assistant_mock.assistant_ids = [sub_assistant_id]
    
    sub_assistant_mock = MagicMock()
    sub_assistant_mock.id = sub_assistant_id
    
    category_mock = MagicMock()
    category_mock.id = "cat-1"
    
    with (
        patch("codemie.rest_api.routers.assistant.Assistant.find_by_id") as mock_find,
        patch("codemie.core.ability.Ability.can", return_value=True),
        patch("codemie.repository.category_repository.CategoryRepository.get_by_ids") as mock_get_cats,
    ):
        def find_side_effect(aid):
            if aid == assistant_id:
                return assistant_mock
            if aid == sub_assistant_id:
                return sub_assistant_mock
            return None
        
        def get_cats_side_effect(cat_ids):
            # Return valid categories for main assistant, empty for sub-assistant
            if "cat-1" in cat_ids and len(cat_ids) == 1:
                return [category_mock]
            return []
        
        mock_find.side_effect = find_side_effect
        mock_get_cats.side_effect = get_cats_side_effect
        
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as ac:
            response = await ac.post(
                f"/v1/assistants/{assistant_id}/marketplace/publish",
                json={
                    "categories": valid_category_ids,
                    "sub_assistants_settings": [
                        {
                            "assistant_id": sub_assistant_id,
                            "is_global": True,
                            "categories": invalid_sub_category_ids
                        }
                    ]
                },
                headers={"Authorization": "Bearer testtoken"},
            )
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        result = response.json()
        assert "invalid category" in str(result).lower()
```

- [ ] **Step 6: Run negative test to verify rejection**

Run: `pytest tests/codemie/rest_api/routers/test_assistant_marketplace.py::test_publish_rejects_invalid_sub_assistant_categories -v`

Expected: PASS

- [ ] **Step 7: Commit the sub-assistant validation**

```bash
git add src/codemie/rest_api/routers/assistant.py tests/codemie/rest_api/routers/test_assistant_marketplace.py
git commit -m "EPMCDME-10198: Add category validation for sub-assistant publishing"
```

---

### Task 7: Run Full Test Suite

**Files:**
- All modified test files

- [ ] **Step 1: Run all new tests together**

Run: `pytest tests/codemie/rest_api/routers/test_assistant_marketplace.py -k "categories" -v`

Expected: All category-related tests PASS

- [ ] **Step 2: Run entire assistant marketplace test file**

Run: `pytest tests/codemie/rest_api/routers/test_assistant_marketplace.py -v`

Expected: All tests PASS (no regressions)

- [ ] **Step 3: Run workflow marketplace tests to verify reference pattern still works**

Run: `pytest tests/codemie/rest_api/routers/test_workflow_marketplace_router.py -v`

Expected: All tests PASS (no interference)

---

### Task 8: Manual Verification Against Local Backend

**Files:**
- Local dev environment

**Test-first: no — Manual verification of implementation**

- [ ] **Step 1: Verify backend is running**

Check that the backend is running in dev mode:

```bash
# Verify the process is running
ps aux | grep codemie
```

Expected: Backend process visible

- [ ] **Step 2: Test publishing without categories via API**

Using the assistant ID `26fdcab8-28ab-43de-b6f3-22ff698a6bef` and user `dev-codemie-user`:

```bash
curl -X POST "http://localhost:8000/v1/assistants/26fdcab8-28ab-43de-b6f3-22ff698a6bef/marketplace/publish" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <dev-token>" \
  -d '{}'
```

Expected: HTTP 422 with error message mentioning "categories"

- [ ] **Step 3: Test publishing with empty categories**

```bash
curl -X POST "http://localhost:8000/v1/assistants/26fdcab8-28ab-43de-b6f3-22ff698a6bef/marketplace/publish" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <dev-token>" \
  -d '{"categories": []}'
```

Expected: HTTP 422 with error message about minimum length

- [ ] **Step 4: Test publishing with invalid category IDs**

```bash
curl -X POST "http://localhost:8000/v1/assistants/26fdcab8-28ab-43de-b6f3-22ff698a6bef/marketplace/publish" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <dev-token>" \
  -d '{"categories": ["invalid-id-1", "invalid-id-2"]}'
```

Expected: HTTP 400 with error message "Invalid category IDs: ['invalid-id-1', 'invalid-id-2']"

- [ ] **Step 5: Test publishing with valid category IDs**

First, get valid category IDs:

```bash
curl -X GET "http://localhost:8000/v1/categories" \
  -H "Authorization: Bearer <dev-token>"
```

Then publish with 1-3 valid IDs:

```bash
curl -X POST "http://localhost:8000/v1/assistants/26fdcab8-28ab-43de-b6f3-22ff698a6bef/marketplace/publish" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <dev-token>" \
  -d '{"categories": ["<valid-id-1>", "<valid-id-2>"]}'
```

Expected: HTTP 200 with success response

- [ ] **Step 6: Document manual test results**

Create a brief summary in a comment or note:
- [ ] All four API scenarios tested
- [ ] Error responses are clear and actionable
- [ ] Valid categories allow successful publishing
- [ ] No regression in existing publish flow

---

## Self-Review

**Spec coverage:**
- ✅ API rejects publishing requests lacking categories (Tasks 1, 2, 4)
- ✅ API rejects invalid category IDs (Task 3, 5)
- ✅ Error responses are clear and descriptive (all tasks use ValidationException with specific messages)
- ✅ Consistent validation between API and UI (mirroring workflow marketplace pattern)
- ✅ No regression in assistant creation or category selection (Task 7 verifies no test failures)
- ✅ Sub-assistant path validated (Task 6)

**Placeholder scan:**
- No "TBD", "TODO", or "implement later" found
- All test code is complete with assertions
- All implementation code is complete with exact logic
- Commands include expected output

**Type consistency:**
- `categories: list[str]` used consistently across all tasks
- `ValidationException` used for HTTP 400 errors
- Pydantic `Field` constraint for HTTP 422 structural validation
- All function signatures match across references

**Reference implementation alignment:**
- `Field(min_length=1, max_length=3)` matches workflow marketplace exactly
- `_validate_categories()` helper follows workflow service pattern
- Test structure follows workflow marketplace test pattern
- Error response format follows project conventions
