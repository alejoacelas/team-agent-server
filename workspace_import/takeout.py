"""Import ZIP/TGZ members to hashed files without extracting paths or links."""
from pathlib import Path, PurePosixPath
import tarfile
import zipfile
from .core import ImportFailure, file_sha


def takeout(config, snap):
    archive = Path(config['archive']).expanduser()
    expected = snap.checkpoint('archive_sha256')
    digest = file_sha(archive)
    if expected and expected != digest:
        raise ImportFailure('Archive changed since this run started')
    snap.checkpoint('archive_sha256', digest)
    maximum = config.get('max_file_bytes', 20_000_000_000)
    total_limit = config.get('max_total_bytes', 100_000_000_000)
    seen, total = set(), 0

    def save(name, size, opener):
        nonlocal total
        path = PurePosixPath(name)
        if path.is_absolute() or '..' in path.parts or '\\' in name or name in seen:
            raise ImportFailure('Unsafe or duplicate archive path')
        seen.add(name)
        total += size
        if size > maximum or total > total_limit:
            raise ImportFailure('Archive exceeds configured size limits')
        key = 'member:' + name
        suffix = path.suffix.lower()
        if not suffix or not suffix[1:].isalnum():
            suffix = '.bin'
        asset = snap.cached(key)
        if asset is None:
            with opener() as stream:
                asset = snap.put_stream(key, iter(lambda: stream.read(1024 * 1024), b''), suffix, max_bytes=maximum)
        if asset.stat().st_size != size:
            raise ImportFailure('Archive member size mismatch')
        snap.json('record:' + name, {'archive_path': name, 'bytes': size,
                                   'file': str(asset.relative_to(snap.path))})

    if zipfile.is_zipfile(archive):
        with zipfile.ZipFile(archive) as z:
            for member in z.infolist():
                if member.is_dir():
                    continue
                if (member.external_attr >> 16) & 0o170000 == 0o120000:
                    raise ImportFailure('Archive symlinks are not supported')
                save(member.filename, member.file_size, lambda m=member: z.open(m))
    else:
        with tarfile.open(archive, 'r:*') as t:
            for member in t:
                if member.isdir():
                    continue
                if not member.isfile():
                    raise ImportFailure('Archive links and special files are not supported')
                save(member.name, member.size, lambda m=member: t.extractfile(m))
