# Technical Research

**Task**: langfuse workflow-evaluation enterprise-optional-imports
**Generated**: 2026-07-14T00:00:00Z
**Research path**: filesystem

---

## 1. Original Context

EPMCDME-13525 — OSS build (INSTALL_ENTERPRISE=false) crashes at startup because src/codemie/service/workflow_evaluation_service.py imports the Langfuse SDK directly at module top level (`from langfuse.experiment import ExperimentItem`). This bypasses the guarded codemie.enterprise.* loader path. In the OSS build, langfuse is not installed because it is only pulled as a transitive dependency of the optional codemie-enterprise package / "enterprise" extra, so the backend fails before FastAPI can start. Expected result: the OSS backend starts successfully with INSTALL_ENTERPRISE=false; workflow evaluation may still return the existing structured enterprise/Langfuse-unavailable response at request time via require_langfuse_client(), but optional enterprise dependencies must not crash application startup. Root cause: ExperimentItem is used only as a type annotation, and the module already has `from __future__ import annotations`, so the runtime import is unnecessary. Fix proposal from the ticket: move the langfuse import under `if TYPE_CHECKING:`.

Note: the working tree currently has an UNCOMMITTED, unreviewed change to workflow_evaluation_service.py that already applies this exact TYPE_CHECKING fix (added `from typing import TYPE_CHECKING` and wrapped the langfuse import). Please note this existing uncommitted diff in your findings, and also identify: (1) any other optional-enterprise-dependency modules in the codebase that follow the same guarded-import pattern correctly (e.g. how codemie.enterprise.* modules are conditionally imported elsewhere) so the fix here is consistent with established conventions, (2) how `require_langfuse_client()` works and where it's called, (3) existing tests for workflow_evaluation_service.py and how OSS/non-enterprise startup is tested, if at all, (4) any other top-level imports in this file or nearby enterprise-optional files that could have the same startup-crash problem.

---

## 2. Codebase Findings

### Existing Implementations

**Core files directly involved:**
- `src/codemie/service/workflow_evaluation_service.py` — service that evaluates workflows against Langfuse datasets; site of the bug and the uncommitted fix. The `ExperimentItem` type is used only in the inner function signature `def item_task(*, item: ExperimentItem) -> str | None:` inside `_run_evaluation_task`. The fix moves `from langfuse.experiment import ExperimentItem` from module top-level into an `if TYPE_CHECKING:` block (lines 22–24). `from __future__ import annotations` is present at line 17 and `from typing import TYPE_CHECKING` at line 19, so the annotation is never evaluated at runtime.
- `src/codemie/enterprise/loader.py` — central enterprise capability registry. Wraps every enterprise SDK import (`codemie_enterprise.langfuse`, `.litellm`, `.plugin`, `.idp`, `.mcp_auth`) in `try/except ImportError` blocks. Sets `HAS_LANGFUSE`, `HAS_LITELLM`, `HAS_PLUGIN`, `HAS_IDP`, `HAS_MCP_AUTH`, `HAS_LLM_OBSERVABILITY` flags. Its module docstring is an inline architectural decision: _"CRITICAL: This loader ONLY handles imports and flags. NO business logic."_ In OSS builds, all `HAS_*` flags are `False` and all enterprise types resolve to `None`.
- `src/codemie/enterprise/langfuse/dependencies.py` — defines `require_langfuse_client()`, `get_langfuse_service()`, `is_langfuse_enabled()`, and all Langfuse DI helpers. Re-exports everything via `src/codemie/enterprise/langfuse/__init__.py`. Reads `LANGFUSE_HOST`, `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY` directly from `os.environ`.
- `src/codemie/enterprise/langfuse/__init__.py` — re-exports `dependencies.py` and `workflows.py`.
- `src/codemie/enterprise/observability/langfuse_provider.py` — the only other file in `src/` that imports directly from the `langfuse` pip package (`from langfuse.langchain.CallbackHandler import CONTROL_FLOW_EXCEPTION_TYPES`). Crucially, this import is NOT at module top level — it is inside the `_register_control_flow_exceptions()` method body under a `try/except Exception` block. Not at risk of a startup crash.
- `src/codemie/service/assistant_evaluation_service.py` — parallel evaluation service for assistants. Follows the same `require_langfuse_client` pattern; no direct `from langfuse.*` import at module level. A safe reference implementation.
- `src/codemie/rest_api/routers/workflow.py` — REST router. Imports `WorkflowEvaluationService` from `codemie.service.workflow_evaluation_service` at line 47 (module top level). This import chain means any crash in `workflow_evaluation_service.py` at import time also crashes the router module and prevents FastAPI from starting.

**Uncommitted working tree change (already applied, unreviewed):**
The fix is already present in the working tree. Lines 19 and 22–24 of `workflow_evaluation_service.py` read:
```python
from typing import TYPE_CHECKING
...
if TYPE_CHECKING:
    from langfuse.experiment import ExperimentItem
```
`ExperimentItem` is used only at line 134 as a type annotation in `item_task`'s signature. With PEP 563 semantics (`from __future__ import annotations`), that annotation is never resolved at runtime. The fix is complete and consistent with the codebase convention.

### Architecture and Layers Affected

- **Service layer** — `workflow_evaluation_service.py` (primary change site); `assistant_evaluation_service.py` (reference)
- **Enterprise adapter layer** — `codemie.enterprise.langfuse.*` and `codemie.enterprise.loader` (unchanged by the fix; provide the HAS_LANGFUSE flag and require_langfuse_client enforcement)
- **REST API / Router layer** — `src/codemie/rest_api/routers/workflow.py`; endpoint `POST /workflows/{workflow_id}/evaluate`, response model `EvaluationResponse`. The router imports the service at module load time, so it is the entry point for the startup crash.
- **Build / packaging layer** — `Dockerfile` (`INSTALL_ENTERPRISE` build ARG); `pyproject.toml` (`enterprise` extras group)

### Integration Points

**Internal module dependencies:**
- `workflow_evaluation_service.py` → `codemie.enterprise.langfuse` (internal wrapper, always present, safe)
- `codemie.enterprise.langfuse.dependencies` → `codemie.enterprise.loader.HAS_LANGFUSE` (safe, guarded)
- `codemie.enterprise.loader` → `codemie_enterprise.*` (optional external package, guarded via try/except)
- `workflow.py` (router) → `workflow_evaluation_service.py` (module-level import — the crash propagation path)

**External service connections:**
- Langfuse OSS SDK (`langfuse` pip package) — transitive dependency only; installed exclusively via `codemie-enterprise` optional extra. Not listed anywhere in `pyproject.toml` as a direct dependency.
- Langfuse cloud/self-hosted API — accessed via `LANGFUSE_HOST`, `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY` env vars.

### Patterns and Conventions

The codebase uses a three-tier layered defense for optional enterprise dependencies:

1. **`loader.py` try/except ImportError** — canonical entry point. All `codemie_enterprise.*` symbols go through this file. Stubs are set to `None` on failure; `HAS_*` flags are set to `False`.
2. **`if TYPE_CHECKING:` guard for type-only annotations** — used in at least 20 files across `src/codemie/service/` and `src/codemie/enterprise/`. Always paired with `from __future__ import annotations` to ensure annotations are never evaluated at runtime. The fix for EPMCDME-13525 applies this pattern to `workflow_evaluation_service.py`.
3. **Deferred local import inside method body with try/except** — used in `langfuse_provider.py` for direct SDK imports that are needed at call time but should degrade gracefully if missing.

Runtime callers never check `HAS_LANGFUSE` directly; they call `require_langfuse_client()` which enforces availability and raises a typed HTTP 503 error if `HAS_LANGFUSE` is `False` or the client is `None`.

---

## 3. Documentation Findings

### Guides and Architecture Docs

- `.ai-run/guides/development/configuration-patterns.md` — directly relevant. The "Feature Flags" section explicitly names "Assuming enterprise features always exist" as an anti-pattern and prescribes the enterprise loader/provider abstraction instead. This is the guide-level authority for the TYPE_CHECKING fix.
- `.ai-run/guides/integration/external-services.md` — tangentially relevant. States that SDK calls must be kept behind adapter boundaries and not called from routers/handlers. Does not address optional imports directly.
- No dedicated langfuse guide exists under `.ai-run/guides/`.

### Architectural Decisions

- No formal ADR files found. The canonical decision is inline in `src/codemie/enterprise/loader.py` module docstring: _"CRITICAL: This loader ONLY handles imports and flags. NO business logic."_ This encodes the architectural rule that all optional enterprise package probing is centralized in `loader.py` using `try/except ImportError`, with `None` fallbacks and `HAS_*` flags. All other modules must read these flags rather than importing optional packages directly.
- The choice to keep `langfuse` absent from `pyproject.toml` as a direct dep (relying on `codemie-enterprise` as the only install vector) is a deliberate packaging decision. Any unguarded `from langfuse.*` at module top level is therefore a guaranteed `ModuleNotFoundError` in any OSS build.

### Derived Conventions

- Always use `from __future__ import annotations` together with `if TYPE_CHECKING:` guards. One without the other is insufficient.
- The enterprise package boundary is `codemie.enterprise.*` (internal wrapper modules). These modules are always present even in OSS builds; their internals gracefully degrade via `loader.py`. Imports of these wrappers at module top level are safe.
- Direct imports from the `langfuse` pip package (e.g. `from langfuse.experiment import ...`, `from langfuse.langchain import ...`) are the dangerous category — they bypass the wrapper and reach a package that may not be installed.
- `is_langfuse_enabled()` checks `HAS_LANGFUSE and config.LANGFUSE_TRACES` — both conditions must be true for Langfuse to be active. `HAS_LANGFUSE` is the installation guard; `LANGFUSE_TRACES` is the user-preference flag.

---

## 4. Testing Landscape

### Existing Coverage

- `tests/codemie/service/test_workflow_evaluation_service.py` — unit tests covering: happy path, 503 on missing Langfuse, 400 on missing dataset, background task scheduling, and item-task error propagation. All Langfuse interactions are mocked via `patch("codemie.service.workflow_evaluation_service.require_langfuse_client")`. These tests survive the TYPE_CHECKING fix with no changes — they never exercise the langfuse import path.
- `tests/codemie/rest_api/routers/test_workflow.py` — router-level tests referencing workflow evaluation (exact coverage scope not fully enumerated, but file confirmed relevant).
- `tests/enterprise/langfuse/test_dependencies.py` — tests `initialize_langfuse_from_config`, `get_langfuse_callback_handler`, `require_langfuse_client`, global service registry, and priority order (HAS_LANGFUSE > config).
- `tests/enterprise/langfuse/test_workflows.py` — tests `create_workflow_trace_context`: disabled case, session_id fallback, exception handling.
- `tests/enterprise/test_loader.py` — tests `HAS_LANGFUSE` flag, `LangFuseConfig`/`LangFuseService` None vs. populated, `has_langfuse()`, and migration loader symbols.
- `tests/enterprise/test_graceful_degradation.py` — tests that `get_langfuse_callback_handler()` returns None, `get_langfuse_client_or_none()` returns None, and `require_langfuse_client()` raises HTTP 503, all under the `mock_enterprise_not_installed` fixture.
- `tests/codemie/rest_api/test_startup_integration.py` — tests FastAPI `lifespan` startup and shutdown, LiteLLM init ordering, MCP auth init. Does NOT exercise an `INSTALL_ENTERPRISE=false` startup path for the workflow evaluation service.
- `tests/codemie/rest_api/security/jwks/test_no_enterprise.py` — OSS-compatibility test using `monkeypatch.setattr(loader, "HAS_IDP", False)` pattern. The closest existing model for testing the absence of an enterprise feature.
- `tests/codemie/triggers/bindings/test_webhook_rate_limiter_import.py` — uses `sys.modules.pop` + `importlib.import_module` to re-import a module after hiding an optional dependency. **This is the exact pattern needed for a regression test for this bug.**

### Testing Framework and Patterns

- pytest with `pytest-asyncio` and `pytest-env`; `--import-mode=importlib` (modules re-imported fresh per test file).
- **Enterprise presence fixtures** — `mock_enterprise_installed` / `mock_enterprise_not_installed` in `tests/enterprise/conftest.py`: use `monkeypatch.setattr` on `codemie.enterprise.loader.HAS_LANGFUSE` and related symbols.
- **Module-level import isolation** — `sys.modules.pop(module_name)` + `importlib.import_module(module_name)` used in `test_webhook_rate_limiter_import.py` to verify a module loads cleanly when an optional dependency is hidden.
- **AST static analysis** — `test_discovery_probe_bridge.py` uses `ast.parse` to assert enterprise-dependent imports are not present at module top level. Applicable pattern for adding an import-guard assertion for `workflow_evaluation_service.py`.
- **Session-scoped DB mock** — `tests/conftest.py` auto-uses a session fixture that mocks `PostgresClient.get_engine` to prevent DB connections in all tests.
- `.env.test` only sets `ENV=local`, `PG_URL`, `REPOS_LOCAL_DIR`. `INSTALL_ENTERPRISE` is not in the test environment config.

### Coverage Gaps

- **No regression test for the specific crash.** No test imports `workflow_evaluation_service` after evicting `langfuse` from `sys.modules`. If the TYPE_CHECKING guard were accidentally reverted, no test would catch it before a deployment.
- **No OSS startup integration test.** `test_startup_integration.py` does not simulate a clean `INSTALL_ENTERPRISE=false` environment (no enterprise package at all).
- **No AST guard test** for `workflow_evaluation_service.py` asserting that `from langfuse.*` imports only appear inside `if TYPE_CHECKING:` blocks.

---

## 5. Configuration and Environment

### Environment Variables

- `LANGFUSE_TRACES` — Pydantic config field, default `False`. Feature flag enabling Langfuse request tracing.
- `LANGFUSE_HOST` — Langfuse server URL, default `https://cloud.langfuse.com`. Read in `dependencies.py` via `os.environ.get`.
- `LANGFUSE_PUBLIC_KEY` — Langfuse API public key. Required for client initialization; None if absent.
- `LANGFUSE_SECRET_KEY` — Langfuse API secret key. Required for client initialization; None if absent.
- `LANGFUSE_BLOCKED_INSTRUMENTATION_SCOPES` — list of OTEL scopes to suppress from Langfuse tracing.
- `LLM_PROXY_LANGFUSE_TRACES` — flag for LiteLLM-proxy-side Langfuse tracing, default `False`.
- `OBSERVABILITY_PROVIDER` — selects backend: `"langfuse"` | `"phoenix"` | `"none"`. Backward-compat: if `"none"` but `LANGFUSE_TRACES=True`, Langfuse is still used.
- `INSTALL_ENTERPRISE` — Docker build ARG only (not a runtime env var). Default `true` in Dockerfile.

### Configuration Files

- `src/codemie/configs/config.py` (lines 500–510) — declares `LANGFUSE_TRACES: bool = False`, `LANGFUSE_BLOCKED_INSTRUMENTATION_SCOPES`, `OBSERVABILITY_PROVIDER: str = "none"`, `LLM_PROXY_LANGFUSE_TRACES: bool = False`.
- `pyproject.toml` — `[tool.poetry.extras]`: `enterprise = ["codemie-enterprise"]`; `codemie-enterprise` pinned at `2.3.34`, `optional = true`, sourced from GCP Artifact Registry. `langfuse` has no direct entry in `pyproject.toml`; it is only a transitive dep of `codemie-enterprise`.
- `Dockerfile` — `ARG INSTALL_ENTERPRISE=true` (line 16). Builder stage branches on this ARG: `true` → `poetry install --only main -E enterprise --no-root` (requires GCP keyring auth secret); `false` → `poetry install --only main --no-root` (OSS, no enterprise extra, no langfuse).
- `Makefile` — exposes `install-enterprise` (`poetry install -E enterprise --sync`) and `install-oss` (`poetry install --sync`) as explicit local targets.
- `docker-compose.yml` — does not pass `INSTALL_ENTERPRISE` as a build arg; uses Dockerfile default (`true`). No `LANGFUSE_*` env vars in compose. Local dev always runs enterprise build.

### Feature Flags and Deployment Concerns

- `HAS_LANGFUSE` (runtime bool, set in `loader.py`) — `True` only if `codemie_enterprise.langfuse` imports without error. `False` in all OSS builds. Checked first in every Langfuse code path.
- `HAS_LLM_OBSERVABILITY` = `HAS_LANGFUSE or HAS_PHOENIX` — composite flag; recommended for callers that support multiple observability backends.
- `is_langfuse_enabled()` — combines both: `HAS_LANGFUSE and config.LANGFUSE_TRACES`.
- Deployment concern: `docker-compose.yml` always runs enterprise build locally, making it easy to miss OSS startup regressions during development. The `install-oss` Makefile target can be used locally but requires the developer to actively switch.
- Helm `deploy-templates/values.yaml` — no `LANGFUSE_*` or `INSTALL_ENTERPRISE` keys; these are injected via CI/CD pipeline value overrides.

---

## 6. Risk Indicators

- **No regression test for the import-level crash.** The TYPE_CHECKING fix has no accompanying test that evicts `langfuse` from `sys.modules` and re-imports `workflow_evaluation_service` to confirm clean loading. The `test_webhook_rate_limiter_import.py` pattern (`sys.modules.pop` + `importlib.import_module`) is the correct template. Without this test, a future accidental revert of the `if TYPE_CHECKING:` guard would ship undetected.
- **No AST guard test for `workflow_evaluation_service.py`.** The pattern exists in `test_discovery_probe_bridge.py` (uses `ast.parse` to assert no enterprise imports at module top level) but is not applied to this file.
- **No OSS startup integration test.** `test_startup_integration.py` does not simulate a build with no enterprise package installed; it only patches individual `HAS_*` flags post-import. A true OSS startup simulation would require hiding `codemie_enterprise` from `sys.modules` before the application is imported.
- **Router imports service at module top level.** `src/codemie/rest_api/routers/workflow.py` imports `WorkflowEvaluationService` at line 47. Any future regression in `workflow_evaluation_service.py` that crashes at import time will also crash the router and prevent FastAPI from starting — the blast radius is the entire API server, not just this endpoint.
- **`docker-compose.yml` always installs enterprise.** Local development always uses `INSTALL_ENTERPRISE=true`, so the OSS startup path is never exercised during routine local dev. Developers must actively use `make install-oss` to reproduce this class of issue.
- **`langfuse` has zero direct entries in `pyproject.toml`.** Any future code that directly imports from `langfuse.*` at module top level will silently work in enterprise builds and crash in OSS builds. There is no tooling guard (e.g. a linting rule) that prevents this pattern from being reintroduced.
- **`dependencies.py` reads `LANGFUSE_*` env vars via `os.environ.get` at init time**, not through the Pydantic config class. This means these vars are not visible in the config schema and are not validated at startup.

---

## 7. Summary for Complexity Assessment

This task is a **single-file, one-line-class fix** (moving one import block from module top level into `if TYPE_CHECKING:`) already applied in the uncommitted working tree. The fix touches exactly one source file (`src/codemie/service/workflow_evaluation_service.py`), makes zero runtime behavior changes, and is fully consistent with the established codebase convention (used in at least 20 other files across the service and enterprise layers). The architectural layers touched are limited to the service layer import structure and the build/packaging layer — no database models, no API contracts, no config schema changes. The change surface is minimal: the diff adds three lines and removes one.

The fix does not introduce any new patterns. It applies pattern #2 from the codebase's three-tier optional-import defense: `if TYPE_CHECKING:` guard paired with `from __future__ import annotations`, which is already the norm across `src/codemie/service/` and `src/codemie/enterprise/`. The only other direct `from langfuse.*` import in the codebase (`langfuse_provider.py`) is already safely guarded inside a method body with try/except, so this file was the sole remaining violation.

The primary risk is not the fix itself but the absence of a regression test. The existing test suite for `workflow_evaluation_service.py` mocks `require_langfuse_client` at the call site and does not exercise the module import path at all; it would pass even if the `if TYPE_CHECKING:` guard were removed. Two test templates already exist in the codebase for this scenario: `test_webhook_rate_limiter_import.py` (module re-import with optional dep hidden via `sys.modules.pop`) and `test_discovery_probe_bridge.py` (AST-level assertion of no enterprise imports at module top level). Adding one of these patterns as a dedicated test for `workflow_evaluation_service.py` is the only non-trivial work remaining and should accompany the fix to prevent silent regression. Overall complexity is low; the delivery risk is also low given the fix is already written and aligns with established patterns.
