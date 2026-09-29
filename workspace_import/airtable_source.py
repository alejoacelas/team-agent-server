"""Read-only Airtable export with a personal access token."""
import json
from pathlib import Path
from .core import HTTP, ImportFailure

API = 'https://api.airtable.com/v0'


class Airtable:
    def __init__(self, config, http=None):
        path = Path(config.get('token_file', '~/.config/workspace/airtable.json')).expanduser()
        token = json.loads(path.read_text())['token']
        # Airtable allows 5 requests per second per base.
        self.http = http or HTTP(headers={'Authorization': 'Bearer ' + token}, min_interval=0.25)

    def pages(self, url, field, params=None):
        params, seen = dict(params or {}), set()
        while True:
            data = self.http.json('GET', url, params=params)
            yield from data.get(field, [])
            offset = data.get('offset')
            if not offset:
                return
            if offset in seen:
                raise ImportFailure('Airtable repeated offset')
            seen.add(offset)
            params['offset'] = offset

    def bases(self):
        return list(self.pages(API + '/meta/bases', 'bases'))

    def tables(self, base):
        return self.http.json('GET', f'{API}/meta/bases/{base}/tables')['tables']


def airtable(config, snap, api=None):
    api = api or Airtable(config)
    wanted = config.get('table_ids')
    for base in config['base_ids']:
        for table in api.tables(base):
            if wanted and table['id'] not in wanted and table['name'] not in wanted:
                continue
            snap.json(f"table:{base}:{table['id']}", table, 'metadata')
            count = 0
            for record in api.pages(f"{API}/{base}/{table['id']}", 'records', {'pageSize': 100}):
                snap.json(f"{base}:{table['id']}:{record['id']}", {'table': table['name'], **record})
                count += 1
            snap.json(f"count:{base}:{table['id']}", {'table': table['name'], 'records': count}, 'metadata')
    snap.json('scope', {'base_ids': config['base_ids'], 'table_ids': wanted,
                        'note': 'Attachment files are listed by their temporary Airtable links, not downloaded'}, 'metadata')
