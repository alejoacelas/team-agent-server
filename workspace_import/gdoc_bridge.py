#!/usr/bin/env python3
"""Run using the installed gdoc tool's Python; stdin is non-secret request JSON.

Use gdoc's account-scoped authentication and API clients for every Drive operation.
This never emits tokens or file content on stdout. Downloads go to private staging.
"""
import hashlib
import fcntl
import json
import os
from pathlib import Path
import sys

# gdoc normally requests write scopes. This read-only bridge loads only the
# scopes actually stored in the per-user token; no wider refresh is requested.
import gdoc.auth
from gdoc.util import token_path_for
from gdoc.api import get_drive_service
from gdoc.api.docs import get_docs_service
from gdoc.util import account_context
from googleapiclient.http import MediaIoBaseDownload
from googleapiclient.discovery import build
from functools import lru_cache

@lru_cache(maxsize=8)
def forms_service(account):
    return build("forms", "v1", credentials=gdoc.auth.get_credentials(account))

# gdoc's token writer uses a fixed .tmp name. Serialize only credential loading/
# refresh across workers; API requests themselves remain concurrent.
_original_get_credentials = gdoc.auth.get_credentials


def _locked_credentials(account):
    token = token_path_for(account)
    with token.with_name(token.name + ".workspace-lock").open("a") as lock:
        os.chmod(lock.name, 0o600)
        fcntl.flock(lock, fcntl.LOCK_EX)
        return _original_get_credentials(account)


gdoc.auth.get_credentials = _locked_credentials

FIELDS = "id,name,mimeType,modifiedTime,size,md5Checksum,parents,driveId,trashed,webViewLink,shortcutDetails"
EXPORTS = {
    "application/vnd.google-apps.spreadsheet": ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", ".xlsx"),
    "application/vnd.google-apps.presentation": ("application/vnd.openxmlformats-officedocument.presentationml.presentation", ".pptx"),
    "application/vnd.google-apps.drawing": ("application/pdf", ".pdf"),
}


def main(p=None):
    os.umask(0o077)
    if p is None:
        p = json.load(sys.stdin)
    with account_context(p["account"]):
        stored = json.loads(token_path_for(p["account"]).read_text())
        gdoc.auth.SCOPES = stored.get("scopes", [])
        service = get_drive_service()
        action = p["action"]
        if action == "identity":
            r = service.about().get(fields="user(emailAddress)").execute(num_retries=6)
            result = {"email": r["user"]["emailAddress"]}
        elif action == "discover":
            files, token, seen = [], None, set()
            while True:
                page = service.files().list(q="mimeType='application/vnd.google-apps.folder' and trashed=false", pageSize=1000, pageToken=token, fields="files(id,name,driveId),nextPageToken,incompleteSearch", supportsAllDrives=True, includeItemsFromAllDrives=True).execute(num_retries=6)
                if page.get("incompleteSearch"):
                    raise ValueError("Incomplete folder discovery")
                files.extend(page.get("files", []))
                token = page.get("nextPageToken")
                if not token:
                    break
                if token in seen:
                    raise ValueError("Repeated folder cursor")
                seen.add(token)
            result = {"my_drive_root": "root", "folders": files}
        elif action == "get":
            result = service.files().get(fileId=p["file_id"], fields=FIELDS, supportsAllDrives=True).execute(num_retries=6)
        elif action == "list":
            fid = p["folder_id"].replace("\\", "\\\\").replace("'", "\\'")
            # Inside a shared drive, search that drive's corpus: the default corpus covers only
            # shared-drive files the user has accessed, so unopened files could be missed.
            scope = {"corpora": "drive", "driveId": p["drive_id"]} if p.get("drive_id") else {}
            result = service.files().list(q=f"'{fid}' in parents and trashed=false", pageSize=1000,
                pageToken=p.get("page_token"), fields=f"files({FIELDS}),nextPageToken,incompleteSearch",
                supportsAllDrives=True, includeItemsFromAllDrives=True, **scope).execute(num_retries=6)
        elif action == "download":
            out = Path(p["output_dir"])
            out.mkdir(parents=True, exist_ok=True, mode=0o700)
            stem = hashlib.sha256(p["file_id"].encode()).hexdigest()
            mime = p["mime_type"]
            if mime == "application/vnd.google-apps.form":
                form = forms_service(p["account"]).forms().get(formId=p["file_id"]).execute(num_retries=6)
                path = out / (stem + ".json")
                path.write_text(json.dumps({"form": form, "responses_exported": False,
                    "note": "Form questions/settings only. Responses require a separate OAuth scope or the linked response sheet."}, ensure_ascii=False))
                if path.stat().st_size > p["max_bytes"]:
                    raise ValueError("Form exceeds configured size")
                result = {"path": str(path), "suffix": ".json"}
            elif mime == "application/vnd.google-apps.document":
                # Native API snapshot preserves tab topology, including text omitted by some exports.
                doc = get_docs_service().documents().get(documentId=p["file_id"], includeTabsContent=True).execute(num_retries=6)
                path = out / (stem + ".json")
                path.write_text(json.dumps(doc, ensure_ascii=False))
                if path.stat().st_size > p["max_bytes"]:
                    raise ValueError("Document exceeds configured size")
                result = {"path": str(path), "suffix": ".json"}
            else:
                if mime.startswith("application/vnd.google-apps."):
                    if mime not in EXPORTS:
                        raise ValueError("Unsupported native Drive type: explicitly exclude or add exporter")
                    target, suffix = EXPORTS[mime]
                    request = service.files().export_media(fileId=p["file_id"], mimeType=target)
                else:
                    suffix = ".bin"
                    name = p.get("filename", "")
                    ext = Path(name).suffix.lower()
                    if ext and ext[1:].isalnum() and len(ext) < 12:
                        suffix = ext
                    request = service.files().get_media(fileId=p["file_id"], supportsAllDrives=True)
                path = out / (stem + suffix)
                with path.open("wb") as f:
                    downloader = MediaIoBaseDownload(f, request, chunksize=1024 * 1024)
                    done = False
                    while not done:
                        _, done = downloader.next_chunk(num_retries=6)
                        if f.tell() > p["max_bytes"]:
                            raise ValueError("File exceeds configured size")
                result = {"path": str(path), "suffix": suffix}
        else:
            raise ValueError("Unknown action")
    print(json.dumps(result), flush=True)


if __name__ == "__main__":
    try:
        if "--serve" in sys.argv:
            for line in sys.stdin:
                try:
                    main(json.loads(line))
                except Exception as exc:
                    print(json.dumps({"_bridge_error": type(exc).__name__, "_http_status": getattr(getattr(exc, "resp", None), "status", None)}), flush=True)
        else:
            main()
    except Exception as exc:
        # Avoid provider response bodies, tokens, or private document content in logs.
        print(type(exc).__name__ + ": gdoc operation failed", file=sys.stderr)
        sys.exit(1)
