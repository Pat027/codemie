# Unify User Management Logs — Design Spec

**Ticket**: EPMCDME-13273  
**Branch**: EPMCDME-13273_unify-user-management-logs  
**Date**: 2026-07-02

---

## Goal

Standardize all backend user-management log messages so they:
1. Follow a consistent `snake_case_event_key: field=value` format
2. Carry `domain=user_management` in every INFO/WARNING message, enabling reliable log extraction via regexp
3. Include `actor_user_id` and `target_user_id` for all user-affecting operations
4. Preserve all existing information — no log removal, only format normalization plus targeted field enrichment

---

## Target Convention

```
INFO  <snake_case_event>: actor_user_id=<id>, target_user_id=<id>[, <extra>=<value>], domain=user_management
WARN  blocked_<action>: actor_user_id=<id>, target_user_id=<id>, action=<action>, timestamp=<ts>, domain=user_management
WARN  access_denied_<context>: actor_user_id=<id>[, resource=<name>], domain=user_management
DEBUG <prose or terse>                          ← no domain marker
ERROR <prose>                                   ← no domain marker; operational errors unchanged
```

**Rules:**
- `domain=user_management` on every INFO and WARNING message in the user-management domain
- `actor_user_id=` for who performed the action; `target_user_id=` for who it happened to
- Role-change events include the changed role values: `is_admin=`, `is_maintainer=`, `project_limit=`
- `access_denied_<context>:` replaces all `"Access denied: ..."` prose in the security layer
- No PII — no emails, passwords, names, or resource content in any log message
- DEBUG and ERROR levels keep existing prose style; they are operational, not audit

---

## Affected Files

### 1. `src/codemie/service/user/authentication_service.py`

| Before | After |
|---|---|
| `"User authenticated: user_id={user.id}, auth_source=local"` | `"user_authenticated: target_user_id={user.id}, auth_source=local, domain=user_management"` |
| `"User logged in: user_id={user_id}"` | `"user_logged_in: target_user_id={user_id}, domain=user_management"` |
| `"IDP user migrated: user_id={db_user.id}"` | `"user_migrated: target_user_id={db_user.id}, auth_source={config.IDP_PROVIDER}, domain=user_management"` |
| `"User creation race condition handled: user_id={user_id}"` | `"user_creation_race_handled: target_user_id={user_id}, domain=user_management"` |
| `"Dev header user created: user_id={db_user.id}"` | `"user_created: target_user_id={db_user.id}, auth_source=dev_header, domain=user_management"` |
| `"Failed login attempt: user_id={user.id}"` (WARNING) | `"login_failed: target_user_id={user.id}, domain=user_management"` |
| `"user_created: target_user_id=..."` (already conforming) | Add `, domain=user_management` |

DEBUG calls (`auth_cache_invalidated`, `Auth token cache hit`, `User authenticated (debug)`, `Ensured project exists`) and ERROR calls are unchanged.

### 2. `src/codemie/service/user/registration_service.py`

| Before | After |
|---|---|
| `"User registered: user_id={user.id}, auth_source=local"` | `"user_registered: target_user_id={user.id}, auth_source=local, domain=user_management"` |
| `"Email verified: user_id={user.id}"` | `"email_verified: target_user_id={user.id}, domain=user_management"` |

ERROR calls unchanged.

### 3. `src/codemie/service/user/user_profile_service.py`

| Before | After |
|---|---|
| `"Profile updated: user_id={user_id}"` | `"profile_updated: target_user_id={user_id}, domain=user_management"` |
| `"Failed to send verification email for profile update: {e}"` (WARNING) | `"verification_email_failed: domain=user_management"` |

Note: `_send_verification_email_safe` receives `email` and `token` only — `user_id` is not in scope. The warning omits `target_user_id` rather than changing the helper's signature, which is out of scope for this task.

### 4. `src/codemie/service/user/password_management_service.py`

| Before | After |
|---|---|
| `"password_changed: target_user_id={user_id}"` | Add `, domain=user_management` |
| `"password_changed: actor_user_id=..., target_user_id=..."` | Add `, domain=user_management` |
| `"Password reset completed: user_id={token_record.user_id}"` | `"password_reset_completed: target_user_id={token_record.user_id}, domain=user_management"` |
| `"Password reset token created: user_id={user.id}"` | `"password_reset_token_created: target_user_id={user.id}, domain=user_management"` |

DEBUG call (`Password reset token created` debug variant) unchanged.

### 5. `src/codemie/service/user/user_management_service.py`

**Conforming calls** — add `domain=user_management`:
- `user_created:` (in `create_local_user_with_flow`)
- `user_updated:` — also enrich with audit fields when present in the update dict
- `user_deactivated:`
- `blocked_last_admin_deactivation:`, `blocked_self_revocation:`, `blocked_last_admin_revocation:`

**Non-conforming calls** — normalize and add domain:
- `"SuperAdmin bootstrapped: user_id={superadmin_id}"` → `"superadmin_bootstrapped: target_user_id={superadmin_id}, domain=user_management"`
- `"SuperAdmin already exists, skipping bootstrap"` → `"superadmin_bootstrap_skipped: domain=user_management"`

**Duplicate `user_created` rationalization:**  
Remove the `user_created` log from `create_local_user` (line ~119) — this function is called both by `bootstrap_superadmin` and `create_local_user_with_flow`. The bootstrap path has `superadmin_bootstrapped:` at a higher level; the flow path has `user_created:` with actor context in `create_local_user_with_flow`. Eliminating the inner log removes the duplicate without losing coverage.

**`user_updated` enrichment:**  
When `is_admin`, `is_maintainer`, or `project_limit` are in the fields dict, append them to the log so role promotions and project-limit changes are audit-traceable:
```python
role_fields = {k: fields[k] for k in ("is_admin", "is_maintainer", "project_limit") if k in fields}
extra = (", " + ", ".join(f"{k}={v}" for k, v in role_fields.items())) if role_fields else ""
logger.info(f"user_updated: actor_user_id={actor_user_id}, target_user_id={user_id}{extra}, domain=user_management")
```

### 6. `src/codemie/service/user/user_access_service.py`

All 6 log calls already conform to the event-key convention. Only add `, domain=user_management`:
- `project_access_granted:`, `project_access_updated:`, `project_access_removed:`
- `kb_access_granted:`, `kb_access_removed:`
- `project_authorization_failed:` (WARNING)

### 7. `src/codemie/service/user/application_service.py`

| Before | After |
|---|---|
| `"Auto-created application for project: {project_name}"` (INFO) | `"application_auto_created: project={project_name}, domain=user_management"` |

DEBUG and ERROR calls unchanged.

### 8. `src/codemie/rest_api/security/authentication.py`

All 10 access-denied WARNING calls get:
- `snake_case` event key replacing prose
- `actor_user_id={request.state.user.id}` (user is on `request.state` in all these decorators)
- `, domain=user_management`

| Before | After |
|---|---|
| `"Access denied: admin or maintainer privileges required"` (×2 functions) | `"access_denied_admin: actor_user_id={request.state.user.id}, domain=user_management"` |
| `"Access denied: maintainer privileges required"` | `"access_denied_maintainer: actor_user_id={request.state.user.id}, domain=user_management"` |
| `"Access denied: missing target user_id in path for user detail access"` | `"access_denied_missing_target_user_id: actor_user_id={request.state.user.id}, domain=user_management"` |
| `"Access denied: project admin cannot view user outside their projects"` | `"access_denied_project_scope: actor_user_id={request.state.user.id}, domain=user_management"` |
| `"Access denied: admin or project admin privileges required for user detail"` | `"access_denied_user_detail: actor_user_id={request.state.user.id}, domain=user_management"` |
| `"Access denied: user lacks access to application '{app_name}'"` | `"access_denied_application: actor_user_id={request.state.user.id}, resource={app_name}, domain=user_management"` |
| `"Access denied: user lacks access to project '{project_name}'"` | `"access_denied_project: actor_user_id={request.state.user.id}, resource={project_name}, domain=user_management"` |
| `"Access denied: user lacks access to knowledge base '{name}'"` | `"access_denied_kb: actor_user_id={request.state.user.id}, resource={name}, domain=user_management"` |

Authentication failure warnings (lines 151, 154) are operational — the request context at that point carries no authenticated user, so `actor_user_id` cannot be added. These two log calls are left unchanged.

---

## Tests

Only update existing assertions — no new test files. Files with assertions on changed messages:

- `tests/codemie/service/user/test_user_management_service_super_admin.py` — `blocked_self_revocation`, `blocked_last_admin_revocation`, `blocked_last_admin_deactivation` messages; update to include `, domain=user_management`
- `tests/codemie/service/user/test_user_access_service.py` — `project_access_granted`, `project_access_updated`, `project_access_removed`, `project_authorization_failed` messages; update to include `, domain=user_management`
- `tests/codemie/service/user/test_authentication_service.py` — the failed-login warning assertion at line 172–173; update to `login_failed: target_user_id=...`

All other test files (`test_registration_service.py`, `test_user_profile_service.py`, `test_password_management_service.py`) do not assert on log messages — no test changes needed in those files.

---

## Out of Scope

- No changes to `src/codemie/configs/logger.py` (formatter/envelope unchanged)
- No changes to router files (logging is delegated to service layer)
- No new test files or coverage for previously untested log paths
- No shared log-builder helper (inline formatting is sufficient)
- DEBUG and ERROR level messages are not reformatted
