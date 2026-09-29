"""Download explicit public URLs; no provider credentials or login cookies."""
import ipaddress
from html.parser import HTMLParser
import socket
from urllib.parse import urljoin, urlparse
import requests
from .core import ImportFailure


def validate_url(url):
    p = urlparse(url)
    if p.scheme != 'https' or not p.hostname or p.username or p.password or p.port not in (None,443):
        raise ImportFailure('Public web import requires HTTPS URLs without credentials on port 443')
    addresses = socket.getaddrinfo(p.hostname, 443, type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
        raise ImportFailure('Public web import refuses non-public destination')


class Text(HTMLParser):
    def __init__(self):
        super().__init__(); self.parts = []; self.skip = 0
    def handle_starttag(self, tag, attrs):
        if tag in ('script','style'):
            self.skip += 1
        if tag in ('p','div','br','h1','h2','li'):
            self.parts.append('\n')
    def handle_endtag(self, tag):
        if tag in ('script','style') and self.skip:
            self.skip -= 1
    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def web(config, snap):
    session = requests.Session(); session.trust_env = False
    for original in config['urls']:
        url = original
        for step in range(6):
            validate_url(url)
            with session.get(url, stream=True, timeout=(15,60), allow_redirects=False) as r:
                if r.status_code in (301,302,303,307,308):
                    url = urljoin(url, r.headers.get('Location',''))
                    continue
                if r.status_code != 200:
                    raise ImportFailure(f'Public website returned HTTP {r.status_code}')
                mime = r.headers.get('Content-Type','').split(';')[0]
                if mime not in ('text/html','text/plain','application/pdf'):
                    raise ImportFailure('Unsupported public web content type')
                suffix = {'text/html':'.html','text/plain':'.txt','application/pdf':'.pdf'}[mime]
                path = snap.put_stream('asset:' + original, r.iter_content(1024*1024), suffix,
                                       max_bytes=config.get('max_file_bytes', 20_000_000))
                if mime == 'text/html':
                    parser = Text(); parser.feed(path.read_text(errors='replace'))
                    snap.put('text:' + original, ''.join(parser.parts).encode(), '.txt', 'asset')
                snap.json('url:' + original, {'source_url': original, 'final_url': url,
                    'content_type': mime, 'path': str(path.relative_to(snap.path)),
                    'note': 'Public response only; login/paywall content is not bypassed'})
                break
        else:
            raise ImportFailure('Public URL redirect limit reached')
