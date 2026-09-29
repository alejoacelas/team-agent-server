import multiprocessing
import os
from pathlib import Path
import tempfile
import unittest

from workspace_import.core import Snapshot, ImportFailure, source_lock, HTTP, pages


def interrupted(root):
    s = Snapshot(root, 'mail', {}, 'interrupted')
    s.json('saved', {'text': 'synthetic saved record'})
    def chunks():
        yield b'partial'
        os._exit(19)
    s.put_stream('unfinished', chunks())


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.snapshots = []

    def tearDown(self):
        for s in self.snapshots:
            s.close()
        self.tmp.cleanup()

    def snapshot(self, run='first', config=None):
        s = Snapshot(self.root, 'mail', config or {}, run)
        self.snapshots.append(s)
        return s

    def test_killed_writer_resumes_without_publishing_partial_bytes(self):
        process = multiprocessing.Process(target=interrupted, args=(str(self.root),))
        process.start()
        process.join(10)
        self.assertEqual(process.exitcode, 19)
        self.assertFalse((self.root / 'mail/current').exists())
        s = self.snapshot('interrupted')
        self.assertIsNotNone(s.cached('saved'))
        self.assertIsNone(s.cached('unfinished'))
        s.put_stream('unfinished', [b'complete'])
        self.assertEqual(s.finish(publish=True)['records'], 1)
        self.assertEqual(s.cached('unfinished').read_bytes(), b'complete')

    def test_hash_corruption_blocks_publication(self):
        s = self.snapshot()
        p = s.json('one', {'x': 1})
        p.write_bytes(b'corrupt')
        self.assertIsNone(s.cached('one'))
        with self.assertRaises(ImportFailure):
            s.finish(publish=True)
        self.assertFalse((s.base / 'current').exists())

    def test_rejected_generation_preserves_old_current(self):
        s = self.snapshot()
        for i in range(10):
            s.json(str(i), {'i': i})
        s.finish(publish=True)
        second = self.snapshot('second')
        second.json('one', {})
        with self.assertRaises(ImportFailure):
            second.finish(publish=True)
        self.assertEqual((s.base / 'current').resolve(), s.path)

    def test_config_change_refuses_resume(self):
        self.snapshot()
        with self.assertRaises(ImportFailure):
            self.snapshot(config={'different': True})

    def test_missing_record_on_resume_blocks_publication(self):
        self.snapshot().json('disappeared', {})
        resumed = self.snapshot()
        resumed.json('new', {})
        with self.assertRaises(ImportFailure):
            resumed.finish(publish=True)

    def test_completed_generation_cannot_be_reopened(self):
        s = self.snapshot()
        s.json('one', {})
        s.finish()
        with self.assertRaises(ImportFailure):
            self.snapshot()

    def test_completed_handle_cannot_mutate_published_data(self):
        s = self.snapshot()
        p = s.json('one', {'original': True})
        original = p.read_bytes()
        s.finish(publish=True)
        with self.assertRaises(ImportFailure):
            s.json('one', {'changed': True})
        self.assertEqual(p.read_bytes(), original)

    def test_publishing_removes_older_generations(self):
        first = self.snapshot('first')
        first.json('deleted-at-source', {'text': 'synthetic'})
        first.finish(publish=True)
        second = self.snapshot('second')
        second.json('kept', {'text': 'synthetic'})
        second.finish(publish=True, allow_drop=True)
        self.assertEqual([p.name for p in (second.base / 'runs').iterdir()], ['second'])
        self.assertEqual((second.base / 'current').resolve(), second.path.resolve())

    def test_orphan_partial_blocks_publication(self):
        s = self.snapshot()
        s.json('one', {})
        (s.path / 'objects/orphan.part').write_text('partial data')
        with self.assertRaises(ImportFailure):
            s.finish(publish=True)
        self.assertFalse((s.base / 'current').exists())

    def test_size_limit_keeps_partial_out_of_manifest(self):
        s = self.snapshot()
        with self.assertRaises(ImportFailure):
            s.put_stream('large', [b'12345', b'67890'], max_bytes=6)
        self.assertIsNone(s.cached('large'))
        self.assertEqual(s.verify()['bytes'], 0)

    def test_lock_refuses_second_writer(self):
        with source_lock(self.root):
            with self.assertRaises(ImportFailure):
                with source_lock(self.root):
                    pass

    def test_files_are_owner_only(self):
        s = self.snapshot()
        p = s.json('one', {})
        for path in (p, s.path / 'manifest.sqlite', s.path / 'run.json'):
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(s.path.stat().st_mode & 0o777, 0o700)


class Response:
    def __init__(self, code=200, headers=None):
        self.status_code, self.headers = code, headers or {}
    def close(self):
        pass


class Session:
    def __init__(self, responses):
        self.responses, self.calls = iter(responses), []
    def request(self, *args, **kwargs):
        self.calls.append(kwargs)
        return next(self.responses)


class TransportTests(unittest.TestCase):
    def test_429_respects_retry_after(self):
        waits = []
        session = Session([Response(429, {'Retry-After': '3'}), Response()])
        HTTP(session=session, sleep=waits.append).request('GET', 'https://example.test')
        self.assertIn(3, waits)
        self.assertEqual(len(session.calls), 2)
        self.assertFalse(session.calls[0]['allow_redirects'])

    def test_oversized_retry_wait_fails_for_later_resume(self):
        session = Session([Response(429, {'Retry-After': '600'})])
        with self.assertRaises(ImportFailure):
            HTTP(session=session, sleep=lambda _: None).request('GET', 'https://example.test')

    def test_redirect_does_not_forward_credentials(self):
        session = Session([Response(302, {'Location': 'https://other.test'})])
        with self.assertRaises(ImportFailure):
            HTTP(session=session, sleep=lambda _: None).request('GET', 'https://example.test')
        self.assertEqual(len(session.calls), 1)

    def test_empty_page_does_not_stop_pagination(self):
        results = iter([{'nextPageToken': 'a'}, {'items': [1, 2]}])
        class API:
            def json(self, *args, **kwargs):
                return next(results)
        self.assertEqual(list(pages(API(), 'unused')), [1, 2])

    def test_repeated_cursor_fails(self):
        class API:
            def json(self, *args, **kwargs):
                return {'items': [1], 'nextPageToken': 'same'}
        with self.assertRaises(ImportFailure):
            list(pages(API(), 'unused'))


if __name__ == '__main__':
    unittest.main()
