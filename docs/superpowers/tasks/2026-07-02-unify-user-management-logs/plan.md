# Unify User Management Logs — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Normalize all user-management log messages to `snake_case_event_key: field=value, domain=user_management` so that operations teams can filter audit logs with a single regexp.

**Architecture:** Message-content-only changes across 8 files (7 in `service/user/`, 1 in `rest_api/security/`). No formatter, no schema, no router changes. Tests with existing log assertions are updated first (RED), then the source files are updated (GREEN). Files with no existing log assertions are updated directly.

**Tech Stack:** Python, `logging` stdlib, pytest + `unittest.mock`, Poetry

---

## File Map

| File | Change type |
|---|---|
| `src/codemie/service/user/user_access_service.py` | Add `, domain=user_management` to 6 calls |
| `tests/codemie/service/user/test_user_access_service.py` | Add `domain=user_management` assertion to 4 tests |
| `src/codemie/service/user/user_management_service.py` | Add domain to 9 calls; normalize 2; enrich `user_updated`; remove inner duplicate |
| `tests/codemie/service/user/test_user_management_service_super_admin.py` | Add `domain=user_management` assertion to 4 assertions |
| `src/codemie/service/user/authentication_service.py` | Normalize 5 INFO calls + 1 WARNING; add domain to all 7 affected calls |
| `tests/codemie/service/user/test_authentication_service.py` | Update 1 warning assertion |
| `src/codemie/service/user/password_management_service.py` | Normalize 2 calls; add domain to all 4 |
| `src/codemie/service/user/registration_service.py` | Normalize 2 calls; add domain |
| `src/codemie/service/user/user_profile_service.py` | Normalize 2 calls; add domain |
| `src/codemie/service/user/application_service.py` | Normalize 1 INFO call; add domain |
| `src/codemie/rest_api/security/authentication.py` | Replace 10 prose warnings with `access_denied_*:` + `actor_user_id` + domain |

---

### Task 1: user_access_service — update test assertions (RED)

**Files:**
- Modify: `tests/codemie/service/user/test_user_access_service.py`

- [ ] **Step 1: Add `domain=user_management` assertions to the 4 tests that check log messages**

In `test_grant_project_access_success` (around line 155), add after the existing assertions:
```python
assert "domain=user_management" in log_message
```

In `test_update_project_access_success` (around line 288), add after existing assertions:
```python
assert "domain=user_management" in log_message
```

In `test_remove_project_access_success` (around line 411), add after existing assertions:
```python
assert "domain=user_management" in log_message
```

In `test_grant_project_access_project_not_found` (around line 210), add after `assert "project_authorization_failed" in log_message`:
```python
assert "domain=user_management" in log_message
```

- [ ] **Step 2: Run the tests to confirm they fail (RED)**

```bash
poetry run pytest tests/codemie/service/user/test_user_access_service.py -v -k "test_grant_project_access_success or test_update_project_access_success or test_remove_project_access_success or test_grant_project_access_project_not_found" 2>&1 | tail -20
```
Expected: FAIL — `AssertionError: assert 'domain=user_management' in '...'`

---

### Task 2: user_access_service — add `domain=user_management` to log calls (GREEN)

**Files:**
- Modify: `src/codemie/service/user/user_access_service.py`

- [ ] **Step 1: Update the 3 project access INFO calls (lines ~98, ~126, ~151)**

Change each `f"project_access_granted: {log_details}"` pattern:
```python
# Before (line ~98):
logger.info(f"project_access_granted: {log_details}")
# After:
logger.info(f"project_access_granted: {log_details}, domain=user_management")

# Before (line ~126):
logger.info(f"project_access_updated: {log_details}")
# After:
logger.info(f"project_access_updated: {log_details}, domain=user_management")

# Before (line ~151):
logger.info(f"project_access_removed: {log_details}")
# After:
logger.info(f"project_access_removed: {log_details}, domain=user_management")
```

- [ ] **Step 2: Update the 2 KB access INFO calls (lines ~221, ~258)**

```python
# Before (line ~221):
logger.info(f"kb_access_granted: actor_user_id={actor_user_id}, target_user_id={user_id}, kb={kb_name}")
# After:
logger.info(f"kb_access_granted: actor_user_id={actor_user_id}, target_user_id={user_id}, kb={kb_name}, domain=user_management")

# Before (line ~258):
logger.info(f"kb_access_removed: actor_user_id={actor_user_id}, target_user_id={user_id}, kb={kb_name}")
# After:
logger.info(f"kb_access_removed: actor_user_id={actor_user_id}, target_user_id={user_id}, kb={kb_name}, domain=user_management")
```

- [ ] **Step 3: Update the `project_authorization_failed` WARNING (line ~314)**

```python
# Before:
logger.warning(f"project_authorization_failed: {log_details}")
# After:
logger.warning(f"project_authorization_failed: {log_details}, domain=user_management")
```

- [ ] **Step 4: Run the tests to confirm they pass (GREEN)**

```bash
poetry run pytest tests/codemie/service/user/test_user_access_service.py -v 2>&1 | tail -20
```
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/codemie/service/user/user_access_service.py tests/codemie/service/user/test_user_access_service.py
git commit -m "EPMCDME-13273: Add domain=user_management to user_access_service logs"
```

---

### Task 3: user_management_service — update test assertions (RED)

**Files:**
- Modify: `tests/codemie/service/user/test_user_management_service_super_admin.py`

The tests that assert on log messages are:
- `test_self_revocation_blocked` (line ~111–115): asserts `blocked_self_revocation`, `actor_user_id=super-admin-1`, `target_user_id=super-admin-1`
- `test_last_admin_status_revocation_blocked` (line ~147–149): asserts `blocked_last_admin_revocation`
- `test_last_admin_deactivation_blocked` (line ~177–179): asserts `blocked_last_admin_deactivation`
- `test_blocked_operations_are_logged` (line ~457–460): asserts `blocked_self_revocation`, `actor_user_id`, `target_user_id`, `timestamp=`

- [ ] **Step 1: Add `domain=user_management` assertion to the 4 log-asserting tests**

In `test_self_revocation_blocked`, after `assert "target_user_id=super-admin-1" in log_call`:
```python
assert "domain=user_management" in log_call
```

In `test_last_admin_status_revocation_blocked`, after `assert "blocked_last_admin_revocation" in log_call`:
```python
assert "domain=user_management" in log_call
```

In `test_last_admin_deactivation_blocked`, after `assert "blocked_last_admin_deactivation" in log_call`:
```python
assert "domain=user_management" in log_call
```

In `test_blocked_operations_are_logged`, after `assert "timestamp=" in log_call`:
```python
assert "domain=user_management" in log_call
```

- [ ] **Step 2: Run the tests to confirm they fail (RED)**

```bash
poetry run pytest tests/codemie/service/user/test_user_management_service_super_admin.py -v -k "test_self_revocation_blocked or test_last_admin_status_revocation_blocked or test_last_admin_deactivation_blocked or test_blocked_operations_are_logged" 2>&1 | tail -20
```
Expected: FAIL — `AssertionError: assert 'domain=user_management' in '...'`

---

### Task 4: user_management_service — normalize and enrich log calls (GREEN)

**Files:**
- Modify: `src/codemie/service/user/user_management_service.py`

- [ ] **Step 1: Remove the duplicate `user_created` log from `create_local_user` (line ~119)**

```python
# Before (line ~119, inside create_local_user):
user = user_repository.create(session, user)
logger.info(f"user_created: target_user_id={user.id}, auth_source=local, is_admin={is_admin}")
return user

# After:
user = user_repository.create(session, user)
return user
```

- [ ] **Step 2: Enrich `user_updated` with audit fields and add domain (line ~215)**

```python
# Before:
logger.info(f"user_updated: actor_user_id={actor_user_id}, target_user_id={user_id}")

# After:
role_fields = {k: fields[k] for k in ("is_admin", "is_maintainer", "project_limit") if k in fields}
extra = (", " + ", ".join(f"{k}={v}" for k, v in role_fields.items())) if role_fields else ""
logger.info(f"user_updated: actor_user_id={actor_user_id}, target_user_id={user_id}{extra}, domain=user_management")
```

- [ ] **Step 3: Add `domain=user_management` to `blocked_last_admin_deactivation` (lines ~242–245)**

```python
# Before:
msg = (
    f"blocked_last_admin_deactivation: actor_user_id={actor_user_id}, "
    f"target_user_id={user_id}, action=deactivate, timestamp={datetime.now(UTC)}"
)
# After:
msg = (
    f"blocked_last_admin_deactivation: actor_user_id={actor_user_id}, "
    f"target_user_id={user_id}, action=deactivate, timestamp={datetime.now(UTC)}, domain=user_management"
)
```

- [ ] **Step 4: Add `domain=user_management` to `user_deactivated` (line ~254)**

```python
# Before:
logger.info(f"user_deactivated: actor_user_id={actor_user_id}, target_user_id={user_id}")
# After:
logger.info(f"user_deactivated: actor_user_id={actor_user_id}, target_user_id={user_id}, domain=user_management")
```

- [ ] **Step 5: Normalize `bootstrap_superadmin_startup` logs (lines ~407, ~410)**

```python
# Before (line ~407):
logger.info(f"SuperAdmin bootstrapped: user_id={superadmin_id}")
# After:
logger.info(f"superadmin_bootstrapped: target_user_id={superadmin_id}, domain=user_management")

# Before (line ~410):
logger.info("SuperAdmin already exists, skipping bootstrap")
# After:
logger.info("superadmin_bootstrap_skipped: domain=user_management")
```

- [ ] **Step 6: Add `domain=user_management` to `user_created` in `create_local_user_with_flow` (line ~570)**

```python
# Before:
logger.info(f"user_created: actor_user_id={actor_user_id}, target_user_id={new_user_id}")
# After:
logger.info(f"user_created: actor_user_id={actor_user_id}, target_user_id={new_user_id}, domain=user_management")
```

- [ ] **Step 7: Add `domain=user_management` to `blocked_self_revocation` (lines ~605–608)**

```python
# Before:
msg = (
    f"blocked_self_revocation: actor_user_id={actor_user_id}, "
    f"target_user_id={user_id}, action=revoke_self, timestamp={datetime.now(UTC)}"
)
# After:
msg = (
    f"blocked_self_revocation: actor_user_id={actor_user_id}, "
    f"target_user_id={user_id}, action=revoke_self, timestamp={datetime.now(UTC)}, domain=user_management"
)
```

- [ ] **Step 8: Add `domain=user_management` to `blocked_last_admin_revocation` (lines ~614–617)**

```python
# Before:
msg = (
    f"blocked_last_admin_revocation: actor_user_id={actor_user_id}, "
    f"target_user_id={user_id}, action=revoke_last, timestamp={datetime.now(UTC)}"
)
# After:
msg = (
    f"blocked_last_admin_revocation: actor_user_id={actor_user_id}, "
    f"target_user_id={user_id}, action=revoke_last, timestamp={datetime.now(UTC)}, domain=user_management"
)
```

- [ ] **Step 9: Add `domain=user_management` to `project_limit_auto_management` and `project_limit_override_ignored` (lines ~689, ~693, ~750)**

```python
# Before (line ~689):
logger.info(f"project_limit_auto_management: user_id={user_id}, action=promotion, limit=NULL")
# After:
logger.info(f"project_limit_auto_management: user_id={user_id}, action=promotion, limit=NULL, domain=user_management")

# Before (line ~693):
logger.info(f"project_limit_auto_management: user_id={user_id}, action=demotion, limit=3")
# After:
logger.info(f"project_limit_auto_management: user_id={user_id}, action=demotion, limit=3, domain=user_management")

# Before (line ~750):
logger.warning(f"project_limit_override_ignored: user={user_id}, value={project_limit}")
# After:
logger.warning(f"project_limit_override_ignored: user={user_id}, value={project_limit}, domain=user_management")
```

- [ ] **Step 10: Run the super_admin tests to confirm they pass (GREEN)**

```bash
poetry run pytest tests/codemie/service/user/test_user_management_service_super_admin.py -v 2>&1 | tail -20
```
Expected: All tests PASS

- [ ] **Step 11: Run the full user management test suite to confirm no regressions**

```bash
poetry run pytest tests/codemie/service/user/ -v 2>&1 | tail -30
```
Expected: All tests PASS

- [ ] **Step 12: Commit**

```bash
git add src/codemie/service/user/user_management_service.py tests/codemie/service/user/test_user_management_service_super_admin.py
git commit -m "EPMCDME-13273: Normalize user_management_service logs with domain marker and role audit fields"
```

---

### Task 5: authentication_service — update test assertion (RED)

**Files:**
- Modify: `tests/codemie/service/user/test_authentication_service.py`

The test `test_authenticate_local_wrong_password` (around line 160–173) asserts on the failed login warning:
```python
mock_logger.warning.assert_called_once()
assert f"user_id={user_id}" in mock_logger.warning.call_args[0][0]
```

The source will change `"Failed login attempt: user_id={user.id}"` to `"login_failed: target_user_id={user.id}, domain=user_management"`.

- [ ] **Step 1: Update the failing-login assertion**

Replace the existing `assert f"user_id={user_id}" in ...` with:
```python
mock_logger.warning.assert_called_once()
log_call = mock_logger.warning.call_args[0][0]
assert "login_failed" in log_call
assert f"target_user_id={user_id}" in log_call
assert "domain=user_management" in log_call
```

- [ ] **Step 2: Run the test to confirm it fails (RED)**

```bash
poetry run pytest tests/codemie/service/user/test_authentication_service.py -v -k "test_authenticate_local_wrong_password" 2>&1 | tail -15
```
Expected: FAIL — `assert 'login_failed' in 'Failed login attempt: ...'`

---

### Task 6: authentication_service — normalize log calls (GREEN)

**Files:**
- Modify: `src/codemie/service/user/authentication_service.py`

- [ ] **Step 1: Normalize the failed-login WARNING (line ~110)**

```python
# Before:
logger.warning(f"Failed login attempt: user_id={user.id}")
# After:
logger.warning(f"login_failed: target_user_id={user.id}, domain=user_management")
```

- [ ] **Step 2: Normalize `User authenticated` INFO (line ~127)**

```python
# Before:
logger.info(f"User authenticated: user_id={user.id}, auth_source=local")
# After:
logger.info(f"user_authenticated: target_user_id={user.id}, auth_source=local, domain=user_management")
```

- [ ] **Step 3: Add domain to already-conforming `user_created` (line ~222)**

```python
# Before:
logger.info(f"user_created: target_user_id={db_user.id}, auth_source={config.IDP_PROVIDER}")
# After:
logger.info(f"user_created: target_user_id={db_user.id}, auth_source={config.IDP_PROVIDER}, domain=user_management")
```

- [ ] **Step 4: Normalize `IDP user migrated` INFO (line ~396)**

```python
# Before:
logger.info(f"IDP user migrated: user_id={db_user.id}")
# After:
logger.info(f"user_migrated: target_user_id={db_user.id}, auth_source={config.IDP_PROVIDER}, domain=user_management")
```

- [ ] **Step 5: Normalize `User creation race condition handled` INFO (line ~461)**

```python
# Before:
logger.info(f"User creation race condition handled: user_id={user_id}")
# After:
logger.info(f"user_creation_race_handled: target_user_id={user_id}, domain=user_management")
```

- [ ] **Step 6: Normalize `Dev header user created` INFO (line ~565)**

```python
# Before:
logger.info(f"Dev header user created: user_id={db_user.id}")
# After:
logger.info(f"user_created: target_user_id={db_user.id}, auth_source=dev_header, domain=user_management")
```

- [ ] **Step 7: Normalize `User logged in` INFO (line ~640)**

```python
# Before:
logger.info(f"User logged in: user_id={user_id}")
# After:
logger.info(f"user_logged_in: target_user_id={user_id}, domain=user_management")
```

- [ ] **Step 8: Run authentication_service tests to confirm GREEN**

```bash
poetry run pytest tests/codemie/service/user/test_authentication_service.py -v 2>&1 | tail -20
```
Expected: All tests PASS

- [ ] **Step 9: Commit**

```bash
git add src/codemie/service/user/authentication_service.py tests/codemie/service/user/test_authentication_service.py
git commit -m "EPMCDME-13273: Normalize authentication_service logs with domain marker"
```

---

### Task 7: password_management_service — normalize log calls

**Files:**
- Modify: `src/codemie/service/user/password_management_service.py`

No existing test assertions on these log messages — update source only.

- [ ] **Step 1: Add domain to conforming `password_changed` calls**

```python
# Before (self-change path, line ~85):
logger.info(f"password_changed: target_user_id={user_id}")
# After:
logger.info(f"password_changed: target_user_id={user_id}, domain=user_management")

# Before (admin-change path, line ~268):
logger.info(f"password_changed: actor_user_id={actor_user_id}, target_user_id={user_id}")
# After:
logger.info(f"password_changed: actor_user_id={actor_user_id}, target_user_id={user_id}, domain=user_management")
```

- [ ] **Step 2: Normalize `Password reset completed` INFO (line ~158)**

```python
# Before:
logger.info(f"Password reset completed: user_id={token_record.user_id}")
# After:
logger.info(f"password_reset_completed: target_user_id={token_record.user_id}, domain=user_management")
```

- [ ] **Step 4: Run password management tests**

```bash
poetry run pytest tests/codemie/service/user/test_password_management_service.py -v 2>&1 | tail -15
```
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/codemie/service/user/password_management_service.py
git commit -m "EPMCDME-13273: Normalize password_management_service logs with domain marker"
```

---

### Task 8: registration_service — normalize log calls

**Files:**
- Modify: `src/codemie/service/user/registration_service.py`

No existing test assertions on these log messages — update source only.

- [ ] **Step 1: Normalize `User registered` INFO (line ~94)**

```python
# Before:
logger.info(f"User registered: user_id={user.id}, auth_source=local")
# After:
logger.info(f"user_registered: target_user_id={user.id}, auth_source=local, domain=user_management")
```

- [ ] **Step 2: Normalize `Email verified` INFO (line ~126)**

```python
# Before:
logger.info(f"Email verified: user_id={user.id}")
# After:
logger.info(f"email_verified: target_user_id={user.id}, domain=user_management")
```

- [ ] **Step 3: Run registration tests**

```bash
poetry run pytest tests/codemie/service/user/test_registration_service.py -v 2>&1 | tail -15
```
Expected: All tests PASS

- [ ] **Step 4: Commit**

```bash
git add src/codemie/service/user/registration_service.py
git commit -m "EPMCDME-13273: Normalize registration_service logs with domain marker"
```

---

### Task 9: user_profile_service — normalize log calls

**Files:**
- Modify: `src/codemie/service/user/user_profile_service.py`

No existing test assertions on these log messages — update source only.

- [ ] **Step 1: Normalize `Profile updated` INFO (line ~203)**

```python
# Before:
logger.info(f"Profile updated: user_id={user_id}")
# After:
logger.info(f"profile_updated: target_user_id={user_id}, domain=user_management")
```

- [ ] **Step 2: Normalize `Failed to send verification email` WARNING (line ~127)**

`_send_verification_email_safe` does not have `user_id` in scope (takes `email`, `token` only). Normalize to snake_case with domain but without `target_user_id`:
```python
# Before:
logger.warning(f"Failed to send verification email for profile update: {e}")
# After:
logger.warning(f"verification_email_failed: domain=user_management")
```

- [ ] **Step 3: Run profile tests**

```bash
poetry run pytest tests/codemie/service/user/test_user_profile_service.py -v 2>&1 | tail -15
```
Expected: All tests PASS

- [ ] **Step 4: Commit**

```bash
git add src/codemie/service/user/user_profile_service.py
git commit -m "EPMCDME-13273: Normalize user_profile_service logs with domain marker"
```

---

### Task 10: application_service — normalize log call

**Files:**
- Modify: `src/codemie/service/user/application_service.py`

No existing test assertions on this log message — update source only.

- [ ] **Step 1: Normalize `Auto-created application` INFO (line ~86)**

```python
# Before:
logger.info(f"Auto-created application for project: {project_name}")
# After:
logger.info(f"application_auto_created: project={project_name}, domain=user_management")
```

- [ ] **Step 2: Run application service tests**

```bash
poetry run pytest tests/codemie/service/user/ -v 2>&1 | tail -20
```
Expected: All tests PASS

- [ ] **Step 3: Commit**

```bash
git add src/codemie/service/user/application_service.py
git commit -m "EPMCDME-13273: Normalize application_service logs with domain marker"
```

---

### Task 11: authentication.py (security layer) — replace access-denied prose

**Files:**
- Modify: `src/codemie/rest_api/security/authentication.py`

All 10 access-denied warnings currently use prose and lack `actor_user_id`. The requesting user is available on `request.state.user` in every decorator that fires these warnings (the `authenticate` dependency has already run by this point).

No existing test assertions on these warnings — update source only.

- [ ] **Step 1: Update `admin_access_only` warning (line ~163)**

```python
# Before:
logger.warning("Access denied: admin or maintainer privileges required")
# After:
logger.warning(f"access_denied_admin: actor_user_id={request.state.user.id}, domain=user_management")
```

- [ ] **Step 2: Update `admin_or_maintainer_access_only` warning (line ~176)**

```python
# Before:
logger.warning("Access denied: admin or maintainer privileges required")
# After:
logger.warning(f"access_denied_admin: actor_user_id={request.state.user.id}, domain=user_management")
```

- [ ] **Step 3: Update `maintainer_access_only` warning (line ~189)**

```python
# Before:
logger.warning("Access denied: maintainer privileges required")
# After:
logger.warning(f"access_denied_maintainer: actor_user_id={request.state.user.id}, domain=user_management")
```

- [ ] **Step 4: Update `project_admin_or_admin_user_detail_access` warnings (lines ~235, ~259, ~268)**

```python
# Before (line ~235):
logger.warning("Access denied: missing target user_id in path for user detail access")
# After:
logger.warning(f"access_denied_missing_target_user_id: actor_user_id={request.state.user.id}, domain=user_management")

# Before (line ~259):
logger.warning("Access denied: project admin cannot view user outside their projects")
# After:
logger.warning(f"access_denied_project_scope: actor_user_id={request.state.user.id}, domain=user_management")

# Before (line ~268):
logger.warning("Access denied: admin or project admin privileges required for user detail")
# After:
logger.warning(f"access_denied_user_detail: actor_user_id={request.state.user.id}, domain=user_management")
```

- [ ] **Step 5: Update resource-based access-denied warnings (lines ~282, ~294, ~309)**

```python
# Before (line ~282):
logger.warning(f"Access denied: user lacks access to application '{app_name}'")
# After:
logger.warning(f"access_denied_application: actor_user_id={request.state.user.id}, resource={app_name}, domain=user_management")

# Before (line ~294) — note: function signature is project_access_check(user: User, project_name: str), user is direct param not request.state.user:
logger.warning(f"Access denied: user lacks access to project '{project_name}'")
# After:
logger.warning(f"access_denied_project: actor_user_id={user.id}, resource={project_name}, domain=user_management")

# Before (line ~309):
logger.warning(f"Access denied: user lacks access to knowledge base '{name}'")
# After:
logger.warning(f"access_denied_kb: actor_user_id={request.state.user.id}, resource={name}, domain=user_management")
```

- [ ] **Step 6: Run the full test suite to confirm no regressions**

```bash
poetry run pytest tests/ -v 2>&1 | tail -30
```
Expected: All tests PASS

- [ ] **Step 7: Run linter**

```bash
make ruff
```
Expected: No violations

- [ ] **Step 8: Commit**

```bash
git add src/codemie/rest_api/security/authentication.py
git commit -m "EPMCDME-13273: Replace access-denied prose warnings with structured event keys in authentication.py"
```

---

## Test-first coverage matrix

| File changed | Has existing log assertions? | Test-first (RED first)? |
|---|---|---|
| `user_access_service.py` | Yes — 4 tests | Yes — Task 1 (RED) before Task 2 (GREEN) |
| `user_management_service.py` | Yes — 4 assertions | Yes — Task 3 (RED) before Task 4 (GREEN) |
| `authentication_service.py` | Yes — 1 assertion | Yes — Task 5 (RED) before Task 6 (GREEN) |
| `password_management_service.py` | No | Direct implementation (Task 7) |
| `registration_service.py` | No | Direct implementation (Task 8) |
| `user_profile_service.py` | No | Direct implementation (Task 9) |
| `application_service.py` | No | Direct implementation (Task 10) |
| `authentication.py` | No | Direct implementation (Task 11) |
