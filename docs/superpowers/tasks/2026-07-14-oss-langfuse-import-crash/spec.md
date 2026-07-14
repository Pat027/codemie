# Spec: Fix OSS build startup crash — top-level langfuse import (EPMCDME-13525)

## Problem

`src/codemie/service/workflow_evaluation_service.py` imports `langfuse.experiment.ExperimentItem` at module top level. `langfuse` is only installed transitively via the optional `codemie-enterprise` extra, so any OSS build (`INSTALL_ENTERPRISE=false`) crashes at startup with `ModuleNotFoundError` the moment `src/codemie/rest_api/routers/workflow.py` imports `WorkflowEvaluationService`.

## Fix

Move the langfuse import under `if TYPE_CHECKING:`, since `ExperimentItem` is used only as a type annotation (in `item_task`'s signature inside `_run_evaluation_task`) and the module already has `from __future__ import annotations` (PEP 563), so the annotation is never evaluated at runtime.

This is already applied, uncommitted, in the working tree:

```python
from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import BackgroundTasks, Request

if TYPE_CHECKING:
    from langfuse.experiment import ExperimentItem

from codemie.configs import logger
from codemie.core.exceptions import ExtendedHTTPException
```

No runtime behavior changes. `require_langfuse_client()` continues to enforce Langfuse availability at request time (raising the existing typed 503) — this fix only removes the import-time crash.

This is consistent with the codebase's established three-tier optional-dependency pattern (see `technical-analysis.md` §2 "Patterns and Conventions"): `codemie.enterprise.loader` for guarded SDK imports, `if TYPE_CHECKING:` + `from __future__ import annotations` for type-only annotations (used in 20+ files), and deferred in-method imports for call-time SDK use.

## Regression test

Add `tests/codemie/service/test_workflow_evaluation_service_import.py`, following the existing pattern in `tests/codemie/triggers/bindings/test_webhook_rate_limiter_import.py`:

- Pop `codemie.service.workflow_evaluation_service` and `langfuse` from `sys.modules`.
- Re-import the module via `importlib.import_module`.
- Assert the import succeeds (no `ImportError`/`ModuleNotFoundError`), restoring `sys.modules` state in a `finally` block.

This proves the module loads cleanly without `langfuse` installed — the exact condition that crashes an OSS build. Without it, an accidental revert of the `TYPE_CHECKING` guard would ship undetected, since the existing test suite for this service mocks `require_langfuse_client` at the call site and never exercises the import path.

## Out of scope

- No changes to `require_langfuse_client()`, `codemie.enterprise.langfuse.*`, or any other file.
- The unrelated uncommitted changes already present in the working tree (`google_oauth.py`, `sharepoint_oauth.py`, `.env`, `.codemie/codemie-cli.config.json`) are not part of this fix and must not appear in this ticket's diff or commit.
- No changes to `docker-compose.yml` or the Dockerfile to exercise the OSS path locally by default — out of scope for this ticket.

## Verification approach

The local Poetry venv on this machine has an unrelated, pre-existing corruption (missing transitive packages across the tool ecosystem, and a native-build failure for `pymssql` on macOS arm64/Python 3.13) that makes a full local `import codemie.service.workflow_evaluation_service` impractical to fix without unrelated dependency changes. Per user decision, the regression test's RED/GREEN cycle is verified inside a clean Docker container built from `python:3.12.12-slim` with an OSS-only `poetry install --sync` (no `codemie-enterprise` extra, matching `make install-oss`), avoiding both issues.

## Acceptance criteria

- [ ] `workflow_evaluation_service.py` imports `ExperimentItem` only under `TYPE_CHECKING`.
- [ ] New regression test fails (RED) against the pre-fix import (top-level `from langfuse.experiment import ExperimentItem`) when `langfuse` is hidden from `sys.modules`.
- [ ] New regression test passes (GREEN) against the fixed import.
- [ ] Existing `tests/codemie/service/test_workflow_evaluation_service.py` suite is unaffected.
- [ ] Diff and commit contain only `workflow_evaluation_service.py` and the new test file.
