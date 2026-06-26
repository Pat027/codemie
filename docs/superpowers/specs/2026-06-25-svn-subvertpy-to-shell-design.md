# SVN: Replace subvertpy with svn CLI shell commands

**Ticket:** EPMCDME-13166  
**Branch:** EPMCDME-13166_svn-subvertpy-to-shell  
**Date:** 2026-06-25

## Goal

Replace the `subvertpy` C-extension library with subprocess calls to the `svn` CLI. The public interface of `SVNBatchLoader` is unchanged. No callers outside `svn_loader.py` are modified.

## Motivation

- `subvertpy` ships platform-specific C wheels (`manylinux_2_34_x86_64`) that complicate container builds.
- Its license (GPLv2+) requires an explicit allowlist entry.
- The three operations used (`get_latest_revnum`, `get_dir`, `get_file`) map directly to standard `svn` CLI commands available in all SVN server environments.

## Scope

| File | Change |
|---|---|
| `src/codemie/datasource/loader/svn_client.py` | **New file** — `svn_is_available`, `_build_auth_flags`, `SvnClient` |
| `src/codemie/datasource/loader/svn_loader.py` | Remove `subvertpy` imports; replace `_build_remote_access` + `conn.*` calls with `SvnClient`; call `svn_is_available()` guard |
| `tests/codemie/datasource/loader/test_svn_client.py` | **New file** — unit tests for `svn_client.py` |
| `tests/codemie/datasource/loader/test_svn_loader.py` | Update mocks from `_build_remote_access` to `SvnClient`; add `svn_is_available` guard tests |
| `pyproject.toml` | Remove `subvertpy` dependency and its license-allowlist comment |

No changes to service, API, trigger, DB, or migration layers.

## Architecture

```
src/codemie/datasource/loader/
├── svn_client.py    ← NEW
└── svn_loader.py    ← updated imports + call sites only
```

`_svn_ssh_context` and `_build_branch_url` remain in `svn_loader.py` — they are loader-level concerns.

## svn_client.py

### `svn_is_available() -> bool`

`shutil.which("svn") is not None`.

Callers (`test_connection`, `lazy_load`) check this first and raise `RuntimeError("svn CLI is not installed or not on PATH")` if it returns `False`.

### `_build_auth_flags(creds: SVNCredentials) -> list[str]`

Always included:
```
--non-interactive --trust-server-cert --trust-server-cert-failures=unknown-ca
```

BASIC auth adds:
```
--username <username> --password <password> --no-auth-cache
```

SSH_KEY auth: no extra flags — the `SVN_SSH` env var set by `_svn_ssh_context` handles authentication at the SSH layer.

### `SvnClient`

```python
class SvnClient:
    def __init__(self, url: str, creds: SVNCredentials): ...
    def get_latest_revnum(self) -> int: ...
    def get_dir(self, path: str, revision: int) -> dict[str, dict]: ...
    def get_file(self, path: str, revision: int) -> bytes: ...
```

| Method | Command | Parse target | Returns |
|---|---|---|---|
| `get_latest_revnum()` | `svn info --xml <url> <flags>` | `<commit revision="N">` attribute | `int` |
| `get_dir(path, rev)` | `svn list --xml <target>@<rev> <flags>` | `<entry>` nodes | `dict[name, {kind: "file"\|"dir", size: int}]` |
| `get_file(path, rev)` | `svn cat <target>@<rev> <flags>` | stdout | `bytes` |

`<target>` for `get_dir` and `get_file`: `f"{url}/{path}"` when `path` is non-empty, otherwise `url` directly. This handles the root traversal call `get_dir("", revision)` correctly — produces `<url>@<rev>` not `<url>/@<rev>`.

All three use `subprocess.run(..., check=True, capture_output=True)`. A non-zero exit raises `subprocess.CalledProcessError`. XML parsing uses `xml.etree.ElementTree` (stdlib).

## svn_loader.py changes

- Remove imports: `subvertpy.ra`, `subvertpy.NODE_DIR/NODE_FILE`, `subvertpy.ra.DIRENT_KIND/DIRENT_SIZE`
- Add imports: `from codemie.datasource.loader.svn_client import SvnClient, svn_is_available`
- Remove: `_ssl_server_trust_prompt`, `_build_remote_access`
- `test_connection`: call `svn_is_available()` guard, then `SvnClient(branch_url, creds).get_latest_revnum()`
- `fetch_remote_stats`: same pattern
- `lazy_load`: call `svn_is_available()` guard, then use `SvnClient` inside the SSH context
- `_walk_remote`: receives `SvnClient` instead of `svn_ra.RemoteAccess`; `get_dir` returns a plain dict — iterate the same way; use `"file"` / `"dir"` string comparisons instead of `NODE_FILE` / `NODE_DIR` constants
- `_fetch_and_process`: receives `SvnClient`; replace `conn.get_file(path, buf, rev)` with `content = client.get_file(path, rev)`; remove `io.BytesIO` buffer

## Error handling

| Error | Source | Handled by |
|---|---|---|
| `RuntimeError` — svn not on PATH | `svn_is_available()` check | Propagates to caller (HTTP 422 via existing handler) |
| `subprocess.CalledProcessError` — non-zero svn exit | `check=True` | `_fetch_and_process` catches `Exception`; connection methods propagate |
| `xml.etree.ElementTree.ParseError` — malformed output | XML parse in `SvnClient` | Same as above |

## Testing

### test_svn_client.py (new)

All tests mock `subprocess.run`:

- `svn_is_available` — True when `shutil.which` returns a path, False otherwise
- `_build_auth_flags` — BASIC includes username/password/no-auth-cache flags; SSH_KEY includes only the base flags; empty creds include only base flags
- `SvnClient.get_latest_revnum` — parses revision from well-formed XML; raises on non-zero exit
- `SvnClient.get_dir` — parses file and dir entries with kind and size; handles empty directory
- `SvnClient.get_file` — returns stdout bytes; raises on non-zero exit

### test_svn_loader.py (updated)

- Replace all `patch("...svn_loader._build_remote_access", return_value=mock_conn)` with `patch("...svn_loader.SvnClient", return_value=mock_client)`
- `mock_client` exposes `get_latest_revnum`, `get_dir`, `get_file` matching the old `mock_conn` interface
- Add: `test_connection` raises `RuntimeError` when `svn_is_available` returns `False`
- Add: `lazy_load` raises `RuntimeError` when `svn_is_available` returns `False`

## Dependency removal

`pyproject.toml` line 162: remove `subvertpy = ">=0.11"`.  
`pyproject.toml` line 265: remove the `"subvertpy"` license-allowlist entry and its comment.  
Run `poetry lock --no-update` after removal to update `poetry.lock`.
