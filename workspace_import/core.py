from __future__ import annotations

import contextlib
import datetime as dt
import email.utils
import fcntl
import hashlib
import json
import os
from pathlib import Path
import random
import re
import shutil
import sqlite3
import time
from urllib.parse import urlparse

import requests


class ImportFailure(RuntimeError):
    pass


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def file_sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def atomic(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temp = path.with_name(path.name + ".part")
    with temp.open("wb") as f:
        os.chmod(temp, 0o600)
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.replace(temp, path)


def slug(value):
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,100}", value):
        raise ImportFailure("Invalid source or run name")
    return value


@contextlib.contextmanager
def source_lock(directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (directory / ".lock").open("a") as f:
        os.chmod(f.name, 0o600)
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ImportFailure("Another import holds this source lock") from None
        yield


class Snapshot:
    """A generation is invisible to readers until a verified atomic pointer switch.

    Resuming replays the discovery pass; completed per-object downloads are reused
    only when their key and hash match. Publishing removes every other generation,
    so records deleted at the source leave the server with the next refresh.
    """

    def __init__(self, root, name, config, run_id=None):
        self.base = Path(root).resolve() / slug(name)
        self.run_id = slug(run_id or dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + os.urandom(3).hex())
        self.path = self.base / "runs" / self.run_id
        self.path.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.fingerprint = sha(canonical(config))
        info = self.path / "run.json"
        if info.exists():
            if json.loads(info.read_text())["config_sha256"] != self.fingerprint:
                raise ImportFailure("Config changed: start a new generation instead of resuming")
            if (self.path / "COMPLETE.json").exists():
                raise ImportFailure("Completed generation is immutable; start a new run")
        else:
            atomic(info, canonical({"run_id": self.run_id, "config_sha256": self.fingerprint,
                                    "started_at": dt.datetime.now(dt.timezone.utc).isoformat()}))
        self.db = sqlite3.connect(self.path / "manifest.sqlite")
        os.chmod(self.path / "manifest.sqlite", 0o600)
        self.db.execute("CREATE TABLE IF NOT EXISTS objects (key TEXT PRIMARY KEY, path TEXT, sha256 TEXT, size INTEGER, kind TEXT)")
        self.db.execute("CREATE TABLE IF NOT EXISTS checkpoint (key TEXT PRIMARY KEY, value TEXT)")
        self.db.commit()
        self.seen = set()

    def close(self):
        self.db.close()

    def _writable(self):
        if (self.path / "COMPLETE.json").exists():
            raise ImportFailure("Completed generation is immutable; start a new run")

    def checkpoint(self, key, value=None):
        if value is not None:
            self._writable()
            self.db.execute("INSERT OR REPLACE INTO checkpoint VALUES (?,?)", (key, json.dumps(value)))
            self.db.commit()
            return value
        row = self.db.execute("SELECT value FROM checkpoint WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else None

    def cached(self, key):
        row = self.db.execute("SELECT path,sha256,size FROM objects WHERE key=?", (key,)).fetchone()
        if row:
            path = self.path / row[0]
            if path.is_file() and path.stat().st_size == row[2] and file_sha(path) == row[1]:
                self.seen.add(key)
                return path
        return None

    def put(self, key, data, suffix=".json", kind="record"):
        return self.put_stream(key, [data], suffix, kind)

    def json(self, key, obj, kind="record"):
        # Metadata is rewritten so current discovery never preserves stale text.
        return self.put(key, canonical(obj), ".json", kind)

    def put_stream(self, key, chunks, suffix=".bin", kind="asset", max_bytes=2_000_000_000):
        self._writable()
        if not re.fullmatch(r"\.[a-zA-Z0-9.]+", suffix):
            raise ImportFailure("Unsafe filename suffix")
        rel = f"objects/{sha(key.encode())}{suffix}"
        path = self.path / rel
        path.parent.mkdir(exist_ok=True, mode=0o700)
        temp = path.with_name(path.name + ".part")
        h, size = hashlib.sha256(), 0
        with temp.open("wb") as f:
            os.chmod(temp, 0o600)
            for chunk in chunks:
                size += len(chunk)
                if size > max_bytes:
                    raise ImportFailure("Object exceeds configured size limit")
                h.update(chunk)
                f.write(chunk)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, path)
        self.db.execute("INSERT OR REPLACE INTO objects VALUES (?,?,?,?,?)", (key, rel, h.hexdigest(), size, kind))
        self.db.commit()
        self.seen.add(key)
        return path

    def verify(self):
        count, total = 0, 0
        for key, rel, digest, size, kind in self.db.execute("SELECT * FROM objects"):
            path = self.path / rel
            if not path.is_file() or path.stat().st_size != size or file_sha(path) != digest:
                raise ImportFailure("Manifest verification failed")
            count += kind == "record"
            total += size
        return {"records": count, "bytes": total}

    def finish(self, minimum=1, max_drop_fraction=0.5, publish=False, allow_drop=False):
        self._writable()
        registered = {row[0] for row in self.db.execute("SELECT path FROM objects")}
        objects = self.path / "objects"
        if objects.exists() and any(str(p.relative_to(self.path)) not in registered for p in objects.iterdir()):
            raise ImportFailure("Untracked or partial object files remain; start a fresh run")
        # A resume cannot quietly publish assets from records that disappeared.
        saved = {r[0] for r in self.db.execute("SELECT key FROM objects")}
        if saved - self.seen:
            raise ImportFailure("Source changed during resume: stale objects remain; start a fresh run")
        stats = self.verify()
        if stats["records"] < minimum:
            raise ImportFailure("Record count below configured minimum; not published")
        current = self.base / "current"
        previous = None
        if current.exists():
            previous = json.loads((current / "COMPLETE.json").read_text())
            if not allow_drop and stats["records"] < previous["records"] * (1 - max_drop_fraction):
                raise ImportFailure("Unexpected record-count drop; review scope before publishing")
        summary = {**stats, "run_id": self.run_id, "completed_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                   "scope": "configured-source-visible-records", "config_sha256": self.fingerprint,
                   "retained_old_generations": not publish}
        atomic(self.path / "COMPLETE.json", canonical(summary))
        if publish:
            temp = self.base / "current.next"
            if temp.is_symlink():
                temp.unlink()  # Our own disposable pointer, never data.
            temp.symlink_to(Path("runs") / self.run_id, target_is_directory=True)
            os.replace(temp, current)
            atomic(self.base / "status.json", canonical({**summary, "status": "complete"}))
            for old in (self.base / "runs").iterdir():
                if old.name != self.run_id and not old.is_symlink():
                    shutil.rmtree(old)
        return summary


class HTTP:
    def __init__(self, headers=None, session=None, sleep=time.sleep, attempts=6, min_interval=0):
        self.session = session or requests.Session()
        if headers:
            self.session.headers.update(headers)
        self.sleep, self.attempts = sleep, attempts
        self.min_interval = min_interval
        self.last = 0.0

    def request(self, method, url, **kwargs):
        if urlparse(url).scheme != "https":
            raise ImportFailure("Only HTTPS API endpoints are allowed")
        for attempt in range(self.attempts):
            self.sleep(max(0, self.min_interval - (time.monotonic() - self.last)))
            self.last = time.monotonic()
            try:
                r = self.session.request(method, url, timeout=(15, 120), allow_redirects=False, **kwargs)
            except (requests.Timeout, requests.ConnectionError):
                if attempt + 1 == self.attempts:
                    raise ImportFailure("API connection failed after retries") from None
                self.sleep(min(60, 2 ** attempt) + random.random())
                continue
            retry = r.status_code in (408, 429, 500, 502, 503, 504)
            if r.status_code == 403:
                try:
                    retry = any(x.get("reason") in ("rateLimitExceeded", "userRateLimitExceeded")
                                for x in r.json().get("error", {}).get("errors", []))
                except (ValueError, AttributeError):
                    pass
            if retry and attempt + 1 < self.attempts:
                value = r.headers.get("Retry-After", "")
                try:
                    delay = float(value)
                except ValueError:
                    try:
                        delay = email.utils.parsedate_to_datetime(value).timestamp() - time.time()
                    except (ValueError, TypeError):
                        delay = min(60, 2 ** attempt) + random.random()
                r.close()
                if delay > 300:
                    raise ImportFailure("Rate limit requires a later retry; resume this run")
                self.sleep(max(0, delay))
                continue
            if not 200 <= r.status_code < 300:
                code = r.status_code
                r.close()
                raise ImportFailure(f"API HTTP {code} from {urlparse(url).hostname}")
            return r
        raise ImportFailure("API retries exhausted")

    def json(self, method, url, **kwargs):
        with self.request(method, url, **kwargs) as r:
            try:
                return r.json()
            except ValueError:
                raise ImportFailure("API returned invalid JSON") from None


def pages(http, url, params=None, items="items", token="nextPageToken", request_token="pageToken"):
    params = dict(params or {})
    seen = set()
    while True:
        result = http.json("GET", url, params=params)
        if items not in result:
            # Google commonly omits the collection field when it is empty.
            values = []
        else:
            values = result[items]
        if not isinstance(values, list):
            raise ImportFailure("Unexpected API collection")
        yield from values
        next_token = result.get(token)
        if not next_token:
            break
        if next_token in seen:
            raise ImportFailure("Repeated pagination token")
        seen.add(next_token)
        params[request_token] = next_token
