# Requirements — EPMCDME-13552

**Source**: https://jiraeu.epam.com/browse/EPMCDME-13552
**Type**: Bug
**Status**: In Progress
**Assignee**: Yana Asadchaya

---

## Goal

Fix `GithubTool` to route `method_arguments` as URL query parameters (`params=`) for `GET`, `HEAD`, and `DELETE` requests, and as a JSON request body (`data=`) for `POST`, `PUT`, and `PATCH` requests.

## Root Cause

`GithubTool.execute()` unconditionally passes `method_arguments` via `data=` (request body) regardless of HTTP method. GitHub silently ignores the body on GET requests, so parameters like `q=test` never reach `/search/issues`, causing GitHub to return `422 Validation Failed`.

Other endpoints such as `GET /user` and `GET /repos/.../pulls/424` were unaffected because they require no URL query parameters — the ignored body was harmless.

## Scope

| File | Change |
|------|--------|
| `src/codemie_tools/core/vcs/github/tools.py` | Route `method_arguments` to `params=` or `data=` based on HTTP method in `execute()` |
| `src/codemie_tools/core/vcs/github/github_client.py` | Add `params: Optional[Dict[str, Any]] = None` to `make_request()` and pass through both call sites (initial request + auth-retry) |
| `tests/codemie_tools/core/vcs/github/test_tools.py` | Add `test_get_request_passes_method_arguments_as_url_params` and `test_post_request_passes_method_arguments_as_json_body`; update existing test assertions |

## Acceptance Criteria

1. `method_arguments` are routed by HTTP method:
   - `GET`, `HEAD`, `DELETE` → `params=` (URL query string)
   - `POST`, `PUT`, `PATCH` → `data=` (JSON request body)
2. `github_client.py` `make_request()` accepts a `params` argument and passes it through both the initial request and auth-retry.
3. Calling `GithubTool` with `GET /search/issues` and `{"q": "test"}` returns `200` instead of `422`.
4. Existing GitHub API calls continue to work: `GET /user`, `GET /repos/.../pulls/424`.
5. Regression tests added:
   - `test_get_request_passes_method_arguments_as_url_params`
   - `test_post_request_passes_method_arguments_as_json_body`

## Preconditions

- GithubTool configured with valid credentials
- GitHub API authentication works
- Search API rate limits not exhausted

## No Open Questions

Requirements are fully specified in the ticket. Implementation is already present in the working tree.
