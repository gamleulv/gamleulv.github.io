#!/usr/bin/env python3
import base64
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path('/Users/einar/Documents/GitHub/gamleulv.github.io')
TOOLS = REPO / '.site-tools'
GENERATOR = TOOLS / 'generate_site.py'
SOURCE_DIR = Path.home() / 'Documents' / 'Privat-kilde' / 'Solvi-Einar'
SOURCE_HTML = SOURCE_DIR / 'search.html'
SOURCE_JSON = SOURCE_DIR / 'search-index.json'
OUTPUT_HTML = REPO / 'Privat' / 'Solvi-Einar' / 'search.html'
SECRET_FILE = Path.home() / 'Documents' / '.gamleulv-secret' / 'privat-secret.txt'


def fail(message):
    print('STOPP:', message, file=sys.stderr)
    raise SystemExit(1)


def git_output(*args):
    return subprocess.run(['git', '-C', str(REPO), *args], text=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          check=True).stdout

for path in (GENERATOR, SOURCE_HTML, SOURCE_JSON, OUTPUT_HTML, SECRET_FILE):
    if not path.exists():
        fail(f'Mangler fil: {path}')

if git_output('status', '--porcelain', '--', 'Privat').strip():
    fail('Privat har lokale endringer eller usporede filer. Rydd først.')

password = SECRET_FILE.read_text(encoding='utf-8').strip()
if not password:
    fail('Passordfilen er tom.')

spec = importlib.util.spec_from_file_location('gamleulv_generator', GENERATOR)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

source_text = SOURCE_HTML.read_text(encoding='utf-8')
index_data = json.loads(SOURCE_JSON.read_text(encoding='utf-8'))
if not isinstance(index_data, list):
    fail('search-index.json er ikke en JSON-liste.')

old_fetch = "fetch('search-index.json')"
if old_fetch not in source_text:
    fail(f'Fant ikke {old_fetch} i kildesiden.')

history_line = "history.replaceState(null, '', url);"
if history_line not in source_text:
    fail('Fant ikke history.replaceState-linjen i kildesiden.')

search_json_bytes = json.dumps(index_data, ensure_ascii=False).encode('utf-8')
embedded_b64 = base64.b64encode(search_json_bytes).decode('ascii')
marker = (
    "<script>window.__PRIVATE_SEARCH_DATA__=JSON.parse("
    "new TextDecoder('utf-8').decode("
    "Uint8Array.from(atob('" + embedded_b64 + "'),c=>c.charCodeAt(0))"
    "));</script>"
)
if not re.search(r'</head>', source_text, flags=re.IGNORECASE):
    fail('Kildesiden mangler </head>.')
source_text = re.sub(r'</head>', marker + '</head>', source_text,
                     count=1, flags=re.IGNORECASE)
source_text = source_text.replace(
    old_fetch,
    "Promise.resolve({ok:true,json:()=>Promise.resolve(window.__PRIVATE_SEARCH_DATA__)})",
    1,
)
source_text = source_text.replace(
    history_line,
    "try { history.replaceState(null, '', url); } catch (e) { /* srcdoc: ignore */ }",
    1,
)

payload = module.aes.encrypt_for_browser(source_text.encode('utf-8'), password)
page = module.gate_page_shell('search', payload, 'html', {}, module.RENDER_JS_HTML)

backup = OUTPUT_HTML.with_name('search.html.before-targeted-fix')
backup.write_bytes(OUTPUT_HTML.read_bytes())

fd, temp_name = tempfile.mkstemp(prefix='search.', suffix='.html', dir=str(OUTPUT_HTML.parent))
os.close(fd)
temp = Path(temp_name)
try:
    temp.write_text(page, encoding='utf-8')
    if '"ciphertext"' not in temp.read_text(encoding='utf-8'):
        fail('Den nye siden ser ikke kryptert ut.')
    os.replace(temp, OUTPUT_HTML)
finally:
    if temp.exists():
        temp.unlink()

changed = git_output('diff', '--name-only', '--', 'Privat').splitlines()
untracked = git_output('ls-files', '--others', '--exclude-standard', '--', 'Privat').splitlines()
allowed_changed = {'Privat/Solvi-Einar/search.html'}
unexpected_changed = set(changed) - allowed_changed
unexpected_untracked = [p for p in untracked if p != 'Privat/Solvi-Einar/search.html.before-targeted-fix']
if unexpected_changed or unexpected_untracked:
    fail('Uventede Privat-endringer: ' + ', '.join(sorted(unexpected_changed) + unexpected_untracked))

print(f'OK: Bygget kun {OUTPUT_HTML.relative_to(REPO)}')
print(f'OK: Innebygde {len(index_data)} søkeoppføringer')
print(f'Sikkerhetskopi: {backup}')
