import datetime as dt
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import urlparse, parse_qs

from workspace_import import cli
from workspace_import.core import ImportFailure


class PastedSignInTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.client = root / 'client.json'
        self.client.write_text(json.dumps({'installed': {
            'client_id': 'id.apps.googleusercontent.com', 'client_secret': 'secret',
            'auth_uri': 'https://accounts.google.com/o/oauth2/auth',
            'token_uri': 'https://oauth2.googleapis.com/token',
            'redirect_uris': ['http://localhost']}}))
        config = root / 'config.json'
        config.write_text(json.dumps({'email': 'member@example.org', 'data_root': str(root), 'sources': {}}))
        self.pending = root / 'google-pending.json'
        for name, value in (('CONFIG', config), ('PENDING', self.pending)):
            patcher = patch.object(cli, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.addCleanup(self.tmp.cleanup)

    def start(self):
        with patch.object(cli, 'emit') as emit:
            cli.start_google(8765, str(self.client))
        url = emit.call_args[0][0]['open_this_link']
        return parse_qs(urlparse(url).query)

    def test_start_uses_loopback_pkce_and_private_pending_file(self):
        query = self.start()
        self.assertEqual(query['redirect_uri'], ['http://127.0.0.1:8765/'])
        self.assertEqual(query['code_challenge_method'], ['S256'])
        self.assertEqual(query['login_hint'], ['member@example.org'])
        self.assertEqual(query['access_type'], ['offline'])
        self.assertEqual(self.pending.stat().st_mode & 0o777, 0o600)
        self.assertNotIn('secret', self.pending.read_text())

    def test_finish_exchanges_matching_address(self):
        state = self.start()['state'][0]
        verifier = json.loads(self.pending.read_text())[state]['code_verifier']
        seen = {}
        def fetch(flow, authorization_response):
            seen['response'] = authorization_response
            seen['verifier'] = flow.code_verifier
        with patch('google_auth_oauthlib.flow.Flow.fetch_token', fetch), \
             patch('google_auth_oauthlib.flow.Flow.credentials', 'creds'), \
             patch.object(cli, 'save_google') as save:
            cli.finish_google(f'http://127.0.0.1:8765/?state={state}&code=abc&scope=x\n')
        self.assertTrue(seen['response'].startswith('https://127.0.0.1:8765/'))
        self.assertEqual(seen['verifier'], verifier)
        save.assert_called_once()
        self.assertEqual(json.loads(self.pending.read_text()), {})

    def test_finish_rejects_wrong_state_host_denial_and_expiry(self):
        state = self.start()['state'][0]
        for address in (f'http://127.0.0.1:8765/?state=other&code=abc',
                        f'http://127.0.0.1:9999/?state={state}&code=abc',
                        f'https://example.org/?state={state}&code=abc',
                        f'http://127.0.0.1:8765/?state={state}&error=access_denied',
                        'code=abc'):
            with self.assertRaises(ImportFailure):
                cli.finish_google(address)
        self.assertTrue(self.pending.exists())
        pending = json.loads(self.pending.read_text())
        pending[state]['created'] = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=1)).isoformat()
        self.pending.write_text(json.dumps(pending))
        with self.assertRaises(ImportFailure):
            cli.finish_google(f'http://127.0.0.1:8765/?state={state}&code=abc')

    def test_older_unexpired_link_still_finishes(self):
        first = self.start()['state'][0]
        second = self.start()['state'][0]
        self.assertNotEqual(first, second)
        with patch('google_auth_oauthlib.flow.Flow.fetch_token'), \
             patch('google_auth_oauthlib.flow.Flow.credentials', 'creds'), \
             patch.object(cli, 'save_google') as save:
            cli.finish_google(f'http://127.0.0.1:8765/?state={first}&code=abc')
        save.assert_called_once()
        self.assertEqual(list(json.loads(self.pending.read_text())), [second])

    def test_finish_without_start(self):
        with self.assertRaises(ImportFailure):
            cli.finish_google('http://127.0.0.1:8765/?state=x&code=abc')


if __name__ == '__main__':
    unittest.main()
