"""Read-only Salesforce export through an integration credential from the server owners."""
import json
from pathlib import Path
import re
from urllib.parse import urlparse
from .core import HTTP, ImportFailure

API = '/services/data/v62.0'
NAME = re.compile(r'^[A-Za-z][A-Za-z0-9_]*$')


class Salesforce:
    def __init__(self, config, http=None):
        path = Path(config.get('token_file', '~/.config/workspace/salesforce.json')).expanduser()
        cred = json.loads(path.read_text())
        self.base = cred['instance_url'].rstrip('/')
        parsed = urlparse(self.base)
        if parsed.scheme != 'https' or not (parsed.hostname or '').endswith(('.salesforce.com', '.force.com')):
            raise ImportFailure('Salesforce instance_url must be an https *.salesforce.com address')
        self.http = http or HTTP(min_interval=0.2)
        token = cred.get('access_token')
        if not token:
            # OAuth client-credentials flow: the credential file holds the connected app's key and secret.
            token = self.http.json('POST', self.base + '/services/oauth2/token', data={
                'grant_type': 'client_credentials', 'client_id': cred['client_id'],
                'client_secret': cred['client_secret']})['access_token']
        self.http.session.headers['Authorization'] = 'Bearer ' + token

    def get(self, path, params=None):
        if not path.startswith('/services/data/'):
            raise ImportFailure('Unexpected Salesforce API path')
        return self.http.json('GET', self.base + path, params=params)

    def objects(self):
        return [o['name'] for o in self.get(API + '/sobjects')['sobjects'] if o.get('queryable')]

    def fields(self, obj):
        # Compound address/location fields cannot be selected directly; their parts are.
        return [f['name'] for f in self.get(f'{API}/sobjects/{obj}/describe')['fields']
                if f.get('type') not in ('address', 'location')]

    def query(self, soql):
        result, seen = self.get(API + '/query', {'q': soql}), set()
        while True:
            yield from result['records']
            if result.get('done', True):
                return
            nxt = result.get('nextRecordsUrl')
            if not nxt or nxt in seen:
                raise ImportFailure('Salesforce pagination ended early: refusing incomplete export')
            seen.add(nxt)
            result = self.get(nxt)


def salesforce(config, snap, api=None):
    api = api or Salesforce(config)
    for obj in config['objects']:
        fields = config.get('fields', {}).get(obj) or api.fields(obj)
        if not NAME.match(obj) or not all(NAME.match(f) for f in fields):
            raise ImportFailure('Salesforce object and field names must be plain API names')
        where = config.get('where', {}).get(obj)
        soql = f"SELECT {', '.join(fields)} FROM {obj}" + (f' WHERE {where}' if where else '')
        count = 0
        for record in api.query(soql):
            record.pop('attributes', None)
            snap.json(f"{obj}:{record['Id']}", record)
            count += 1
        snap.json('object:' + obj, {'object': obj, 'fields': fields, 'where': where, 'records': count}, 'metadata')
    snap.json('scope', {'objects': config['objects'],
                        'note': 'Records visible to the integration user; files and attachments are not downloaded'}, 'metadata')
