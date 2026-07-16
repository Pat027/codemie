# EPMCDME-13552 — GithubTool: GET /search/issues returns 422 (method_arguments sent as body instead of URL params)

**Jira**: https://jiraeu.epam.com/browse/EPMCDME-13552
**Type**: Bug
**Status**: In Progress → Ready for review
**Assignee**: Yana Asadchaya
**Epic**: EPMCDME-13287

## Summary

Fix `GithubTool` to route `method_arguments` as URL query params for GET/HEAD/DELETE and as JSON body for POST/PUT/PATCH.

## Branch

`EPMCDME-13552_github-get-params`

## Linked Artifacts

- `docs/superpowers/runs/20260716-1025-main/requirements.md`
- `docs/superpowers/runs/20260716-1025-main/plan.md` (pending)

## History

| Timestamp | Event | Summary |
|-----------|-------|---------|
| 2026-07-16T10:25:00Z | work_item.created | Resolved from Jira EPMCDME-13552 |
| 2026-07-16T10:27:00Z | work_item.assigned | Branch: EPMCDME-13552_github-get-params |
