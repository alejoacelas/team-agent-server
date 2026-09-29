from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import subprocess
import sys
import select
from collections import deque
from concurrent.futures import ThreadPoolExecutor
import threading
from .text_files import readable
from urllib.parse import quote

from google.auth.transport.requests import AuthorizedSession
from google.oauth2.credentials import Credentials

from .core import HTTP, ImportFailure, pages


def google_http(config):
    token_file = config.get("token_file") or os.environ.get(config.get("token_file_env", "GOOGLE_TOKEN_FILE"))
    if not token_file:
        raise ImportFailure("Missing Google OAuth token file environment variable")
    creds = Credentials.from_authorized_user_file(str(Path(token_file).expanduser()))
    http = HTTP(session=AuthorizedSession(creds))
    who = http.json("GET", "https://www.googleapis.com/oauth2/v2/userinfo")
    if who.get("email", "").lower() != config["expected_email"].lower():
        raise ImportFailure("Google identity mismatch")
    return http


def gmail(config, snap, http=None):
    http = http or google_http(config)
    root = "https://gmail.googleapis.com/gmail/v1/users/me"
    profile = http.json("GET", root + "/profile")
    if profile.get("emailAddress", "").lower() != config["expected_email"].lower():
        raise ImportFailure("Gmail identity mismatch")
    # Full selected-scope reconciliation deliberately avoids fragile history cursors.
    for item in pages(http, root + "/messages", {"maxResults": 500, "q": config["query"], "includeSpamTrash": "false"}, items="messages"):
        mid = item["id"]
        msg = http.json("GET", root + "/messages/" + quote(mid, safe=""), params={"format": "full"})
        key = "message:" + mid
        assets = []

        def parts(part):
            body = part.get("body", {})
            attid = body.get("attachmentId")
            data = body.get("data")
            if attid or data:
                # Includes HTML/plain bodies and inline images, not just named attachments.
                aid = key + ":part:" + str(part.get("partId", "root"))
                path = snap.cached(aid)
                if path is None:
                    if attid:
                        b = http.json("GET", root + "/messages/" + quote(mid, safe="") + "/attachments/" + quote(attid, safe=""))
                        data = b["data"]
                    raw = base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))
                    suffix = ".txt" if part.get("mimeType", "").startswith("text/") else ".bin"
                    path = snap.put(aid, raw, suffix, "asset")
                assets.append({"part_id": part.get("partId"), "filename": part.get("filename"),
                               "mime_type": part.get("mimeType"), "path": str(path.relative_to(snap.path))})
            for child in part.get("parts", []):
                parts(child)
        parts(msg.get("payload", {}))
        snap.json(key, {"source": "gmail", "id": mid, "thread_id": msg.get("threadId"), "message": msg, "parts": assets})
    snap.json("scope", {"query": config["query"], "identity": config["expected_email"], "initial_history_id": profile.get("historyId"),
                        "note": "Full API enumeration is not a transactional mailbox snapshot."}, "metadata")


def calendar(config, snap, http=None):
    http = http or google_http(config)
    root = "https://www.googleapis.com/calendar/v3"
    for cid in config["calendar_ids"]:
        # Preserve recurring masters and exception events rather than expanding forever.
        params = {"maxResults": 2500, "singleEvents": "false", "showDeleted": "false"}
        if config.get("time_min"):
            params["timeMin"] = config["time_min"]
        if config.get("time_max"):
            params["timeMax"] = config["time_max"]
        for event in pages(http, root + "/calendars/" + quote(cid, safe="") + "/events", params):
            snap.json(f"event:{cid}:{event['id']}", {"calendar_id": cid, "event": event})


def tasks(config, snap, http=None):
    http = http or google_http(config)
    root = "https://tasks.googleapis.com/tasks/v1"
    lists = list(pages(http, root + "/users/@me/lists", {"maxResults": 100}))
    selected = config.get("tasklist_ids", [])
    if selected:
        found = {x["id"] for x in lists}
        if set(selected) - found:
            raise ImportFailure("Configured task list missing or inaccessible")
        lists = [x for x in lists if x["id"] in selected]
    for tasklist in lists:
        lid = tasklist["id"]
        snap.json("tasklist:" + lid, tasklist, "metadata")
        for task in pages(http, root + "/lists/" + quote(lid, safe="") + "/tasks",
                          {"maxResults": 100, "showCompleted": "true", "showHidden": "true", "showDeleted": "false"}):
            snap.json(f"task:{lid}:{task['id']}", {"tasklist_id": lid, "task": task})


class GdocBridge:
    """One gdoc process and authenticated API connection per source run."""
    def __init__(self, config):
        self.config = config
        self.process = subprocess.Popen(
            [config.get("gdoc_python", sys.executable), str(Path(__file__).with_name("gdoc_bridge.py")), "--serve"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)

    def call(self, action, **kwargs):
        payload = {"action": action, "account": self.config["expected_email"], **kwargs}
        try:
            self.process.stdin.write(json.dumps(payload) + "\n")
            self.process.stdin.flush()
            ready, _, _ = select.select([self.process.stdout], [], [], 600)
            if not ready:
                raise ImportFailure("gdoc operation timed out; resume this run")
            result = json.loads(self.process.stdout.readline())
        except (BrokenPipeError, ValueError):
            raise ImportFailure("gdoc bridge failed; check account/API access and retry") from None
        if "_bridge_error" in result:
            raise ImportFailure(f"gdoc {action} failed ({result['_bridge_error']}, HTTP {result.get('_http_status', 'n/a')}); file {kwargs.get('file_id', 'n/a')}; check permissions/export support and retry")
        return result

    def close(self):
        self.process.stdin.close()
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait()
        self.process.stdout.close()


def drive(config, snap):
    bridge = GdocBridge(config)
    local = threading.local()
    workers = []
    lock = threading.Lock()
    pool = ThreadPoolExecutor(max_workers=4)

    def download(job):
        item, key, cached = job
        if cached is not None:
            return job, None
        if not hasattr(local, "bridge"):
            local.bridge = GdocBridge(config)
            with lock:
                workers.append(local.bridge)
        result = local.bridge.call("download", file_id=item["id"], mime_type=item["mimeType"],
            filename=item["name"], max_bytes=config.get("max_file_bytes", 2_000_000_000),
            output_dir=str(snap.path / "transfer"))
        return job, result

    try:
        _drive(config, snap, bridge.call, lambda jobs: pool.map(download, jobs))
    finally:
        pool.shutdown(wait=True, cancel_futures=True)
        for worker in workers:
            worker.close()
        bridge.close()


def _drive(config, snap, call, download_map=None):
    identity = call("identity")
    if identity["email"].lower() != config["expected_email"].lower():
        raise ImportFailure("Drive identity mismatch")
    queue = deque(config["root_ids"])
    visited = set()
    jobs = []
    while queue:
        pending = queue.popleft()
        fid = pending["id"] if isinstance(pending, dict) else pending
        if fid in visited:
            continue
        visited.add(fid)
        item = pending if isinstance(pending, dict) else call("get", file_id=fid)
        if item.get("trashed"):
            raise ImportFailure("Configured Drive item is trashed; review scope")
        mime = item["mimeType"]
        snap.json("metadata:" + fid, item, "metadata")
        if mime == "application/vnd.google-apps.folder":
            token, tokens = None, set()
            while True:
                result = call("list", folder_id=fid, page_token=token, drive_id=item.get("driveId"))
                if result.get("incompleteSearch"):
                    raise ImportFailure("Drive reported an incomplete search")
                queue.extend(result.get("files", []))
                token = result.get("nextPageToken")
                if not token:
                    break
                if token in tokens:
                    raise ImportFailure("Drive pagination repeated")
                tokens.add(token)
            continue
        if mime == "application/vnd.google-apps.shortcut":
            snap.json("shortcut:" + fid, {"file": item, "content_exported": False,
                                          "reason": "Shortcut targets are not followed across authorised folder boundaries."})
            continue
        if mime in config.get("excluded_mime_types", []):
            snap.json("excluded:" + fid, {"file": item, "content_exported": False, "reason": "Configured MIME exclusion"}, "metadata")
            continue
        key = "file:" + fid + ":" + item.get("modifiedTime", "")
        jobs.append((item, key, snap.cached(key)))

    def sequential(jobs):
        for job in jobs:
            item, key, cached = job
            result = None if cached is not None else call("download", file_id=item["id"],
                mime_type=item["mimeType"], filename=item["name"],
                max_bytes=config.get("max_file_bytes", 2_000_000_000), output_dir=str(snap.path / "transfer"))
            yield job, result

    for (item, key, path), result in (download_map or sequential)(jobs):
        fid, mime = item["id"], item["mimeType"]
        if path is None:
            src = Path(result["path"])
            with src.open("rb") as f:
                path = snap.put_stream(key, iter(lambda: f.read(1024 * 1024), b""), result["suffix"], max_bytes=config.get("max_file_bytes", 2_000_000_000))
        snap.json("file-record:" + fid, {"file": item, "path": str(path.relative_to(snap.path)),
                                         "transfer_copies": "transfer/ (retained; subject to deletion policy)"})
        text = readable(path, mime)
        if text is not None:
            snap.put("text:" + fid, text.encode(), ".txt", "asset")
