# Technical Research

**Task**: user management logging observability backend
**Generated**: 2026-07-02T00:00:00Z

---

## 1. Original Context

Unify user management logs on the backend side. Standardize backend logs related to user management so that they can be easily identified and separated from other application logs. This will improve observability and make audit-related troubleshooting faster and more reliable.

Acceptance Criteria:
1. User-management-related backend logs follow a unified format or tagging approach.
2. User-management logs are easily distinguishable from other backend logs.
3. Existing important logging information is preserved after unification.
4. The updated logging approach is applied to key user-management operations.

---

## 2. Codebase Findings

### Existing Implementations

The user management domain is well-factored into a dedicated service package. The following files contain logging that must be unified:

**Service layer (`src/codemie/service/user/`):**
- `user_management_service.py` — CRUD and admin operations, bootstrap; 14 logger calls. Uses `snake_case` event keys for most operations (`user_created`, `user_updated`, `user_deactivated`), but has free-form prose for secondary messages (e.g. `"SuperAdmin already exists, skipping bootstrap"`, budget provisioning warnings).
- `authentication_service.py` — Local, IDP, and dev-header auth flows; 12 logger calls. Uses mixed styles: some follow `event_key: field=value` format (`user_created`, `IDP user migrated`), others use natural prose (`"User authenticated: ..."`, `"User logged in: ..."`, `"User creation race condition handled: ..."`).
- `registration_service.py` — New-user registration and email verification; 4 logger calls. Free-form prose throughout (`"User registered: ..."`, `"Email verified: ..."`).
- `user_access_service.py` — Project and KB access grants/revocations; 8 logger calls. Most already follow `event_key: field=value` format via a `_build_project_access_log_details()` helper. KB access calls are inline and consistent. `_log_project_authorization_failure()` produces structured warning.
- `user_profile_service.py` — Self-service profile updates; 2 logger calls. Prose style (`"Profile updated: user_id=..."`, `"Failed to send verification email..."`).
- `password_management_service.py` — Password change and reset; 4 logger calls. Split style: `password_changed: target_user_id=` (snake_case key) in one path, `"Password reset completed: ..."` and `"Password reset token created: ..."` in prose.
- `application_service.py` — Application/project creation helper called during user flows; 3 logger calls. Prose style.

**Security layer (`src/codemie/rest_api/security/`):**
- `authentication.py` — Auth decorators (`admin_access_only`, `maintainer_access_only`, `project_admin_or_admin_user_detail_access`); 10 logger calls. All prose with no structured field anchors (`"Access denied: admin or maintainer privileges required"`, etc). No `user_id` or `actor_user_id` included in these messages.

**Router layer (`src/codemie/rest_api/routers/`):**
- `user_management_router.py` — `/v1/admin/users` API surface; no direct `logger` calls (logging delegated to service).
- `local_auth_router.py` — `/v1/local-auth` endpoints; no direct `logger` calls.
- `user_profile_router.py` — Self-service profile endpoint; no direct `logger` calls.

**Logging infrastructure (`src/codemie/configs/`):**
- `logger.py` — Defines `LogConfig` with a structured JSON format (`LOG_FORMAT`) that includes `uuid`, `user_id`, `conversation_id`, `trace_id`, `span_id`, and `message` fields. Log message content itself is not further structured by the formatter; it is an opaque string. The central logger is `logging.getLogger("codemie")`. Context variables (`logging_uuid`, `logging_user_id`, `logging_conversation_id`) are injected via `record_factory`.

### Architecture and Layers Affected

The task touches three architectural layers:

1. **Service layer** (`src/codemie/service/user/`) — Primary target. All seven service files contain log calls that will be normalized.
2. **Security/auth layer** (`src/codemie/rest_api/security/authentication.py`) — Secondary target. Access-denied warnings lack structured field context.
3. **Logging infrastructure** (`src/codemie/configs/logger.py`) — Read-only for this task. No changes to the formatter or LogConfig are expected; the task is a message content standardization, not a formatter change.

### Integration Points

- All user service files import `logger` directly from `codemie.configs.logger`.
- `authentication.py` imports from the same logger module.
- The structured JSON log envelope already carries request-scoped `user_id` and `uuid` via context variables set by `set_logging_info()` in the middleware. The `message` field is the only variable part being standardized.
- Tests mock `codemie.service.user.<module>.logger` at the module level (not the global `codemie.configs.logger`). Any log-message format change propagates directly to these mocks.

### Patterns and Conventions

The codebase already exhibits an emerging convention in the more recently written service files, clearly seen in `user_management_service.py` and `user_access_service.py`:

- **Event key prefix**: Structured `snake_case` event name at the start of the message (e.g. `user_created:`, `user_deactivated:`, `project_access_granted:`).
- **Field list as key=value pairs**: `actor_user_id=`, `target_user_id=`, `auth_source=`, separated by commas or spaces.
- **No PII**: Email addresses are absent; only IDs and non-sensitive flags are logged.
- **Helper builder pattern**: `_build_project_access_log_details()` in `user_access_service.py` centralises the field-building for project access operations.
- **Warning messages for security events**: Structured warning format with `blocked_<event>:` prefix for admin-protection violations, including `timestamp=`.

The inconsistencies against this convention are:

| File | Inconsistent calls | Style deficit |
|---|---|---|
| `authentication_service.py` | `"User authenticated: ..."`, `"User logged in: ..."`, `"IDP user migrated: ..."`, `"User creation race condition handled: ..."` | Prose, no event key |
| `registration_service.py` | `"User registered: ..."`, `"Email verified: ..."` | Prose, no event key |
| `user_profile_service.py` | `"Profile updated: user_id=..."` | Sentence case, not snake_case key |
| `password_management_service.py` | `"Password reset completed: ..."`, `"Password reset token created: ..."` | Prose |
| `authentication.py` (security) | All 10 `"Access denied: ..."` calls | No `user_id` / `actor_user_id` field |

---

## 3. Documentation Findings

### Guides and Architecture Docs

- `.ai-run/guides/development/logging-patterns.md` — Present and directly relevant. Defines two rules: (1) log operation, IDs, status and sanitized details; (2) match severity to operational impact. Cites `authentication.py:114` as the reference implementation for unexpected-error logging, and `rest_api/main.py:826` as the reference for 5xx vs lower-status error differentiation.
- `.ai-run/guides/development/security-patterns.md` — Relevant as user management operations are security-sensitive (auth, admin actions, access revocation).
- No ADR files or design docs were found for the user management logging format specifically.

### Architectural Decisions

- The `record_factory` in `logger.py` automatically injects `user_id` from the `logging_user_id` context variable into every log record's envelope. This means the middleware-set `user_id` is always present in the structured envelope regardless of message content. Log messages that repeat `user_id=X` in the message body are therefore redundant from an envelope standpoint, but the convention is maintained for message-level grep and log-filter discoverability.
- The `LOG_FORMAT` uses a JSON envelope but the `message` field is an escaped JSON string produced by `process_record_msg()`. Message content searchability depends on string-matching within the `message` field value.
- The `LOGGER_NAME = "codemie"` logger is the sole logger used across all user management files — no sub-logger per module.

### Derived Conventions

From the most recently written and best-conforming service files (`user_management_service.py`, `user_access_service.py`):

1. INFO-level events use `snake_case_event_key: field1=value1, field2=value2` format.
2. WARNING-level security events use `blocked_<action>:` or `<event>_failed:` prefix with full field context and `timestamp=`.
3. Actor context is always included: `actor_user_id=` for admin-initiated actions; `target_user_id=` for the affected user.
4. `auth_source=` is logged on user creation events.
5. No email addresses or passwords appear in any log message.
6. DEBUG-level logs use prose or terse format (cache hits, token creation).

---

## 4. Testing Landscape

### Existing Coverage

The user management domain is heavily tested with log assertions already present:

- `tests/codemie/service/user/test_user_management_service_super_admin.py` — Asserts warning log content for `blocked_self_revocation`, `blocked_last_admin_revocation`, `blocked_last_admin_deactivation` including field presence (`actor_user_id=`, `target_user_id=`, `timestamp=`).
- `tests/codemie/service/user/test_user_access_service.py` — Asserts `project_access_granted`, `project_access_updated`, `project_access_removed`, `project_authorization_failed` log messages including field values.
- `tests/codemie/service/user/test_authentication_service.py` — Asserts `user_id=` in failed login warning at line 172–173. Other log calls in this file are not asserted.
- `tests/codemie/service/user/test_user_management_service_create_local_user.py`, `test_user_management_service_projects.py`, `test_user_management_service_project_limit.py`, `test_user_management_service_field_editability.py` — Test operational correctness; most do not assert on specific log messages except in super_admin tests.
- `tests/codemie/configs/test_logger.py`, `test_logger_pytest.py` — Test the formatter itself (`process_record_msg`, `LogFormatter`), not message content.

### Testing Framework and Patterns

- **Framework**: pytest with `unittest.mock`. `@patch("codemie.service.user.<module>.logger")` is the universal pattern — patches the module-level `logger` binding, not the global logger.
- **Assertions**: `mock_logger.info.assert_called_once()` followed by `mock_logger.info.call_args[0][0]` string-contains assertions (e.g. `assert "user_id=..." in log_message`).
- **No fixture for logger**: Each test that needs it declares its own `mock_logger` via `@patch`.
- Tests are class-based (`class TestX`) with `def test_*` methods inside.

### Coverage Gaps

- `registration_service.py` logs are not asserted in `test_registration_service.py` (the test exists but does not mock logger).
- `user_profile_service.py` logs are not asserted in `test_user_profile_service.py`.
- `password_management_service.py` INFO logs are not asserted in `test_password_management_service.py` (only `password_changed:` admin-override path may have partial coverage).
- `authentication_service.py` — only the failed-login warning is asserted; the success INFO paths (`User authenticated`, `User logged in`, `user_created`, `IDP user migrated`) have no log assertions.
- `authentication.py` (security layer) access-denied warnings have no test assertions.

---

## 5. Configuration and Environment

### Environment Variables

- `LOG_LEVEL` (default `"INFO"`) — controls the log level applied to the `codemie` logger in `LogConfig`. Relevant to whether DEBUG-level user management logs surface.
- `ENABLE_USER_MANAGEMENT` (default `False`) — master switch that gates all `/v1/admin/users` endpoints. Relevant for context: user management logs only fire when this is `True` or when auth flows run regardless.
- `ENV` — determines `is_local` flag; when `local`, the human-readable `LOCAL_LOG_FORMAT` is used instead of JSON. Affects how log messages are rendered but not their content.
- `IDP_PROVIDER` — `"local"` vs IDP mode; several log messages embed `auth_source={config.IDP_PROVIDER}`.

### Configuration Files

- `src/codemie/configs/logger.py` — Central logger configuration; `LogConfig` model; `record_factory`; `set_logging_info()`. This file defines the JSON envelope format. Not expected to change for this task.
- `src/codemie/configs/config.py` — `LOG_LEVEL` and `ENV` are defined here. `ENABLE_USER_MANAGEMENT` is also here.
- `log_conf.prod.json` — Uvicorn-level log config (covers access/error loggers for uvicorn, not the application `codemie` logger). Not part of this task scope.
- `pytest.ini` — Sets `ENV=local` for all tests, ensuring human-readable format is active during testing.

### Feature Flags and Deployment Concerns

- `ENABLE_USER_MANAGEMENT=True` must be set in deployment for admin user management endpoints (and thus most of the log lines in `user_management_service.py`) to be reachable.
- No feature flags control logging behavior itself.
- No secrets management or vault interaction in the logging path.

---

## 6. Risk Indicators

- **Format mismatch in authentication_service.py**: The file uses both the new structured format (`user_created:`) and prose (`"User authenticated: ..."`, `"User logged in: ..."`). Renaming the prose lines to snake_case keys must be coordinated with any existing log monitoring dashboards or alerting rules that match on the old string.
- **authentication.py (security layer) access-denied warnings carry no field context**: Adding `user_id` to these warnings introduces a behavior change but no audit trail currently exists for access denials at the auth layer. The `user_id` is available in the request context.
- **Test brittleness**: 9+ existing tests assert on exact log message substrings. Any format change to currently-asserted messages (e.g. `blocked_self_revocation`, `project_access_granted`) will break those tests. Changes to currently-unasserted messages are safe initially but should be followed by new test coverage.
- **Duplicate `user_created` log in `user_management_service.py`**: `create_local_user` logs `user_created` at line 119 and `create_local_user_with_flow` logs it again at line 570 for the same operation. The outer flow log (570) includes `actor_user_id` while the inner one (119) does not. This duplication should be rationalized as part of unification.
- **No `actor_user_id` in authentication_service.py security warnings**: The `authentication.py` access-denied warnings at lines 163, 176, 189, 235, 259, 268, 282, 294, 309 do not include the requesting user's ID, making audit reconstruction harder.
- **`user_profile_service.py` and `registration_service.py` logs are untested**: Changing their format is low-risk for test breakage but high-risk for silent regression if coverage is not added.
- **No shared log-detail builder for all user management events**: `user_access_service.py` uses `_build_project_access_log_details()` but the pattern is not shared across services. A task-scoped helper or consistent inline convention is needed.

---

## 7. Summary for Complexity Assessment

This task is a message-content standardization across 7 service files and 1 security module. The architectural layers touched are Service (primary) and Security/Auth (secondary); the router layer and logging infrastructure are not changed. Estimated file change surface: 8 files. The number of individual log call sites is approximately 52 across the domain (34 in service files, 10 in `authentication.py`, plus application_service.py's 3). Of these, roughly 15 already conform to the target convention and 37 require normalization of message content only — no logic changes.

The task follows an established but partially-applied pattern: the `snake_case event_key: field=value` convention is already present in the best-conforming files and is documented in `.ai-run/guides/development/logging-patterns.md`. There is no novel pattern to introduce; the work is closing the gap between existing best practice and lagging files. The primary technical subtlety is the duplicate `user_created` log in `user_management_service.py` (lines 119 and 570), which should be resolved by removing or scoping one of them, and the absence of `user_id` context in the `authentication.py` access-denied warnings, which requires threading the `user` dependency into those warning calls.

Test coverage posture is mixed: the audit-critical paths (admin revocation, access grants) are well-tested with log assertions and will require test updates when their messages change format. The authentication success paths, registration paths, profile update, and password paths have no log assertions and represent coverage gaps. Adding test coverage for the newly standardized messages in those paths is advisable but not strictly required by the acceptance criteria. The risk of breaking existing CI is moderate: any message change touching the ~9 assertion-bearing tests (in `test_user_management_service_super_admin.py` and `test_user_access_service.py`) must update those assertions simultaneously.
