from __future__ import annotations
import argparse
import datetime as dt
import json
import os
from pathlib import Path
import sys
from .core import ImportFailure, Snapshot, atomic, canonical, source_lock, slug, file_sha

CONFIG = Path.home() / '.config/workspace/config.json'
TOKEN = Path.home() / '.config/workspace/google.json'
SCOPES = ['openid', 'https://www.googleapis.com/auth/userinfo.email',
          'https://www.googleapis.com/auth/gmail.readonly',
          'https://www.googleapis.com/auth/calendar.readonly',
          'https://www.googleapis.com/auth/tasks.readonly',
          'https://www.googleapis.com/auth/drive.readonly',
          'https://www.googleapis.com/auth/documents.readonly']


def emit(value):
    print(json.dumps(value, indent=2, ensure_ascii=False))


def load(path):
    value = json.loads(Path(path).expanduser().read_text())
    if not isinstance(value, dict):
        raise ImportFailure('Expected JSON object')
    return value


def settings():
    if not CONFIG.exists():
        raise ImportFailure('Run workspace-import init --email your-work-email first')
    return load(CONFIG)


def init(email):
    import re
    if not re.fullmatch(r'[a-zA-Z0-9._+%-]+@[a-zA-Z0-9.-]+', email):
        raise ImportFailure('Invalid email identity')
    if CONFIG.exists():
        if settings()['email'] != email:
            raise ImportFailure('Existing workspace belongs to a different identity')
        emit({'status': 'already configured', 'email': email})
        return
    base = Path.home() / 'workspace'
    for sub in ('data', 'work', 'incoming', 'reports'):
        (base / sub).mkdir(parents=True, exist_ok=True, mode=0o700)
    common = {'expected_email': email, 'token_file': str(TOKEN)}
    sources = {
        'gmail': {**common, 'type': 'gmail', 'query': '', 'minimum': 0, 'enabled': False},
        'calendar': {**common, 'type': 'calendar', 'calendar_ids': ['primary'], 'minimum': 0, 'enabled': False},
        'tasks': {**common, 'type': 'tasks', 'minimum': 0, 'enabled': False},
        'drive': {**common, 'type': 'drive', 'root_ids': ['root'], 'minimum': 0, 'enabled': False},
    }
    atomic(CONFIG, canonical({'email': email, 'data_root': str(base / 'data'), 'sources': sources}))
    emit({'status': 'initialised', 'email': email, 'sources': list(sources), 'enabled': False})


PENDING = Path.home() / '.config/workspace/google-pending.json'
PENDING_SECONDS = 900


def connect_google(port, client):
    from google_auth_oauthlib.flow import InstalledAppFlow
    cfg = settings()
    flow = InstalledAppFlow.from_client_secrets_file(client, SCOPES, autogenerate_code_verifier=True)
    creds = flow.run_local_server(host='127.0.0.1', port=port, open_browser=False,
        timeout_seconds=900, prompt='consent', access_type='offline',
        login_hint=cfg['email'], authorization_prompt_message='Open this link in your LOCAL browser:\n{url}',
        success_message='Google connected. You can close this tab and return to your agent.')
    save_google(creds, cfg)


def pending_signins():
    # Every unexpired link stays valid, so an older browser tab can still finish.
    records = json.loads(PENDING.read_text()) if PENDING.exists() else {}
    now = dt.datetime.now(dt.timezone.utc)
    return {state: r for state, r in records.items() if isinstance(r, dict) and 'created' in r
            and (now - dt.datetime.fromisoformat(r['created'])).total_seconds() <= PENDING_SECONDS}


def start_google(port, client):
    # Browser sign-in without an SSH tunnel: the member pastes back the address the browser could not load.
    from google_auth_oauthlib.flow import Flow
    cfg = settings()
    flow = Flow.from_client_secrets_file(client, SCOPES, autogenerate_code_verifier=True,
                                         redirect_uri=f'http://127.0.0.1:{port}/')
    url, state = flow.authorization_url(prompt='consent', access_type='offline', login_hint=cfg['email'])
    records = pending_signins()
    records[state] = {'code_verifier': flow.code_verifier, 'port': port, 'client': client,
                      'created': dt.datetime.now(dt.timezone.utc).isoformat()}
    atomic(PENDING, canonical(records))
    emit({'status': 'waiting', 'email': cfg['email'], 'open_this_link': url,
          'next': 'Tell the member before they open the link: after approving, the browser shows "This site can\'t be reached. '
                  '127.0.0.1 refused to connect." That is expected; they copy the full address of that page and paste it back. '
                  'Pass it to connect-google --finish on stdin.'})


def finish_google(response):
    from urllib.parse import urlparse, parse_qs
    from google_auth_oauthlib.flow import Flow
    cfg = settings()
    records = pending_signins()
    if not records:
        raise ImportFailure('No unexpired sign-in: run connect-google --start again')
    response = response.strip()
    parsed = urlparse(response)
    query = parse_qs(parsed.query)
    if parsed.hostname != '127.0.0.1' or not parsed.port:
        raise ImportFailure('Paste the full address from the browser address bar after approving access')
    if 'error' in query:
        raise ImportFailure('Google sign-in was not approved: ' + query['error'][0])
    state = query.get('state', [''])[0]
    pending = records.get(state)
    if pending is None or parsed.port != pending['port'] or 'code' not in query:
        raise ImportFailure('Address does not match an unexpired sign-in (links last 15 minutes): run connect-google --start again')
    flow = Flow.from_client_secrets_file(pending['client'], SCOPES, state=state,
                                         redirect_uri=f"http://127.0.0.1:{pending['port']}/")
    flow.code_verifier = pending['code_verifier']
    # oauthlib requires an https response URI; the loopback redirect is registered as http.
    flow.fetch_token(authorization_response=response.replace('http://', 'https://', 1))
    records.pop(state)
    atomic(PENDING, canonical(records))
    save_google(flow.credentials, cfg)


def save_google(creds, cfg):
    from google.auth.transport.requests import AuthorizedSession
    from gdoc.util import account_context, token_path_for
    who = AuthorizedSession(creds).get('https://www.googleapis.com/oauth2/v2/userinfo', timeout=30)
    who.raise_for_status()
    if who.json().get('email', '').lower() != cfg['email'].lower():
        raise ImportFailure('Wrong Google identity: credentials not saved')
    if not creds.refresh_token:
        raise ImportFailure('No refresh token: reconnect with offline access')
    if not creds.has_scopes(SCOPES):
        raise ImportFailure('Required read-only scopes were not granted')
    payload = creds.to_json().encode()
    # Preserve any previous credential until an explicit rotation/retention review.
    if TOKEN.exists():
        atomic(TOKEN.with_name('google-before-' + dt.datetime.now().strftime('%Y%m%dT%H%M%S') + '.json'), TOKEN.read_bytes())
    atomic(TOKEN, payload)
    with account_context(cfg['email']):
        atomic(token_path_for(cfg['email']), payload)
    emit({'status': 'connected', 'email': cfg['email'], 'read_only': True})


EXA_KEY = Path(os.environ.get('WORKSPACE_EXA_KEY_FILE', '/etc/workspace/exa-key'))


def exa(path, payload):
    from .core import HTTP
    if not EXA_KEY.exists():
        raise ImportFailure('Web search is not set up: the server owners need to install an Exa API key')
    data = HTTP(headers={'x-api-key': EXA_KEY.read_text().strip()}).json('POST', 'https://api.exa.ai' + path, json=payload)
    keep = ('title', 'url', 'publishedDate', 'author', 'text')
    return {'results': [{k: r[k] for k in keep if r.get(k)} for r in data.get('results', [])],
            'cost_dollars': data.get('costDollars', {}).get('total')}


def source_config(name):
    cfg = settings()
    if name not in cfg['sources']:
        raise ImportFailure('Unknown source; use sources or configure')
    return cfg, cfg['sources'][name]


def run(name, resume=None, allow_drop=False):
    from .google_sources import gmail, calendar, tasks, drive
    from .slack_source import slack
    from .takeout import takeout
    from .web_source import web
    from .salesforce_source import salesforce
    from .airtable_source import airtable
    adapters = {'gmail': gmail, 'calendar': calendar, 'tasks': tasks, 'drive': drive,
                'slack': slack, 'takeout': takeout, 'web': web, 'salesforce': salesforce, 'airtable': airtable}
    cfg, source = source_config(name)
    if source['type'] not in adapters:
        raise ImportFailure('Unsupported source type')
    with source_lock(Path(cfg['data_root']) / slug(name)):
        snapshot = Snapshot(cfg['data_root'], name, source, resume)
        try:
            atomic(snapshot.base / "latest-attempt.json", canonical({"status": "incomplete", "run_id": snapshot.run_id, "started_at": dt.datetime.now(dt.timezone.utc).isoformat()}))
            emit({'source': name, 'run_id': snapshot.run_id, 'status': 'started'})
            adapters[source['type']](source, snapshot)
            result = snapshot.finish(minimum=source.get('minimum', 1), publish=True, allow_drop=allow_drop)
            atomic(snapshot.base / 'latest-attempt.json', canonical({'status': 'complete', **result}))
            emit({'source': name, **result})
        except Exception:
            atomic(snapshot.base / 'latest-attempt.json', canonical({'status': 'failed', 'run_id': snapshot.run_id,
                'note': 'Previous published generation is unchanged unless failure occurred after pointer switch. Check current/COMPLETE.json.'}))
            raise
        finally:
            snapshot.close()


def doctor():
    cfg = settings()
    checks = {'identity': cfg['email'], 'google_token': TOKEN.exists(),
              'private_home': Path.home().stat().st_mode & 0o077 == 0,
              'data_root': Path(cfg['data_root']).is_dir(), 'web_search': EXA_KEY.exists(), 'sources': {}}
    for name, source in cfg['sources'].items():
        checks['sources'][name] = {'enabled': source.get('enabled', False), 'type': source['type']}
    if TOKEN.exists():
        from .google_sources import google_http
        try:
            google_http({'token_file': str(TOKEN), 'expected_email': cfg['email']})
            checks['google_identity'] = 'verified'
        except Exception:
            checks['google_identity'] = 'failed: reconnect or check network/API access'
    emit(checks)


def discover(kind):
    cfg = settings()
    if kind in ('salesforce', 'airtable'):
        sources = [s for s in cfg['sources'].values() if s['type'] == kind]
        if kind == 'salesforce':
            from .salesforce_source import Salesforce
            emit(Salesforce(sources[0] if sources else {}).objects())
        else:
            from .airtable_source import Airtable
            api = Airtable(sources[0] if sources else {})
            emit([{**b, 'tables': [{'id': t['id'], 'name': t['name']} for t in api.tables(b['id'])]} for b in api.bases()])
        return
    if kind == 'slack':
        from .slack_source import Slack
        sources = [s for s in cfg['sources'].values() if s['type'] == 'slack']
        if not sources:
            raise ImportFailure('Configure Slack identity/token first; see the setup steps')
        api = Slack(sources[0])
        emit(list(api.pages('conversations.list', 'channels', types='public_channel,private_channel', limit=200)))
        return
    from .google_sources import google_http
    from .core import pages
    if kind == 'drive':
        import subprocess
        result = subprocess.run([sys.executable, str(Path(__file__).with_name('gdoc_bridge.py'))],
            input=json.dumps({'action': 'discover', 'account': cfg['email']}), text=True, capture_output=True)
        if result.returncode:
            raise ImportFailure('Drive discovery failed; check account access')
        print(result.stdout)
        return
    http = google_http({'token_file': str(TOKEN), 'expected_email': cfg['email']})
    if kind == 'calendar':
        emit(list(pages(http, 'https://www.googleapis.com/calendar/v3/users/me/calendarList')))
    else:
        emit(list(pages(http, 'https://tasks.googleapis.com/tasks/v1/users/@me/lists')))


def main():
    os.umask(0o077)
    sys.stdout.reconfigure(line_buffering=True)
    p = argparse.ArgumentParser(description='Private member imports. Cloud sources are read-only.')
    sub = p.add_subparsers(dest='command', required=True)
    a = sub.add_parser('init'); a.add_argument('--email', required=True)
    a = sub.add_parser('connect-google'); a.add_argument('--port', type=int, default=8765); a.add_argument('--client', default='/etc/workspace/google-client.json')
    mode = a.add_mutually_exclusive_group(); mode.add_argument('--start', action='store_true'); mode.add_argument('--finish', action='store_true', help='read the browser address from stdin')
    sub.add_parser('doctor'); sub.add_parser('sources'); sub.add_parser('status'); sub.add_parser('refresh')
    a = sub.add_parser('discover'); a.add_argument('kind', choices=['drive', 'calendar', 'tasks', 'slack', 'salesforce', 'airtable'])
    a = sub.add_parser('web-search', help='search the web with Exa; --linkedin restricts to LinkedIn profiles')
    a.add_argument('query'); a.add_argument('--linkedin', action='store_true')
    a.add_argument('--results', type=int, default=5); a.add_argument('--chars', type=int, default=2000)
    a = sub.add_parser('web-contents', help='fetch readable text of pages, including LinkedIn profiles, with Exa')
    a.add_argument('urls', nargs='+'); a.add_argument('--chars', type=int, default=10000)
    a = sub.add_parser('configure'); a.add_argument('name'); a.add_argument('--file', required=True)
    a = sub.add_parser('enable'); a.add_argument('name'); a.add_argument('--off', action='store_true')
    a = sub.add_parser('run'); a.add_argument('name'); a.add_argument('--resume'); a.add_argument('--allow-drop', action='store_true')
    a = sub.add_parser('verify'); a.add_argument('name')
    args = p.parse_args()
    try:
        if args.command == 'init':
            init(args.email)
        elif args.command == 'connect-google':
            if args.start:
                start_google(args.port, args.client)
            elif args.finish:
                finish_google(sys.stdin.read())
            else:
                connect_google(args.port, args.client)
        elif args.command == 'doctor':
            doctor()
        elif args.command == 'web-search':
            payload = {'query': args.query, 'numResults': args.results, 'contents': {'text': {'maxCharacters': args.chars}}}
            if args.linkedin:
                payload['category'] = 'linkedin profile'
            emit(exa('/search', payload))
        elif args.command == 'web-contents':
            emit(exa('/contents', {'urls': args.urls, 'text': {'maxCharacters': args.chars}}))
        elif args.command == 'discover':
            discover(args.kind)
        elif args.command == 'sources':
            emit(settings()['sources'])
        elif args.command == 'configure':
            cfg = settings(); name = slug(args.name); source = load(args.file)
            if source.get('type') not in ('gmail','calendar','tasks','drive','slack','takeout','web','salesforce','airtable'):
                raise ImportFailure('Unsupported source type')
            if any('secret' in k or k in ('access_token', 'refresh_token', 'password') for k in source):
                raise ImportFailure('Config must contain credential file paths, never credential values')
            source.setdefault('expected_email', cfg['email'])
            if source['expected_email'] != cfg['email']:
                raise ImportFailure('Source identity must match member identity')
            if source['type'] in ('gmail', 'calendar', 'tasks', 'drive'):
                source.setdefault('token_file', str(TOKEN))
            elif source['type'] == 'slack':
                source.setdefault('token_file', str(Path.home() / '.config/workspace/slack.json'))
            source.setdefault('enabled', False)
            cfg['sources'][name] = source
            atomic(CONFIG, canonical(cfg)); emit({'configured': name})
        elif args.command == 'enable':
            cfg, source = source_config(args.name); source['enabled'] = not args.off
            atomic(CONFIG, canonical(cfg)); emit({'source': args.name, 'enabled': source['enabled']})
        elif args.command == 'run':
            run(args.name, args.resume, args.allow_drop)
        elif args.command == 'refresh':
            failures = []
            for name, source in settings()['sources'].items():
                if source.get('enabled'):
                    try:
                        run(name)
                    except Exception:
                        failures.append(name)
            emit({'failed_sources': failures})
            if failures:
                return 1
        elif args.command == 'status':
            cfg = settings(); results = {}
            for name in cfg['sources']:
                base = Path(cfg['data_root']) / slug(name)
                results[name] = {k: load(base / f) if (base / f).exists() else None for k,f in
                                 [('current','current/COMPLETE.json'), ('last_attempt','latest-attempt.json')]}
            emit(results)
        elif args.command == 'verify':
            import sqlite3
            cfg, _ = source_config(args.name)
            base = Path(cfg['data_root']) / slug(args.name) / 'current'
            if not (base / 'COMPLETE.json').exists():
                raise ImportFailure('No completed current generation')
            with sqlite3.connect(f'file:{base / "manifest.sqlite"}?mode=ro', uri=True) as db:
                rows = list(db.execute('SELECT path,sha256,size FROM objects'))
            for rel, digest, size in rows:
                path = base / rel
                if not path.is_file() or path.stat().st_size != size or file_sha(path) != digest:
                    raise ImportFailure('Integrity verification failed')
            emit({'status': 'verified', 'objects': len(rows), 'source': args.name})
        return 0
    except Exception as exc:
        # Known errors are controlled; provider/transport exceptions can contain secrets or content.
        message = str(exc) if isinstance(exc, ImportFailure) else type(exc).__name__ + ': operation failed; check credentials/configuration and retry'
        print(message, file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
