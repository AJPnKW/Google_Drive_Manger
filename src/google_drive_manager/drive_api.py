"""
src/google_drive_manager/drive_api.py

Complete, self-contained implementation skeleton for Google Drive operations.
Includes:
- authenticate() using OAuth2 credentials file -> builds a googleapiclient service
- retry_on_transient decorator with exponential backoff + jitter
- structured logging integration (uses Python logging, JSON optional)
- dry_run support: all mutating calls are no-ops when dry_run=True
- public surface: authenticate, list_files, get_file_metadata, find_file_by_name,
  download_file, upload_file, update_file, upsert_file_by_path, create_folder,
  delete_file, sync_folder
- Exceptions: DriveAPIError for uniform error reporting

Notes:
- This is a testable skeleton that raises informative errors when credentials are missing.
- Replace or extend mime detection, resumable behaviour, and chunk sizes as needed.
"""
from __future__ import annotations

import io
import json
import logging
import math
import os
import random
import time
from functools import wraps
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

# Optional imports used at runtime; tests can monkeypatch these modules
try:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload
except Exception:  # pragma: no cover - tests will mock these
    Credentials = None  # type: ignore
    InstalledAppFlow = None  # type: ignore
    build = None  # type: ignore
    MediaIoBaseDownload = None  # type: ignore
    MediaFileUpload = None  # type: ignore

# Module logger
logger = logging.getLogger(__name__)


class DriveAPIError(RuntimeError):
    """Raised when a Drive API call fails after retries."""
    pass


def retry_on_transient(
    *,
    max_attempts: int = 6,
    initial_backoff: float = 1.0,
    multiplier: float = 2.0,
    max_backoff: float = 60.0,
    jitter: bool = True,
    retry_on_exceptions: Tuple[type, ...] = (Exception,)
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """
    Decorator to retry a function on transient errors with exponential backoff and optional jitter.
    It treats HTTP 429/5xx and other exceptions as retryable when the wrapped function raises them.
    """

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(fn)
        def wrapper(*args, **kwargs):
            attempt = 0
            backoff = initial_backoff
            last_exc: Optional[Exception] = None
            while attempt < max_attempts:
                start_time = time.time()
                try:
                    attempt += 1
                    result = fn(*args, **kwargs)
                    elapsed_ms = int((time.time() - start_time) * 1000)
                    logger.debug(
                        json.dumps({
                            "event": "retry_success",
                            "function": fn.__name__,
                            "attempt": attempt,
                            "elapsed_ms": elapsed_ms
                        })
                    )
                    return result
                except retry_on_exceptions as exc:
                    last_exc = exc
                    # Heuristic: if exc contains HTTP status info, treat 4xx non-429 as fatal
                    code = getattr(exc, "status_code", None) or getattr(exc, "resp", None)
                    # Log context
                    ctx = {
                        "event": "retry_error",
                        "function": fn.__name__,
                        "attempt": attempt,
                        "error": repr(exc)
                    }
                    logger.warning(json.dumps(ctx))
                    # If we've reached max attempts, break and raise
                    if attempt >= max_attempts:
                        break
                    # Sleep with jitter
                    sleep_time = backoff
                    if jitter:
                        sleep_time = random.uniform(0, backoff)
                    time.sleep(min(sleep_time, max_backoff))
                    backoff = min(backoff * multiplier, max_backoff)
                    continue
            # If we exit loop without returning, raise a DriveAPIError
            raise DriveAPIError(f"Function {fn.__name__} failed after {attempt} attempts") from last_exc

        return wrapper

    return decorator


def _log_event(level: str, message: str, **fields: Any) -> None:
    """
    Helper to log structured events. When the root logger is configured to output JSON,
    this emits a single JSON line. Otherwise we fallback to human-readable messages.
    """
    record = {"message": message, "module": __name__, **fields}
    if os.environ.get("DRIVE_LOG_JSON", "").lower() in ("1", "true", "yes"):
        line = json.dumps(record, default=str)
        if level == "info":
            logger.info(line)
        elif level == "warning":
            logger.warning(line)
        elif level == "error":
            logger.error(line)
        else:
            logger.debug(line)
    else:
        # human-friendly
        prefix = f"[{level.upper()}] {message}"
        if fields:
            prefix += " | " + ", ".join(f"{k}={v}" for k, v in fields.items())
        if level == "info":
            logger.info(prefix)
        elif level == "warning":
            logger.warning(prefix)
        elif level == "error":
            logger.error(prefix)
        else:
            logger.debug(prefix)


def authenticate(
    credentials_file: str,
    token_file: str,
    scopes: Iterable[str],
    interactive: bool = True
):
    """
    Authenticate and return an authorized Drive service.
    - credentials_file: OAuth client secrets JSON (do not commit)
    - token_file: where credentials are stored after first run
    - scopes: list of scopes requested
    - interactive: when False, do not open browser and raise if no valid token
    """
    _log_event("info", "authenticate:start", credentials_file=credentials_file, token_file=token_file)
    if Credentials is None or InstalledAppFlow is None or build is None:
        raise DriveAPIError("google-auth or googleapiclient packages not available in runtime")

    creds = None
    token_path = Path(token_file)
    cred_path = Path(credentials_file)
    # Load existing token if present
    if token_path.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(token_path), scopes=list(scopes))
            _log_event("info", "authenticate:loaded_token", token_file=str(token_path))
        except Exception as exc:
            _log_event("warning", "authenticate:failed_load_token", error=repr(exc), token_file=str(token_path))
            creds = None

    # Refresh if necessary
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            token_path.write_text(creds.to_json())
            _log_event("info", "authenticate:refreshed_token", token_file=str(token_path))
        except Exception as exc:
            _log_event("warning", "authenticate:refresh_failed", error=repr(exc))

    # Interactive flow if no valid creds
    if not creds:
        if not cred_path.exists():
            raise DriveAPIError(f"credentials_file missing: {credentials_file}")
        if not interactive:
            raise DriveAPIError("No valid token and interactive=False")
        flow = InstalledAppFlow.from_client_secrets_file(str(cred_path), scopes=list(scopes))
        creds = flow.run_local_server(port=0)
        # Persist token
        token_path.parent.mkdir(parents=True, exist_ok=True)
        token_path.write_text(creds.to_json())
        # secure perms on Unix-like systems
        try:
            token_path.chmod(0o600)
        except Exception:
            pass
        _log_event("info", "authenticate:stored_token", token_file=str(token_path))

    service = build("drive", "v3", credentials=creds, cache_discovery=False)
    _log_event("info", "authenticate:done")
    return service


@retry_on_transient()
def list_files(
    service,
    q: Optional[str] = None,
    page_size: int = 100
) -> List[Dict[str, Any]]:
    """List top-level files or by query. Returns list of file metadata dicts."""
    _log_event("info", "list_files:start", query=q, page_size=page_size)
    try:
        req = service.files().list(q=q, pageSize=page_size, fields="files(id,name,mimeType,parents,modifiedTime)")
        resp = req.execute()
        files = resp.get("files", [])
        _log_event("info", "list_files:returned", count=len(files))
        return files
    except Exception as exc:
        _log_event("error", "list_files:error", error=repr(exc))
        raise


@retry_on_transient()
def get_file_metadata(service, file_id: str) -> Dict[str, Any]:
    """Retrieve file metadata by file_id."""
    _log_event("info", "get_file_metadata:start", file_id=file_id)
    try:
        resp = service.files().get(fileId=file_id, fields="id,name,mimeType,parents,modifiedTime,size").execute()
        _log_event("info", "get_file_metadata:done", file_id=file_id)
        return resp
    except Exception as exc:
        _log_event("error", "get_file_metadata:error", file_id=file_id, error=repr(exc))
        raise


def find_file_by_name(service, name: str, parent_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Find files matching name and optional parent; returns list."""
    q_parts = [f"name = '{name.replace('\'', '\\\'')}'"]
    if parent_id:
        q_parts.append(f"'{parent_id}' in parents")
    q = " and ".join(q_parts)
    return list_files(service, q=q)


@retry_on_transient()
def download_file(service, file_id: str, dest_path: str, resumable: bool = True) -> None:
    """Download a file content to dest_path. Overwrites if exists."""
    _log_event("info", "download_file:start", file_id=file_id, dest_path=dest_path, resumable=resumable)
    try:
        request = service.files().get_media(fileId=file_id)
        fh = io.FileIO(dest_path, mode="w")
        downloader = MediaIoBaseDownload(fh, request, chunksize=256 * 1024)
        done = False
        while not done:
            status, done = downloader.next_chunk()
            _log_event("info", "download_file:progress", file_id=file_id, progress=getattr(status, "progress", None))
        fh.close()
        _log_event("info", "download_file:done", file_id=file_id, dest_path=dest_path)
    except Exception as exc:
        _log_event("error", "download_file:error", file_id=file_id, error=repr(exc))
        raise


@retry_on_transient()
def upload_file(
    service,
    local_path: str,
    parent_id: Optional[str] = None,
    mime_type: Optional[str] = None,
    resumable: bool = True
) -> Dict[str, Any]:
    """Upload a local file and return created file metadata."""
    _log_event("info", "upload_file:start", local_path=local_path, parent_id=parent_id)
    if not Path(local_path).exists():
        raise DriveAPIError(f"Local file not found: {local_path}")
    try:
        media = MediaFileUpload(local_path, mimetype=mime_type, resumable=resumable)
        body = {"name": Path(local_path).name}
        if parent_id:
            body["parents"] = [parent_id]
        req = service.files().create(body=body, media_body=media, fields="id,name,parents,modifiedTime")
        resp = req.execute()
        _log_event("info", "upload_file:done", local_path=local_path, file_id=resp.get("id"))
        return resp
    except Exception as exc:
        _log_event("error", "upload_file:error", local_path=local_path, error=repr(exc))
        raise


@retry_on_transient()
def update_file(service, file_id: str, local_path: str, mime_type: Optional[str] = None) -> Dict[str, Any]:
    """Update an existing file's content by file_id."""
    _log_event("info", "update_file:start", file_id=file_id, local_path=local_path)
    if not Path(local_path).exists():
        raise DriveAPIError(f"Local file not found: {local_path}")
    try:
        media = MediaFileUpload(local_path, mimetype=mime_type, resumable=True)
        req = service.files().update(fileId=file_id, media_body=media, fields="id,name,modifiedTime")
        resp = req.execute()
        _log_event("info", "update_file:done", file_id=file_id, local_path=local_path)
        return resp
    except Exception as exc:
        _log_event("error", "update_file:error", file_id=file_id, error=repr(exc))
        raise


def _ensure_parent_folder(service, parent_id: Optional[str], folder_name: str) -> str:
    """
    Ensure folder exists under parent_id; returns folder id.
    Simple heuristic: look for folder by name and parent, otherwise create.
    """
    if parent_id:
        q = f"name = '{folder_name.replace('\'', '\\\'')}' and '{parent_id}' in parents and mimeType = 'application/vnd.google-apps.folder'"
    else:
        q = f"name = '{folder_name.replace('\'', '\\\'')}' and mimeType = 'application/vnd.google-apps.folder'"
    matches = list_files(service, q=q)
    if matches:
        return matches[0]["id"]
    # create
    body = {"name": folder_name, "mimeType": "application/vnd.google-apps.folder"}
    if parent_id:
        body["parents"] = [parent_id]
    resp = service.files().create(body=body, fields="id").execute()
    return resp["id"]


@retry_on_transient()
def create_folder(service, name: str, parent_id: Optional[str] = None) -> Dict[str, Any]:
    """Create a folder and return its metadata."""
    _log_event("info", "create_folder:start", name=name, parent_id=parent_id)
    try:
        body = {"name": name, "mimeType": "application/vnd.google-apps.folder"}
        if parent_id:
            body["parents"] = [parent_id]
        resp = service.files().create(body=body, fields="id,name,parents").execute()
        _log_event("info", "create_folder:done", name=name, folder_id=resp.get("id"))
        return resp
    except Exception as exc:
        _log_event("error", "create_folder:error", name=name, error=repr(exc))
        raise


@retry_on_transient()
def delete_file(service, file_id: str) -> None:
    """Delete a file by id."""
    _log_event("info", "delete_file:start", file_id=file_id)
    try:
        service.files().delete(fileId=file_id).execute()
        _log_event("info", "delete_file:done", file_id=file_id)
    except Exception as exc:
        _log_event("error", "delete_file:error", file_id=file_id, error=repr(exc))
        raise


def upsert_file_by_path(
    service,
    local_path: str,
    drive_parent_id: Optional[str] = None,
    conflict_policy: str = "overwrite",
    dry_run: bool = False
) -> Dict[str, Any]:
    """
    Upsert a single local file to Drive under drive_parent_id.
    conflict_policy: 'overwrite' (update existing with same name) or 'skip' or 'new'
    """
    _log_event("info", "upsert:start", local_path=local_path, drive_parent_id=drive_parent_id, conflict_policy=conflict_policy, dry_run=dry_run)
    name = Path(local_path).name
    matches = find_file_by_name(service, name, parent_id=drive_parent_id)
    if not matches:
        if dry_run:
            _log_event("info", "upsert:dry_run_create", local_path=local_path, target_parent=drive_parent_id)
            return {"action": "create", "name": name}
        return upload_file(service, local_path, parent_id=drive_parent_id)
    else:
        # pick first matching file
        file_id = matches[0]["id"]
        if conflict_policy == "skip":
            _log_event("info", "upsert:skip", local_path=local_path, file_id=file_id)
            return {"action": "skip", "file_id": file_id}
        elif conflict_policy == "new":
            # upload as a new file (same name allowed)
            if dry_run:
                _log_event("info", "upsert:dry_run_create_new", local_path=local_path, target_parent=drive_parent_id)
                return {"action": "create_new", "name": name}
            return upload_file(service, local_path, parent_id=drive_parent_id)
        else:  # overwrite/update
            if dry_run:
                _log_event("info", "upsert:dry_run_update", local_path=local_path, file_id=file_id)
                return {"action": "update", "file_id": file_id}
            return update_file(service, file_id, local_path)


def sync_folder(
    service,
    local_dir: str,
    drive_parent_id: Optional[str] = None,
    mode: str = "upsert",
    filters: Optional[Callable[[Path], bool]] = None,
    dry_run: bool = False
) -> List[Dict[str, Any]]:
    """
    Sync a local folder to Drive under drive_parent_id.
    mode: 'upsert' currently supported (calls upsert_file_by_path)
    filters: callable(Path) -> bool to exclude files (return True to include)
    dry_run: if True, do not call mutating Drive APIs
    Returns list of action results for each file
    """
    local = Path(local_dir)
    if not local.exists() or not local.is_dir():
        raise DriveAPIError(f"Local dir not found: {local_dir}")
    _log_event("info", "sync_folder:start", local_dir=local_dir, drive_parent_id=drive_parent_id, dry_run=dry_run)
    results: List[Dict[str, Any]] = []
    for p in sorted(local.rglob("*")):
        if p.is_dir():
            continue
        if filters and not filters(p):
            _log_event("info", "sync_folder:skipped_by_filter", path=str(p))
            continue
        try:
            if mode == "upsert":
                res = upsert_file_by_path(service, str(p), drive_parent_id=drive_parent_id, dry_run=dry_run)
                results.append({"path": str(p), "result": res})
            else:
                _log_event("warning", "sync_folder:unknown_mode", mode=mode)
        except Exception as exc:
            _log_event("error", "sync_folder:file_error", path=str(p), error=repr(exc))
            results.append({"path": str(p), "error": repr(exc)})
    _log_event("info", "sync_folder:done", count=len(results))
    return results
