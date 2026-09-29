#!/usr/bin/env python3
"""Server-owner metadata inventory: no tokens, message bodies or document contents."""
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import shutil


def read_json(path, boundary):
    path = path.resolve()
    if not path.is_relative_to(boundary.resolve()) or path.stat().st_size > 1_000_000:
        raise ValueError('Unsafe inventory input')
    return json.loads(path.read_text())


def collect(home_root):
    accounts = []
    for home in sorted(home_root.iterdir()):
        if home.is_symlink() or not home.is_dir():
            continue
        config_path = home / '.config/workspace/config.json'
        if not config_path.exists():
            continue
        try:
            cfg = read_json(config_path, home)
            data = Path(cfg['data_root']).resolve()
            if not data.is_relative_to(home.resolve()):
                raise ValueError('Data outside home')
            sources = []
            for name, source in cfg['sources'].items():
                if not name or '/' in name or name in ('.','..'):
                    raise ValueError('Invalid source name')
                current_path = data / name / 'current/COMPLETE.json'
                summary = read_json(current_path, home) if current_path.exists() else {}
                attempt_path = data / name / 'latest-attempt.json'
                attempt = read_json(attempt_path, home) if attempt_path.exists() else {}
                sources.append({'name':name, 'type':source.get('type'), 'enabled':bool(source.get('enabled')),
                    'configuration_sha256':hashlib.sha256(json.dumps(source,sort_keys=True).encode()).hexdigest(),
                    'completed_at':summary.get('completed_at'), 'records':summary.get('records'),
                    'bytes':summary.get('bytes'), 'latest_attempt_status':attempt.get('status'),
                    'run_id':summary.get('run_id')})
            accounts.append({'linux_user':home.name,'sources':sources})
        except (OSError, ValueError, KeyError, TypeError):
            accounts.append({'linux_user':home.name,'inventory_error':True})
    return accounts


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--home-root',type=Path,default=Path('/home'))
    p.add_argument('--output',type=Path)
    args=p.parse_args()
    os.umask(0o077)
    result={'generated_at':dt.datetime.now(dt.timezone.utc).isoformat(),
            'disk_free_bytes':shutil.disk_usage(args.home_root).free,
            'accounts':collect(args.home_root),
            'note':'Operational metadata from member-owned configuration/status files; not a tamper-proof audit.'}
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        if args.output.exists():
            previous=json.loads(args.output.read_text())
            old={(a['linux_user'],s['name']):s['configuration_sha256'] for a in previous['accounts'] for s in a.get('sources',[])}
            result['new_or_changed_sources']=[{'linux_user':a['linux_user'],'source':s['name']} for a in result['accounts'] for s in a.get('sources',[]) if old.get((a['linux_user'],s['name']))!=s['configuration_sha256']]
        text=json.dumps(result,indent=2)
        historical=args.output.with_name(dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S')+'.json')
        historical.write_text(text)
        temp=args.output.with_suffix('.part');temp.write_text(text);temp.replace(args.output)
        print('Owner inventory written; no source contents or credentials included.')
    else:
        print(json.dumps(result,indent=2))


if __name__=='__main__':
    main()
