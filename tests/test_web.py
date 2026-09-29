import unittest
from unittest.mock import patch
from workspace_import.web_source import validate_url, Text
from workspace_import.core import ImportFailure


class WebTests(unittest.TestCase):
    def test_private_destination_refused(self):
        with patch('socket.getaddrinfo', return_value=[(2,1,6,'',('127.0.0.1',443))]):
            with self.assertRaises(ImportFailure):
                validate_url('https://example.com')
    def test_plaintext_and_embedded_credentials_refused(self):
        for url in ['http://example.com','https://user:pass@example.com','https://example.com:8443']:
            with self.assertRaises(ImportFailure):
                validate_url(url)
    def test_html_scripts_not_in_readable_text(self):
        p = Text(); p.feed('<p>hello</p><script>private()</script><p>world</p>')
        self.assertIn('hello', ''.join(p.parts))
        self.assertNotIn('private', ''.join(p.parts))
