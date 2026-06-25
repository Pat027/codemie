# Requirements — EPMCDME-13171
## Scheduler Data Source does not work directly or when created via Integration for Data Source

**Source**: Jira EPMCDME-13171 (Bug)
**Mode**: autonomous

---

## Goal

Fix the Scheduler Data Source functionality so that scheduled reindexing works for **Xray** and **SharePoint** datasource types, both when configured directly from the Data Sources module and when created via Integration for Data Source.

---

## Root Cause Analysis

The bug has two concrete defects in the scheduler trigger infrastructure:

### Defect 1 — `validate_datasource` doesn't recognise Xray and SharePoint

**File**: `src/codemie/triggers/bindings/utils.py` — function `validate_datasource` (line 59)

The function whitelists datasource index types that may be used with the cron trigger. The current whitelist is:
- `is_code_index()` (git/svn code types)
- `FullDatasourceTypes.CONFLUENCE` (`knowledge_base_confluence`)
- `FullDatasourceTypes.JIRA` (`knowledge_base_jira`)
- `FullDatasourceTypes.GOOGLE` (`llm_routing_google`)
- `FullDatasourceTypes.AZURE_DEVOPS_WIKI` (`knowledge_base_azure_devops_wiki`)
- `FullDatasourceTypes.AZURE_DEVOPS_WORK_ITEM` (`knowledge_base_azure_devops_work_item`)
- `FullDatasourceTypes.PROVIDER`

**Missing**: `"knowledge_base_xray"` and `"knowledge_base_sharepoint"`.

When the APScheduler `__watch_settings` loop polls settings and calls `__valid_setting → __validate_resource → validate_datasource` for a scheduled Xray or SharePoint datasource, `validate_datasource` raises `NotImplementedDatasource`. The exception is caught in `__validate_resource` (cron.py line 305), `ds_meta` becomes `None`, `__valid_setting` returns `False`, and the APScheduler job is never registered — silently.

### Defect 2 — `__schedule_datasource_job` has no dispatch case for Xray or SharePoint

**File**: `src/codemie/triggers/bindings/cron.py` — method `__schedule_datasource_job` (line 505)

The method dispatches to a reindex actor based on `index_type_str`. The current dispatch covers: svn, CODE/SUMMARY/CHUNK_SUMMARY, `knowledge_base_jira`, `knowledge_base_confluence`, `llm_routing_google`, `knowledge_base_azure_devops_wiki`, `knowledge_base_azure_devops_work_item`. Missing cases fall through to `logger.error("Datasource index type not supported: %s", ...)` and return `None`.

**Missing**: `"knowledge_base_xray"` and `"knowledge_base_sharepoint"` dispatch branches.

---

## Affected Files

| File | Change |
|------|--------|
| `src/codemie/triggers/bindings/utils.py` | Add `knowledge_base_xray` and `knowledge_base_sharepoint` to `validate_datasource` whitelist |
| `src/codemie/triggers/trigger_models.py` | Add `XrayReindexTask` and `SharePointReindexTask` payload classes |
| `src/codemie/triggers/actors/datasource.py` | Add `reindex_xray` and `reindex_sharepoint` actor functions |
| `src/codemie/triggers/bindings/cron.py` | Add dispatch branches for Xray and SharePoint in `__schedule_datasource_job` |

---

## Constraints

- SharePoint datasources with `auth_type in ("oauth_codemie", "oauth_custom")` already skip scheduler creation in `SharePointDatasourceProcessor._create_or_update_scheduler`. Those datasources will never have a scheduler setting created. Only SharePoint datasources with `auth_type == "integration"` reach the scheduler path. No special-case needed in the new code.
- The `reindex_xray` actor must use `index_info.xray.jql` for the JQL, matching the pattern in `_resume_xray`.
- The `reindex_sharepoint` actor must use `SettingsService.get_sharepoint_creds` for integration-auth datasources, matching the pattern in `_resume_sharepoint`.
- Xray's `index_info.setting_id` is required; it is already checked by `validate_datasource` via the `DATASOURCE_WITHOUT_SETTING_ID` exclusion list.
- No database migrations required.

---

## Acceptance Criteria

1. Scheduled reindexing fires correctly for Xray datasources with a valid `setting_id`.
2. Scheduled reindexing fires correctly for SharePoint datasources with `auth_type == "integration"`.
3. `validate_datasource` returns a non-None result for `knowledge_base_xray` and `knowledge_base_sharepoint` types.
4. `__schedule_datasource_job` schedules APScheduler jobs for Xray and SharePoint instead of logging "not supported".
5. Existing datasource types (Jira, Confluence, Git, etc.) are not regressed.

---

## Out of Scope

- `knowledge_base_file` datasources: those are intentionally in `UNSUPPORTED_RESUME_TYPES` and file uploads can't be triggered remotely on a schedule.
- Adding new integration types or UI changes.
