import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from workspace_import import cli
from workspace_import.core import ImportFailure, Snapshot
from workspace_import.google_sources import gmail, calendar, tasks, _drive
from workspace_import.slack_source import slack
from workspace_import.takeout import takeout
from workspace_import.text_files import google_doc_text


class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.s = Snapshot(self.root, 'test', {}, 'one')
    def tearDown(self):
        self.s.close()
        self.tmp.cleanup()
    def records(self):
        return [json.loads((self.s.path / row[0]).read_text()) for row in self.s.db.execute("SELECT path FROM objects WHERE kind='record'")]

    def test_gmail_two_pages_and_attachment(self):
        calls = []
        class API:
            def json(inner, method, url, params=None):
                calls.append((url, params))
                if url.endswith('/profile'):
                    return {'emailAddress': 'test@example.org'}
                if url.endswith('/messages'):
                    if (params or {}).get('pageToken'):
                        return {'messages': [{'id': 'b'}]}
                    return {'messages': [{'id': 'a'}], 'nextPageToken': 'next'}
                if '/attachments/' in url:
                    return {'data': 'ZmlsZQ'}
                return {'id': url[-1], 'payload': {'partId': '0', 'mimeType': 'text/plain',
                    'body': {'data': 'aGVsbG8'}, 'parts': [{'partId': '1', 'body': {'attachmentId': 'x'}}]}}
        gmail({'expected_email': 'test@example.org', 'query': ''}, self.s, API())
        self.assertEqual(self.s.finish()['records'], 2)
        self.assertEqual(len([x for x in calls if '/attachments/' in x[0]]), 2)
        self.assertTrue(any(p.read_text() == 'hello' for p in (self.s.path / 'objects').glob('*.txt')))

    def test_wrong_gmail_identity_stops_before_messages(self):
        class API:
            def json(inner, *args, **kwargs):
                return {'emailAddress': 'wrong@example.org'}
        with self.assertRaises(ImportFailure):
            gmail({'expected_email': 'test@example.org', 'query': ''}, self.s, API())
        self.assertEqual(self.s.verify()['records'], 0)

    def test_calendar_retains_recurrence(self):
        class API:
            def json(inner, method, url, params):
                self.assertEqual(params['singleEvents'], 'false')
                return {'items': [{'id': 'master', 'recurrence': ['RRULE:FREQ=WEEKLY']}, {'id': 'exception', 'recurringEventId': 'master'}]}
        calendar({'calendar_ids': ['primary']}, self.s, API())
        self.assertEqual(self.s.finish()['records'], 2)

    def test_tasks_includes_completed_hidden_and_pages(self):
        class API:
            def json(inner, method, url, params):
                if url.endswith('/lists'):
                    return {'items': [{'id': 'list'}]}
                self.assertEqual(params['showHidden'], 'true')
                self.assertEqual(params['showCompleted'], 'true')
                if params.get('pageToken'):
                    return {'items': [{'id': 'done', 'status': 'completed'}]}
                return {'items': [{'id': 'todo'}], 'nextPageToken': 'next'}
        tasks({}, self.s, API())
        self.assertEqual(self.s.finish()['records'], 2)

    def test_slack_target_reply_keeps_full_thread(self):
        class API:
            def call(inner, *args, **kwargs):
                return {'ok': True}
            def pages(inner, method, field, **params):
                if method == 'conversations.history':
                    return iter([{'ts': '1', 'reply_count': 2}, {'ts': '4', 'text': 'unrelated', 'user': 'other'}])
                return iter([{'ts':'1','text':'root','user':'other'}, {'ts':'2','text':'<@target>','user':'other'}, {'ts':'3','text':'context','user':'other'}])
        slack({'channel_ids':['channel'],'user_id':'target','mode':'participated'}, self.s, API())
        self.assertEqual(self.s.finish()['records'], 1)
        self.assertEqual(len(self.records()[0]['messages']), 3)

    def test_takeout_preserves_nested_files_without_extracting_names(self):
        path = self.root / 'sample.zip'
        with zipfile.ZipFile(path, 'w') as z:
            z.writestr('Takeout/Mail/email.mbox', 'From sender\nSubject: synthetic\n\nbody\n')
            z.writestr('Takeout/Calendar/calendar.ics', 'BEGIN:VCALENDAR\nEND:VCALENDAR')
        takeout({'archive': str(path)}, self.s)
        self.assertEqual(self.s.finish()['records'], 2)
        self.assertFalse((self.s.path / 'Takeout').exists())

    def test_takeout_path_traversal_refused(self):
        path = self.root / 'bad.zip'
        with zipfile.ZipFile(path, 'w') as z:
            z.writestr('../escaped', 'bad')
        with self.assertRaises(ImportFailure):
            takeout({'archive': str(path)}, self.s)

    def test_takeout_expansion_limit_refused(self):
        path = self.root / 'large.zip'
        with zipfile.ZipFile(path, 'w') as z:
            z.writestr('big.txt', 'a' * 1000)
        with self.assertRaises(ImportFailure):
            takeout({'archive': str(path), 'max_file_bytes': 100}, self.s)

    def test_drive_reuses_list_metadata_and_exports_readable_text(self):
        calls = []
        asset = self.root / 'input.txt'; asset.write_text('synthetic document')
        def call(action, **kwargs):
            calls.append(action)
            if action == 'identity':
                return {'email':'test@example.org'}
            if action == 'get':
                return {'id':'root','mimeType':'application/vnd.google-apps.folder'}
            if action == 'list':
                return {'files':[{'id':'file','name':'test.txt','mimeType':'text/plain','modifiedTime':'now'}]}
            return {'path':str(asset),'suffix':'.txt'}
        _drive({'expected_email':'test@example.org','root_ids':['root']}, self.s, call)
        self.assertEqual(calls.count('get'), 1)
        self.assertEqual(self.s.finish()['records'], 1)
        self.assertEqual(self.s.cached('text:file').read_text(), 'synthetic document')

    def test_docs_all_tabs_readable(self):
        doc = {'tabs': [{'documentTab': {'body': [{'textRun': {'content': 'first'}}]}},
                        {'documentTab': {'body': [{'textRun': {'content': 'second'}}]}}]}
        self.assertEqual(google_doc_text(doc), 'firstsecond')

    def test_slack_configuration_uses_slack_credential_path(self):
        cfg = self.root / 'config.json'
        cfg.write_text(json.dumps({'email':'test@example.org','sources':{}}))
        source = self.root / 'source.json'
        source.write_text(json.dumps({'type':'slack','team_id':'team','user_id':'user'}))
        with patch.object(cli, 'CONFIG', cfg), patch('sys.argv', ['workspace-import','configure','slack','--file',str(source)]):
            self.assertEqual(cli.main(), 0)
        saved = json.loads(cfg.read_text())['sources']['slack']
        self.assertTrue(saved['token_file'].endswith('/slack.json'))

    def test_cli_archive_full_cycle_and_work_preserved(self):
        cfg = self.root / 'config.json'
        archive = self.root / 'sample.zip'
        with zipfile.ZipFile(archive, 'w') as z:
            z.writestr('readme.txt', 'synthetic')
        config = {'email':'test@example.org', 'data_root':str(self.root / 'data'),
                  'sources':{'takeout':{'type':'takeout','archive':str(archive)}}}
        cfg.write_text(json.dumps(config))
        work = self.root / 'work'; work.mkdir(); (work / 'notes.txt').write_text('keep')
        with patch.object(cli, 'CONFIG', cfg):
            cli.run('takeout')
        self.assertTrue((self.root / 'data/takeout/current/COMPLETE.json').exists())
        self.assertEqual((work / 'notes.txt').read_text(), 'keep')


if __name__ == '__main__':
    unittest.main()
