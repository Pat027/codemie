# Fix OSS Build Startup Crash (EPMCDME-13525) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop the OSS build (`INSTALL_ENTERPRISE=false`) from crashing at startup on the top-level `langfuse.experiment` import in `workflow_evaluation_service.py`, and add a regression test that would catch a future reintroduction of the same bug.

**Architecture:** No architectural change. The fix moves one import under an existing `if TYPE_CHECKING:` guard (already applied, uncommitted, in the working tree). The only new artifact is a regression test that re-imports the module with `langfuse` hidden from `sys.modules`, mirroring the existing `test_webhook_rate_limiter_import.py` pattern for the same class of optional-dependency bug.

**Tech Stack:** Python 3.12/3.13, pytest, `importlib`/`sys.modules` for import isolation. Verification runs inside a clean Docker container (`python:3.12.12-slim`, OSS-only `poetry install --sync`, no `codemie-enterprise` extra) because the local Poetry venv has unrelated, pre-existing corruption.

## Global Constraints

- No runtime behavior change to `workflow_evaluation_service.py` beyond the import restructuring — `require_langfuse_client()` must continue to raise its existing typed 503 at request time when Langfuse is unavailable.
- Diff and commit must contain only `src/codemie/service/workflow_evaluation_service.py` and the new test file — the unrelated dirty changes to `google_oauth.py`, `sharepoint_oauth.py`, `.env`, and `.codemie/codemie-cli.config.json` must not be staged or committed as part of this ticket.
- Test file follows the exact `sys.modules.pop` + `importlib.import_module` pattern used in `tests/codemie/triggers/bindings/test_webhook_rate_limiter_import.py`.
- Commit message format: `EPMCDME-13525: <description>` (per `.ai-run/guides/standards/git-workflow.md`).

---

### Task 1: Confirm the existing fix and add the import regression test

**Files:**
- Verify (already modified, uncommitted): `src/codemie/service/workflow_evaluation_service.py`
- Create: `tests/codemie/service/test_workflow_evaluation_service_import.py`

**Interfaces:**
- Consumes: nothing from other tasks (this is the only task).
- Produces: nothing consumed elsewhere — this is a standalone regression test file.

**Test-first: yes — new test `test_workflow_evaluation_service_importable_without_langfuse` must fail (`ModuleNotFoundError`) if the top-level `from langfuse.experiment import ExperimentItem` import were restored, and must pass with the current `TYPE_CHECKING`-guarded import.**

- [x] **Step 1: Confirm the existing uncommitted fix is present**

Run: `git diff -- src/codemie/service/workflow_evaluation_service.py`

Expected output includes:
```python
+from typing import TYPE_CHECKING
+
 from fastapi import BackgroundTasks, Request
+
+if TYPE_CHECKING:
+    from langfuse.experiment import ExperimentItem
```
and the old top-level `from langfuse.experiment import ExperimentItem` line (outside any guard) is removed. If this diff is not present (e.g. someone reset the working tree), re-apply it: open `src/codemie/service/workflow_evaluation_service.py`, ensure line 17 is `from __future__ import annotations`, add `from typing import TYPE_CHECKING` after the stdlib/future imports, and wrap the `langfuse.experiment` import:

```python
from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import BackgroundTasks, Request

if TYPE_CHECKING:
    from langfuse.experiment import ExperimentItem

from codemie.configs import logger
from codemie.core.exceptions import ExtendedHTTPException
```

- [x] **Step 2: Write the failing regression test**

Create `tests/codemie/service/test_workflow_evaluation_service_import.py`:

```python
# Copyright 2026 EPAM Systems, Inc. ("EPAM")
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Verify workflow_evaluation_service can be imported without the langfuse package installed."""

import importlib
import sys


def test_workflow_evaluation_service_importable_without_langfuse():
    """Module must not require langfuse at import time (langfuse is a transitive dep of codemie-enterprise)."""
    # Remove the module from sys.modules so it is re-imported fresh
    sys.modules.pop("codemie.service.workflow_evaluation_service", None)
    # Temporarily hide langfuse from the import system
    langfuse_mod = sys.modules.pop("langfuse", None)
    try:
        importlib.import_module("codemie.service.workflow_evaluation_service")
    except ImportError as exc:
        raise AssertionError(
            "workflow_evaluation_service must be importable without langfuse installed"
        ) from exc
    finally:
        # Restore original module state
        sys.modules.pop("codemie.service.workflow_evaluation_service", None)
        if langfuse_mod is not None:
            sys.modules["langfuse"] = langfuse_mod
```

- [x] **Step 3: Verify RED against the pre-fix import inside the clean Docker OSS container**

The container `codemie-oss-test` (python:3.12.12-slim, OSS-only `poetry install --sync`, no enterprise extra) is used for verification since the local Poetry venv has unrelated corruption.

Temporarily revert only the import guard to reproduce the bug (do not commit this):

```bash
docker exec codemie-oss-test bash -lc 'cd /app && \
  git stash push -- src/codemie/service/workflow_evaluation_service.py && \
  python -c "
import re
p = \"src/codemie/service/workflow_evaluation_service.py\"
s = open(p).read()
s = s.replace(
    \"if TYPE_CHECKING:\n    from langfuse.experiment import ExperimentItem\n\n\",
    \"from langfuse.experiment import ExperimentItem\n\n\",
)
open(p, \"w\").write(s)
" && \
  PYTHONPATH=/app/src python -m pytest tests/codemie/service/test_workflow_evaluation_service_import.py -v'
```

Expected: `FAILED` — `AssertionError: workflow_evaluation_service must be importable without langfuse installed` (raised from a `ModuleNotFoundError: No module named 'langfuse'`).

Then restore the fix:

```bash
docker exec codemie-oss-test bash -lc 'cd /app && git checkout -- src/codemie/service/workflow_evaluation_service.py && git stash pop'
```

- [x] **Step 4: Verify GREEN with the fix in place**

```bash
docker exec codemie-oss-test bash -lc 'cd /app && PYTHONPATH=/app/src python -m pytest tests/codemie/service/test_workflow_evaluation_service_import.py -v'
```

Expected: `PASSED`.

- [x] **Step 5: Run the existing service test suite to confirm no regression**

```bash
docker exec codemie-oss-test bash -lc 'cd /app && PYTHONPATH=/app/src python -m pytest tests/codemie/service/test_workflow_evaluation_service.py -v'
```

Expected: all tests `PASSED` (these mock `require_langfuse_client` at the call site and are unaffected by the import change).

- [x] **Step 6: Stage only the two relevant files and commit**

```bash
git add src/codemie/service/workflow_evaluation_service.py tests/codemie/service/test_workflow_evaluation_service_import.py
git status --porcelain
```

Confirm the status output shows only these two files staged (`.env`, `.codemie/codemie-cli.config.json`, `google_oauth.py`, `sharepoint_oauth.py` must NOT appear staged).

```bash
git commit -m "EPMCDME-13525: Fix OSS build startup crash from top-level langfuse import"
```

---

## Self-Review Notes

- **Spec coverage:** All four spec sections (Fix, Regression test, Verification approach, Out of scope) map to Task 1's steps. Acceptance criteria map 1:1 to Steps 1–6.
- **Placeholder scan:** No TBD/TODO; test code is complete and runnable as written.
- **Type consistency:** N/A — single-file test with no shared interfaces across tasks.
- **Scope:** Single task is correct for an XS-sized fix; no decomposition needed.
