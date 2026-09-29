"""Deterministic readable companions. Originals remain the source of truth."""
from pathlib import Path
import json
import subprocess
import xml.etree.ElementTree as ET
import zipfile


def google_doc_text(value):
    out = []
    def visit(node):
        if isinstance(node, list):
            for item in node:
                visit(item)
        elif isinstance(node, dict):
            if 'textRun' in node:
                out.append(node['textRun'].get('content', ''))
            for key, item in node.items():
                if key != 'textRun':
                    visit(item)
    visit(value)
    return ''.join(out)


def readable(path, mime):
    path = Path(path)
    if mime == 'application/vnd.google-apps.form':
        return json.dumps(json.loads(path.read_text()), ensure_ascii=False, indent=2)
    if mime == 'application/vnd.google-apps.document':
        return google_doc_text(json.loads(path.read_text()))
    if mime.startswith('text/') or mime in ('application/json', 'application/xml'):
        return path.read_text(errors='replace')
    if path.suffix in ('.docx', '.xlsx', '.pptx'):
        with zipfile.ZipFile(path) as z:
            members = [i for i in z.infolist() if i.filename.endswith('.xml') and
                       i.filename.startswith(('word/', 'xl/', 'ppt/slides/'))]
            if sum(i.file_size for i in members) > 100_000_000:
                return None
            return '\n'.join(' '.join(ET.fromstring(z.read(i)).itertext()) for i in members)
    if mime == 'application/pdf':
        result = subprocess.run(['pdftotext', str(path), '-'], capture_output=True, timeout=120)
        if result.returncode == 0:
            return result.stdout.decode(errors='replace')
    return None
