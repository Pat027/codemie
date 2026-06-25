# Plan — EPMCDME-13171: Fix Scheduler Data Source for Xray and SharePoint

**Routing**: writing-plans (score 8)
**Branch**: EPMCDME-13171

---

## Overview

Two defects prevent Xray and SharePoint datasources from being scheduled via the cron trigger engine:
1. `validate_datasource` (utils.py) raises `NotImplementedDatasource` for both types — job never registered.
2. `__schedule_datasource_job` (cron.py) has no dispatch branch for either type — job would fall to error log.

## Tasks

### T1 — Add Xray and SharePoint to `validate_datasource`
**File**: `src/codemie/triggers/bindings/utils.py`

Add `"knowledge_base_xray"` and `"knowledge_base_sharepoint"` to the supported-types condition in `validate_datasource`. Both types use `setting_id` (Xray always; SharePoint with integration auth), so neither should be added to `DATASOURCE_WITHOUT_SETTING_ID`.

```python
# Before
if ds.is_code_index() or ds.index_type in [
    FullDatasourceTypes.CONFLUENCE,
    FullDatasourceTypes.JIRA,
    FullDatasourceTypes.GOOGLE,
    FullDatasourceTypes.AZURE_DEVOPS_WIKI,
    FullDatasourceTypes.AZURE_DEVOPS_WORK_ITEM,
    FullDatasourceTypes.PROVIDER,
]:

# After — add the two missing string literals
if ds.is_code_index() or ds.index_type in [
    FullDatasourceTypes.CONFLUENCE,
    FullDatasourceTypes.JIRA,
    FullDatasourceTypes.GOOGLE,
    FullDatasourceTypes.AZURE_DEVOPS_WIKI,
    FullDatasourceTypes.AZURE_DEVOPS_WORK_ITEM,
    FullDatasourceTypes.PROVIDER,
    "knowledge_base_xray",
    "knowledge_base_sharepoint",
]:
```

**Test-first**: yes — write a unit test that calls `validate_datasource` with a mock `IndexInfo` whose `index_type` is `"knowledge_base_xray"` and asserts it returns a non-None result (not raises `NotImplementedDatasource`). Also write the same test for `"knowledge_base_sharepoint"`. These tests fail before the fix.

---

### T2 — Add `XrayReindexTask` and `SharePointReindexTask` to trigger models
**File**: `src/codemie/triggers/trigger_models.py`

Add two new payload classes. Both are simple `ReindexTaskPayload` subclasses with no extra fields — all config data lives in `index_info.xray` / `index_info.sharepoint` respectively.

```python
class XrayReindexTask(ReindexTaskPayload):
    pass

class SharePointReindexTask(ReindexTaskPayload):
    pass
```

**Test-first**: no — model class definitions have no logic to test independently. Covered by integration via T3 tests.

---

### T3 — Add `reindex_xray` and `reindex_sharepoint` actor functions
**File**: `src/codemie/triggers/actors/datasource.py`

Add two new actor functions following the established pattern of `reindex_jira` / `reindex_confluence`.

**`reindex_xray`**:
- Fetches Xray credentials via `SettingsService.get_xray_creds(user_id, project_name, setting_id=index_info.setting_id)`.
- Reads `jql` from `index_info.xray.jql`.
- Instantiates `XrayDatasourceProcessor` with creds + jql.
- Calls `datasource_concurrency_manager.run(processor.incremental_reindex, processor.index)` — same as Jira which also uses incremental.

**`reindex_sharepoint`**:
- Fetches SharePoint credentials via `SettingsService.get_sharepoint_creds(user_id, project_name, setting_id=index_info.setting_id)`.
- Reads SharePoint config from `index_info.sharepoint`.
- Instantiates `SharePointDatasourceProcessor` with creds + `SharePointProcessorConfig` built from `index_info.sharepoint`.
- Calls `datasource_concurrency_manager.run(processor.reprocess, processor.index)` — same as Confluence.

Both functions must log `REINDEX_START_MSG`, `REINDEX_FAILED_MSG`, and `REINDEX_SUCCESS_MSG` using the same pattern.

Import the new task models (`XrayReindexTask`, `SharePointReindexTask`) from `codemie.triggers.trigger_models`.

**Test-first**: yes — write unit tests that mock `SettingsService.get_xray_creds`, mock `XrayDatasourceProcessor`, mock `datasource_concurrency_manager.run`, and assert the actor calls `incremental_reindex` when credentials are found, and logs an error when credentials are None. Mirror the existing test pattern in `tests/codemie/triggers/actors/test_actor_datasource.py`.

---

### T4 — Add Xray and SharePoint dispatch in `__schedule_datasource_job`
**File**: `src/codemie/triggers/bindings/cron.py`

Add two new `elif` branches before the final `else` in `__schedule_datasource_job`.

Import `XrayReindexTask` and `SharePointReindexTask` from `codemie.triggers.trigger_models`, and `reindex_xray` / `reindex_sharepoint` from `codemie.triggers.actors.datasource`.

**Xray branch** (after `AZURE_DEVOPS_WORK_ITEM` block):
```python
elif index_type_str == "knowledge_base_xray":
    payload = XrayReindexTask(
        project_name=project_name,
        resource_id=job_id,
        resource_name=resource_name,
        user=user,
        index_info=index_info,
    )
    return self.scheduler.add_job(
        reindex_xray,
        trigger=cron_trigger,
        id=job_id,
        replace_existing=True,
        kwargs={"payload": payload},
    )
```

**SharePoint branch**:
```python
elif index_type_str == "knowledge_base_sharepoint":
    payload = SharePointReindexTask(
        project_name=project_name,
        resource_id=job_id,
        resource_name=resource_name,
        user=user,
        index_info=index_info,
    )
    return self.scheduler.add_job(
        reindex_sharepoint,
        trigger=cron_trigger,
        id=job_id,
        replace_existing=True,
        kwargs={"payload": payload},
    )
```

**Test-first**: yes — add two test cases to `tests/codemie/triggers/bindings/test_cron.py` asserting that `__schedule_datasource_job` (via `__actualize_cron_job`) schedules a job for `knowledge_base_xray` and `knowledge_base_sharepoint` index types (using mock index_info). Currently these would not schedule (fall to error branch).

---

## Execution Order

T1 → T2 → T3 → T4 (each depends on the previous).

- T1 is independent of T2/T3/T4.
- T2 must precede T3 and T4 (models needed by actor and cron).
- T3 must precede T4 (actor functions needed by cron imports).

## Verification

After implementing all tasks:
```bash
cd /home/taras_spashchenko/EPAM/cm/codemie
poetry run pytest tests/codemie/triggers/ -v
```
