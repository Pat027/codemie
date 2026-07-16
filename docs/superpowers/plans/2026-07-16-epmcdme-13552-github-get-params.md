# EPMCDME-13552: Fix GithubTool GET Params — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix GithubTool to route `method_arguments` as URL query params (`params=`) for GET/HEAD/DELETE requests and as JSON request body (`data=`) for POST/PUT/PATCH, eliminating `422 Validation Failed` on `/search/issues`.

**Architecture:** Two-layer fix: (1) `github_client.py` `make_request()` gains an optional `params` argument passed through both request call sites (initial + auth-retry); (2) `tools.py` `execute()` branches on the HTTP method to pick `params=` vs `data=`. Tests verify both paths and guard against regression.

**Tech Stack:** Python 3.11+, `requests`, `pytest`, `unittest.mock`

---

## File Map

| File | Change |
|------|--------|
| `src/codemie_tools/core/vcs/github/github_client.py` | Add `params: Optional[Dict[str, Any]] = None` to `make_request()`; pass it through both `requests.request()` call sites |
| `src/codemie_tools/core/vcs/github/tools.py` | Branch `execute()` on HTTP method: GET/HEAD/DELETE → `params=`, POST/PUT/PATCH → `data=` |
| `tests/codemie_tools/core/vcs/github/test_tools.py` | Add two regression tests; update three existing assertions that previously expected `data=json.dumps({})` |

---

### Task 1: Add `params` to `GithubClient.make_request()`

**Test-first: yes — test_get_request_passes_method_arguments_as_url_params fails because make_request() has no params kwarg**

**Files:**
- Modify: `src/codemie_tools/core/vcs/github/github_client.py:165-172`
- Test: `tests/codemie_tools/core/vcs/github/test_tools.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/codemie_tools/core/vcs/github/test_tools.py

@patch('codemie_tools.core.vcs.github.github_client.requests.request')
def test_get_request_passes_method_arguments_as_url_params(self, mock_request):
    """GET requests must pass method_arguments as URL params, not request body.

    Regression: /search/issues returned 422 because q= was sent in the body
    instead of the URL query string.
    """
    config = GithubConfig(token="ghp_123456")
    tool = GithubTool(config=config)

    mock_response = MagicMock()
    mock_response.json.return_value = {"total_count": 1, "items": []}
    mock_request.return_value = mock_response

    query = {
        "method": "GET",
        "url": "https://api.github.com/search/issues",
        "method_arguments": {"q": "test"},
    }

    result = tool.execute(query)

    mock_request.assert_called_once_with(
        method="GET",
        url="https://api.github.com/search/issues",
        headers={"Accept": "application/vnd.github+json", "Authorization": "Bearer ghp_123456"},
        data=None,
        params={"q": "test"},
    )
    assert result == {"total_count": 1, "items": []}
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Users/yanaasadchaya/Projects/epam/airun/codemie-dev/codemie
poetry run pytest tests/codemie_tools/core/vcs/github/test_tools.py::TestGithubTool::test_get_request_passes_method_arguments_as_url_params -v
```

Expected: FAIL — `make_request()` does not accept `params` kwarg.

- [ ] **Step 3: Add `params` argument to `make_request()` signature**

```python
# src/codemie_tools/core/vcs/github/github_client.py — replace make_request() signature

def make_request(
    self,
    method: str,
    url: str,
    headers: Dict[str, str],
    data: Optional[str] = None,
    params: Optional[Dict[str, Any]] = None,
) -> Any:
    """
    Make authenticated request to GitHub API.

    Args:
        method: HTTP method (GET, POST, PUT, DELETE, PATCH)
        url: Complete GitHub API URL
        headers: Request headers (Authorization will be added/overridden)
        data: Optional JSON string for request body (POST/PUT/PATCH)
        params: Optional dict of URL query parameters (GET/HEAD/DELETE)

    Returns:
        JSON response from GitHub API

    Raises:
        ToolException: If request fails or authentication fails
    """
```

- [ ] **Step 4: Pass `params` through both `requests.request()` call sites**

Both the initial request and the auth-retry must forward `params`. Replace the two `requests.request(...)` calls in `make_request()`:

```python
# First call (line ~198):
response = requests.request(method=method, url=url, headers=headers, data=data, params=params)

# Auth-retry call (line ~212):
response = requests.request(method=method, url=url, headers=headers, data=data, params=params)
```

- [ ] **Step 5: Run test to verify it passes**

```bash
poetry run pytest tests/codemie_tools/core/vcs/github/test_tools.py::TestGithubTool::test_get_request_passes_method_arguments_as_url_params -v
```

Expected: PASS

---

### Task 2: Route `method_arguments` by HTTP method in `GithubTool.execute()`

**Test-first: yes — test_post_request_passes_method_arguments_as_json_body fails because execute() always sends data=**

**Files:**
- Modify: `src/codemie_tools/core/vcs/github/tools.py:116-138`
- Test: `tests/codemie_tools/core/vcs/github/test_tools.py`

- [ ] **Step 1: Write the second failing test**

```python
# tests/codemie_tools/core/vcs/github/test_tools.py

@patch('codemie_tools.core.vcs.github.github_client.requests.request')
def test_post_request_passes_method_arguments_as_json_body(self, mock_request):
    """POST requests must pass method_arguments as JSON body, not URL params."""
    config = GithubConfig(token="ghp_123456")
    tool = GithubTool(config=config)

    mock_response = MagicMock()
    mock_response.json.return_value = {"number": 1, "title": "Bug"}
    mock_request.return_value = mock_response

    query = {
        "method": "POST",
        "url": "https://api.github.com/repos/owner/repo/issues",
        "method_arguments": {"title": "Bug", "body": "Description"},
    }

    result = tool.execute(query)

    mock_request.assert_called_once_with(
        method="POST",
        url="https://api.github.com/repos/owner/repo/issues",
        headers={"Accept": "application/vnd.github+json", "Authorization": "Bearer ghp_123456"},
        data=json.dumps({"title": "Bug", "body": "Description"}),
        params=None,
    )
    assert result == {"number": 1, "title": "Bug"}
```

- [ ] **Step 2: Run test to verify it fails**

```bash
poetry run pytest tests/codemie_tools/core/vcs/github/test_tools.py::TestGithubTool::test_post_request_passes_method_arguments_as_json_body -v
```

Expected: FAIL — `execute()` always calls `make_request(data=...)` regardless of method.

- [ ] **Step 3: Replace the `execute()` request dispatch with method-aware routing**

```python
# src/codemie_tools/core/vcs/github/tools.py — in execute(), after building headers:

method: str = (query.get('method') or '').upper()
method_args: dict[str, Any] = query.get('method_arguments') or {}

# GET/HEAD/DELETE: arguments go in the URL query string.
# POST/PUT/PATCH: arguments go in the JSON request body.
# Sending a body on GET is silently ignored by GitHub, so /search/issues
# would never receive the required `q` parameter, causing 422.
if method in ('GET', 'HEAD', 'DELETE'):
    return self.client.make_request(
        method=method,
        url=query.get('url'),
        headers=headers,
        params=method_args or None,
    )
return self.client.make_request(
    method=method,
    url=query.get('url'),
    headers=headers,
    data=json.dumps(method_args) if method_args else None,
)
```

- [ ] **Step 4: Run both new regression tests**

```bash
poetry run pytest tests/codemie_tools/core/vcs/github/test_tools.py::TestGithubTool::test_get_request_passes_method_arguments_as_url_params tests/codemie_tools/core/vcs/github/test_tools.py::TestGithubTool::test_post_request_passes_method_arguments_as_json_body -v
```

Expected: both PASS

---

### Task 3: Update existing test assertions for the new call signature

**Test-first: yes — three existing tests fail because mock assertions expect `data=json.dumps({})` but now receive `data=None, params=None`**

**Files:**
- Modify: `tests/codemie_tools/core/vcs/github/test_tools.py:51-57, 76-82, 106-116`

- [ ] **Step 1: Run the full test file to identify assertion failures**

```bash
poetry run pytest tests/codemie_tools/core/vcs/github/test_tools.py -v
```

Expected: `test_execute_with_dict_query`, `test_execute_with_string_query`, `test_execute_with_custom_headers` fail with assertion mismatch on `data=json.dumps({})`.

- [ ] **Step 2: Update the three affected `assert_called_once_with` assertions**

In all three tests, when `method_arguments` is `{}` (empty), `method_args or None` evaluates to `None` for GET, so both `data` and `params` are `None`.

**`test_execute_with_dict_query` (line ~51):**
```python
mock_request.assert_called_once_with(
    method="GET",
    url="https://api.github.com/user",
    headers={"Accept": "application/vnd.github+json", "Authorization": "Bearer ghp_123456"},
    data=None,
    params=None,
)
```

**`test_execute_with_string_query` (line ~76):**
```python
mock_request.assert_called_once_with(
    method="GET",
    url="https://api.github.com/user",
    headers={"Accept": "application/vnd.github+json", "Authorization": "Bearer ghp_123456"},
    data=None,
    params=None,
)
```

**`test_execute_with_custom_headers` (line ~106):**
```python
mock_request.assert_called_once_with(
    method="GET",
    url="https://api.github.com/user",
    headers={
        "Accept": "application/vnd.github+json",
        "X-Custom-Header": "value",
        "Authorization": "Bearer ghp_123456",
    },
    data=None,
    params=None,
)
```

- [ ] **Step 3: Run the full test file to verify all tests pass**

```bash
poetry run pytest tests/codemie_tools/core/vcs/github/test_tools.py -v
```

Expected: all 9 tests PASS

- [ ] **Step 4: Commit**

```bash
git add src/codemie_tools/core/vcs/github/github_client.py \
        src/codemie_tools/core/vcs/github/tools.py \
        tests/codemie_tools/core/vcs/github/test_tools.py
git commit -m "EPMCDME-13552: Fix GithubTool GET params — route method_arguments as URL query params for GET/HEAD/DELETE"
```

---

## Self-Review

**Spec coverage:**
- ✅ `GET`/`HEAD`/`DELETE` → `params=` — Task 2
- ✅ `POST`/`PUT`/`PATCH` → `data=` — Task 2
- ✅ `make_request()` `params` arg + auth-retry passthrough — Task 1
- ✅ `test_get_request_passes_method_arguments_as_url_params` — Task 1
- ✅ `test_post_request_passes_method_arguments_as_json_body` — Task 2
- ✅ Existing tests updated for new signature — Task 3

**Placeholder scan:** None found.

**Type consistency:** `method_args: dict[str, Any]` in `tools.py` matches `params: Optional[Dict[str, Any]]` in `make_request()`. `method_args or None` coerces empty dict to `None`, matching `Optional`.
