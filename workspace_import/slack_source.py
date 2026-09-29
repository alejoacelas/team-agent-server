import json
from pathlib import Path
import re
from urllib.parse import urlparse
from .core import HTTP, ImportFailure


class Slack:
    def __init__(self, config):
        path = Path(config.get('token_file', '~/.config/workspace/slack.json')).expanduser()
        token = json.loads(path.read_text())['access_token']
        self.http = HTTP(headers={'Authorization': 'Bearer ' + token}, min_interval=1.3)
        self.config = config
        who = self.call('auth.test')
        if who.get('team_id') != config['team_id'] or who.get('user_id') != config['user_id']:
            raise ImportFailure('Slack workspace/user mismatch')

    def call(self, method, **params):
        data = self.http.json('GET', 'https://slack.com/api/' + method, params=params)
        if not data.get('ok'):
            error = data.get('error', 'unknown')
            if not re.fullmatch('[a-z_]+', error):
                error = 'unknown'
            raise ImportFailure('Slack: ' + error)
        return data

    def pages(self, method, field, **params):
        cursor, seen = '', set()
        while True:
            data = self.call(method, cursor=cursor, **params)
            yield from data.get(field, [])
            cursor = data.get('response_metadata', {}).get('next_cursor', '').strip()
            if not cursor:
                if data.get('has_more'):
                    raise ImportFailure('Slack has_more without cursor: refusing incomplete export')
                return
            if cursor in seen:
                raise ImportFailure('Slack repeated cursor')
            seen.add(cursor)


def slack(config, snap, api=None):
    api = api or Slack(config)
    target = config.get('target_user', config['user_id'])
    seen = set()
    for channel in config['channel_ids']:
        api.call('conversations.info', channel=channel)
        for root in api.pages('conversations.history', 'messages', channel=channel, limit=100):
            ts = root.get('thread_ts', root['ts'])
            key = f'{channel}:{ts}'
            if key in seen:
                continue
            seen.add(key)
            messages = list(api.pages('conversations.replies', 'messages', channel=channel, ts=ts, limit=100)) if root.get('reply_count') or root.get('thread_ts') else [root]
            if config.get('mode', 'all') == 'participated' and not any(
                m.get('user') == target or f'<@{target}>' in m.get('text', '') for m in messages
            ):
                continue
            by_ts = {m['ts']: m for m in messages}
            if len(by_ts) != len(messages):
                raise ImportFailure('Slack duplicate thread timestamps')
            ordered = [by_ts[t] for t in sorted(by_ts)]
            assets = []
            for message in ordered:
                for item in message.get('files', []):
                    fid = item.get('id')
                    url = item.get('url_private_download') or item.get('url_private')
                    if not fid or not url or item.get('is_external'):
                        assets.append({'id': fid, 'downloaded': False, 'reason': 'External or inaccessible file'})
                        continue
                    parsed = urlparse(url)
                    if parsed.scheme != 'https' or parsed.hostname != 'files.slack.com':
                        raise ImportFailure('Slack file host not allowed; refusing to send token')
                    asset_key = 'file:' + fid
                    path = snap.cached(asset_key)
                    if path is None:
                        suffix = Path(item.get('name', '')).suffix.lower()
                        if not suffix or not suffix[1:].isalnum() or len(suffix) > 12:
                            suffix = '.bin'
                        with api.http.request('GET', url, stream=True) as response:
                            path = snap.put_stream(asset_key, response.iter_content(1024 * 1024), suffix,
                                max_bytes=config.get('max_file_bytes', 2_000_000_000))
                    assets.append({'id': fid, 'downloaded': True, 'path': str(path.relative_to(snap.path))})
            snap.json('thread:' + key, {'channel': channel, 'thread_ts': ts, 'messages': ordered,
                                      'files': assets})
            snap.put('text:' + key, '\n\n'.join(f"{m['ts']} {m.get('user', '')}\n{m.get('text', '')}" for m in ordered).encode(), '.txt', 'asset')
    snap.json('scope', {'channels': config['channel_ids'], 'mode': config.get('mode', 'all'),
                        'attachments': 'Accessible Slack-hosted files downloaded; external/inaccessible file omissions recorded in each thread',
                        'history': 'Only history visible to the app under Slack retention'}, 'metadata')
