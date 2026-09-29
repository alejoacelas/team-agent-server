#!/usr/bin/env python3
"""Synthetic bulk/restore check. Run as the actual member, never root."""
import json
import os
from pathlib import Path
import sqlite3
import tarfile
import time
from workspace_import.core import Snapshot, file_sha, source_lock

assert os.getuid() != 0
base = Path.home() / 'workspace' / 'test-evidence' / time.strftime('%Y%m%dT%H%M%S')
base.mkdir(parents=True, mode=0o700)
start = time.monotonic()
with source_lock(base / 'bulk'):
    s = Snapshot(base, 'bulk', {'synthetic': True})
    for n in range(5000):
        s.json(str(n), {'index': n, 'text': 'synthetic call transcript ' * 20})
    summary = s.finish(publish=True)
    s.close()
archive = base / 'synthetic-backup.tar'
with tarfile.open(archive, 'w') as t:
    t.add(base / 'bulk', arcname='bulk')
restore = base / 'restored'; restore.mkdir(mode=0o700)
with tarfile.open(archive) as t:
    t.extractall(restore, filter='data')
current = restore / 'bulk/current'
with sqlite3.connect(f'file:{current / "manifest.sqlite"}?mode=ro', uri=True) as db:
    rows = list(db.execute('SELECT path,sha256,size FROM objects'))
for rel, digest, size in rows:
    p = current / rel
    assert p.stat().st_size == size and file_sha(p) == digest
assert len(rows) == 5000
print(json.dumps({'status': 'passed', 'records': 5000, 'elapsed_seconds': round(time.monotonic()-start,2),
                  'bytes': summary['bytes'], 'restore_verified': True,
                  'backup_scope': 'synthetic local archive, not off-host disaster recovery',
                  'evidence_directory': str(base)}, indent=2))
