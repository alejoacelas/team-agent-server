import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from workspace_import import cli
from workspace_import.core import ImportFailure, Snapshot
from workspace_import.salesforce_source import Salesforce, salesforce
from workspace_import.airtable_source import airtable


class FakeHTTP:
    def __init__(self, routes):
        self.routes, self.calls = routes, []
        self.session = type('S', (), {'headers': {}})()

    def json(self, method, url, params=None, data=None, json=None):
        self.calls.append((method, url, params, data, json))
        key = url + ('?' + '&'.join(f'{k}={v}' for k, v in sorted((params or {}).items())) if params else '')
        return self.routes[key]


class NewSourceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.s = Snapshot(self.root / 'data', 'test', {}, 'one')

    def tearDown(self):
        self.s.close()
        self.tmp.cleanup()

    def records(self):
        return [json.loads((self.s.path / row[0]).read_text()) for row in self.s.db.execute("SELECT path FROM objects WHERE kind='record'")]

    def cred(self, **extra):
        path = self.root / 'sf.json'
        path.write_text(json.dumps({'instance_url': 'https://acme.my.salesforce.com', **extra}))
        return str(path)

    def test_salesforce_client_credentials_describe_and_pages(self):
        base = 'https://acme.my.salesforce.com'
        api = '/services/data/v62.0'
        http = FakeHTTP({
            base + '/services/oauth2/token': {'access_token': 'tok'},
            f'{base}{api}/sobjects/Contact/describe': {'fields': [
                {'name': 'Id', 'type': 'id'}, {'name': 'Name', 'type': 'string'},
                {'name': 'MailingAddress', 'type': 'address'}]},
            f'{base}{api}/query?q=SELECT Id, Name FROM Contact': {
                'done': False, 'nextRecordsUrl': f'{api}/query/01g-2000',
                'records': [{'attributes': {}, 'Id': 'a', 'Name': 'A'}]},
            f'{base}{api}/query/01g-2000': {'done': True, 'records': [{'Id': 'b', 'Name': 'B'}]},
        })
        client = Salesforce({'token_file': self.cred(client_id='id', client_secret='secret')}, http=http)
        self.assertEqual(http.session.headers['Authorization'], 'Bearer tok')
        salesforce({'objects': ['Contact']}, self.s, api=client)
        self.assertEqual(sorted(r['Id'] for r in self.records()), ['a', 'b'])
        self.assertNotIn('attributes', self.records()[0])

    def test_salesforce_rejects_foreign_host_injected_names_and_early_stop(self):
        path = self.root / 'bad.json'
        path.write_text(json.dumps({'instance_url': 'https://evil.example.com', 'access_token': 't'}))
        with self.assertRaises(ImportFailure):
            Salesforce({'token_file': str(path)}, http=FakeHTTP({}))
        client = Salesforce({'token_file': self.cred(access_token='t')}, http=FakeHTTP({}))
        with self.assertRaises(ImportFailure):
            salesforce({'objects': ['Contact'], 'fields': {'Contact': ['Id; DELETE']}}, self.s, api=client)
        api = '/services/data/v62.0'
        client.http = FakeHTTP({f'https://acme.my.salesforce.com{api}/query?q=SELECT Id FROM Contact':
                                {'done': False, 'records': []}})
        client.http.session.headers = {}
        with self.assertRaises(ImportFailure):
            salesforce({'objects': ['Contact'], 'fields': {'Contact': ['Id']}}, self.s, api=client)

    def test_airtable_tables_filter_and_offsets(self):
        api = 'https://api.airtable.com/v0'

        class Client:
            http = FakeHTTP({
                f'{api}/meta/bases/app1/tables': {'tables': [{'id': 'tbl1', 'name': 'Calls'}, {'id': 'tbl2', 'name': 'Other'}]},
                f'{api}/app1/tbl1?pageSize=100': {'records': [{'id': 'r1', 'fields': {'Summary': 'x'}}], 'offset': 'o1'},
                f'{api}/app1/tbl1?offset=o1&pageSize=100': {'records': [{'id': 'r2', 'fields': {}}]},
            })
        from workspace_import.airtable_source import Airtable
        client = Airtable.__new__(Airtable)
        client.http = Client.http
        airtable({'base_ids': ['app1'], 'table_ids': ['Calls']}, self.s, api=client)
        self.assertEqual(sorted(r['id'] for r in self.records()), ['r1', 'r2'])
        self.assertTrue(all(r['table'] == 'Calls' for r in self.records()))

    def test_exa_requires_key_and_trims_results(self):
        with patch.object(cli, 'EXA_KEY', self.root / 'missing'):
            with self.assertRaises(ImportFailure):
                cli.exa('/search', {})
        key = self.root / 'exa-key'
        key.write_text('k\n')
        with patch.object(cli, 'EXA_KEY', key), patch('workspace_import.core.HTTP.json',
                return_value={'results': [{'title': 'T', 'url': 'https://x', 'id': 'drop', 'text': 'body'}],
                              'costDollars': {'total': 0.007}}) as call:
            out = cli.exa('/search', {'query': 'q'})
        self.assertEqual(out, {'results': [{'title': 'T', 'url': 'https://x', 'text': 'body'}], 'cost_dollars': 0.007})
        self.assertEqual(call.call_args[0][1], 'https://api.exa.ai/search')


if __name__ == '__main__':
    unittest.main()
