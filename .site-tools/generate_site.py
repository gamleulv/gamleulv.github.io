#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
generate_site.py — static-site generator for gamleulv.github.io

Regenerates every index.html (root + all subfolders), a site-wide search
index, sitemap.xml and rss.xml, disables Jekyll processing, and rebuilds
the password-protected "Privat" section — WITHOUT EVER MODIFYING any of
the user's own content files (HTML forms, email templates, documents).

Run with no arguments; paths are configured below. Designed to be called
from auto-publish.sh on every publish.
"""
import base64
import html
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import aes  # local module, same folder

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

REPO = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/Users/einar/Documents/GitHub/gamleulv.github.io")
BASE_URL = "https://gamleulv.github.io"
SITE_TITLE = "gamleulv.github.io"

PRIVAT_DIR_NAME = "Privat"
PRIVAT_OUTPUT = REPO / PRIVAT_DIR_NAME
# Real private files live OUTSIDE the git repo so plaintext can never be
# committed/pushed by accident. This is what makes the password real
# protection instead of theatre.
PRIVAT_SOURCE = Path.home() / "Documents" / "Privat-kilde"
PRIVAT_SECRET_FILE = Path.home() / "Documents" / ".gamleulv-secret" / "privat-secret.txt"

# A handful of iMessage video attachments exceed GitHub's 100MB per-file hard
# push limit (unrelated to overall push size, and separate from the total-size
# limit already worked around by squashing history). Re-encoding them through
# Git LFS was rejected in favor of hosting the raw files externally (with the
# user's explicit approval) and keeping only a small, still password-gated
# "open externally" card in the repo - so the encrypted git history never
# carries the actual video bytes for these. Keyed by source filename as found
# directly under PRIVAT_SOURCE (media/ subfolder for this particular archive).
EXTERNAL_MEDIA_LINKS = {
    "imessage_1784207921000_1_2026-07-16-15-18-41-1.MOV": {
        "url": "https://ef.smmall.cloud/l/1784207921000_1_2026-07-16-15-18-41-1mp4",
        "thumb": "thumb_imessage_1784207921000_1_zdmthmbh0iiNVHb7huC50dKd_v21785683318316.jpg",
        "size_label": "1,6 GB",
    },
    "imessage_1775311710000_1_2026-04-04-16-08-30.mp4": {
        "url": "https://ef.smmall.cloud/l/1775311710000_1_2026-04-04-16-08-30mp4",
        "thumb": "thumb_imessage_1775311710000_1_zdmthmbhwJEcu3DEX6S3TsjM_v21777388392879.jpg",
        "size_label": "80,8 MB",
    },
    "imessage_1783958893000_1_2026-07-13-18-08-13.MOV": {
        "url": "https://ef.smmall.cloud/l/1783958893000_1_2026-07-13-18-08-13mp4",
        "thumb": "thumb_imessage_1783958893000_1_zdmthmbhEa0kZGb6nPTadOXb_v21785683318160.jpg",
        "size_label": "79,6 MB",
    },
}

# Dirs hidden from every listing/card entirely (never shown, never recursed).
HIDDEN_DIR_NAMES = {".git", ".site-tools", "node_modules"}
# Dirs that ARE shown as normal folder cards, but whose real content must never
# be walked, indexed, or listed as "recent" - Privat is rendered exclusively
# through its own encrypted gate pages (see encrypt_privat), never through the
# ordinary folder-index / search-index / recent-files code paths.
SKIP_CONTENT_DIR_NAMES = HIDDEN_DIR_NAMES | {PRIVAT_DIR_NAME}
# Back-compat alias used by a couple of content-scanning helpers below.
EXCLUDE_DIR_NAMES = SKIP_CONTENT_DIR_NAMES
EXCLUDE_FILE_NAMES = {".DS_Store", "index.html", "sitemap.xml", "rss.xml", "search-index.json", ".nojekyll", "README.md", "auto-publish.sh", "auto-publish-watcher.sh", ".gitignore", "publish.log", ".paused"}
# Any file whose extension is in here is treated as pipeline infrastructure,
# never as user content - never listed, never searchable, never downloadable.
EXCLUDE_FILE_EXTS = {".bak", ".lock", ".pyc"}

DOC_EXTS = {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".txt", ".pages", ".numbers", ".key"}
IMG_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
LISTED_EXTS = {".html"} | DOC_EXTS | IMG_EXTS

ICONS = {
    ".html": "📄", ".pdf": "📕", ".doc": "📝", ".docx": "📝",
    ".xls": "📊", ".xlsx": "📊", ".ppt": "📈", ".pptx": "📈",
    ".txt": "📄", ".pages": "📘", ".numbers": "📗", ".key": "📙",
    ".jpg": "🖼️", ".jpeg": "🖼️", ".png": "🖼️", ".webp": "🖼️", ".gif": "🖼️",
}

BREADCRUMB_MARK = "data-breadcrumb-auto"  # marker used by the OLD, retired bash injector

LOG = []
def log(msg):
    LOG.append(msg)
    print(msg)

# ---------------------------------------------------------------------------
# One-time repair pass: strip legacy corruption from ALL content files.
#
# The previous publishing script injected a <script data-breadcrumb-auto>
# block before every literal "</head>" it found via a dumb text search -
# including occurrences that were sitting inside OTHER scripts' JS string
# literals (e.g. the "save as HTML/PDF" export builders used by the
# psychometric forms). That injected a stray "</script>" into the middle of
# those template strings, which made the browser's HTML parser think the
# page's own <script> block ended early - everything after was then dumped
# onto the page as plain text instead of running as code. That's exactly
# the "form is incomplete, code visible at the bottom" bug.
#
# This function removes every instance of that injected block, wherever it
# landed, from every .html file - restoring the files to their original,
# working state. It is idempotent and safe to run on every publish.
# ---------------------------------------------------------------------------

BREADCRUMB_BLOCK_RE = re.compile(
    r"<script[^>]*\bdata-breadcrumb-auto\b[^>]*>.*?</script>\s*",
    re.DOTALL | re.IGNORECASE,
)
LEGACY_DEBUG_LINE_RE = re.compile(r"^(TITLE=|ICON=).*$\n?|^.*SUBIMG=.*$\n?", re.MULTILINE)

def repair_legacy_corruption(repo: Path):
    fixed = 0
    for path in repo.rglob("*.html"):
        if any(part in EXCLUDE_DIR_NAMES for part in path.relative_to(repo).parts[:-1]):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="surrogateescape")
        except Exception:
            continue
        new_text = BREADCRUMB_BLOCK_RE.sub("", text)
        if new_text != text:
            path.write_text(new_text, encoding="utf-8", errors="surrogateescape")
            fixed += 1
    if fixed:
        log(f"Reparerte {fixed} HTML-fil(er) for gammel skade (fjernet injisert skript).")

# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def icon_for(name: str) -> str:
    return ICONS.get(Path(name).suffix.lower(), "📦")

def is_doc(name: str) -> bool:
    return Path(name).suffix.lower() in DOC_EXTS

def human_size(n: int) -> str:
    for unit in ["B", "KB", "MB", "GB"]:
        if n < 1024:
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"

def title_from_filename(name: str) -> str:
    stem = Path(name).stem
    return re.sub(r"[-_]+", " ", stem).strip()

_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_SCRIPT_STYLE_RE = re.compile(r"<(script|style)\b[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")

def extract_html_meta(path: Path):
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return title_from_filename(path.name), ""
    m = _TITLE_RE.search(text)
    title = html.unescape(_TAG_RE.sub("", m.group(1))).strip() if m else ""
    if not title:
        title = title_from_filename(path.name)
    body = _SCRIPT_STYLE_RE.sub(" ", text)
    body = _TAG_RE.sub(" ", body)
    body = html.unescape(body)
    body = _WS_RE.sub(" ", body).strip()
    return title, body[:700]

def rel_url(repo_rel_path: str) -> str:
    """Root-absolute URL path for a file relative to repo root (POSIX slashes, URL-quoted per segment)."""
    from urllib.parse import quote
    parts = [quote(p) for p in Path(repo_rel_path).parts]
    return "/" + "/".join(parts)

def cleanup_stray_thumbnails(repo: Path):
    """Folder cards no longer show an image preview, so the thumb_*.png/jpg
    helper files generated for that feature are dead weight now - remove them."""
    for p in repo.rglob("thumb_*"):
        if p.is_file() and p.suffix.lower() in IMG_EXTS:
            try:
                p.unlink()
            except Exception:
                pass

# ---------------------------------------------------------------------------
# Shared page chrome (CSS + JS) - identical on every generated page
# ---------------------------------------------------------------------------

BASE_CSS = """
:root {
  --bg: #eef2ff; --bg-card: #f8f9ff; --text: #111; --text-muted: #5a5f73;
  --accent: #0044aa; --accent-strong:#00298f; --border: #d7dbee; --radius: 16px;
}
[data-theme="dark"] {
  --bg: #0f172a; --bg-card: #1b2436; --text: #e7e9f0; --text-muted: #98a0b8;
  --accent: #7fb1ff; --accent-strong:#a9cbff; --border: #2c3752;
}
* { box-sizing: border-box; }
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif;
  background: var(--bg); color: var(--text); margin: 0; padding: 16px;
  line-height: 1.45; -webkit-text-size-adjust: 100%;
}
.container { max-width: 1100px; margin: auto; background: var(--bg-card);
  padding: 20px; border-radius: var(--radius); box-shadow: 0 0 30px rgba(0,0,0,0.10); }
h1 { font-size: clamp(22px, 5vw, 30px); margin: 6px 0 8px; }
h3 { font-size: 17px; margin: 22px 0 8px; }
a { color: var(--accent); text-decoration: none; word-break: break-word; }
a:hover { text-decoration: underline; }
.topbar { display:flex; justify-content:space-between; align-items:center; gap:10px; flex-wrap:wrap; margin-bottom: 6px;}
.home-link { font-weight:600; font-size:15px; }
.theme-toggle button, .btn {
  padding: 7px 14px; border-radius: 999px; border: 1px solid var(--border);
  background: transparent; color: var(--text); cursor: pointer; font-size: 13px;
}
.breadcrumb { font-size: 13px; color: var(--text-muted); margin: 6px 0 16px; line-height:1.8; display:flex; flex-wrap:wrap; align-items:center; gap:6px; }
.breadcrumb a { margin-right:2px; }
.breadcrumb .back-link { margin-left:auto; padding:5px 12px; border:1px solid var(--border); border-radius:999px; background:transparent; color:var(--text); text-decoration:none; font-weight:600; cursor:pointer; }
.breadcrumb .back-link:hover { border-color: var(--primary); color: var(--primary); }
.search-wrap { margin: 14px 0 20px; position: relative; }
.search-wrap input {
  width: 100%; padding: 12px 14px; border-radius: 12px; border: 1px solid var(--border);
  font-size: 16px; background: var(--bg); color: var(--text);
}
#searchResults { margin-top: 8px; border-radius: 12px; overflow: hidden; }
#searchResults .res { display:block; padding: 10px 12px; border-bottom: 1px solid var(--border); background: var(--bg); }
#searchResults .res small { display:block; color: var(--text-muted); }
ul.filelist { list-style: none; padding: 0; margin: 6px 0 0; }
ul.filelist li { display:flex; align-items:center; gap:8px; padding: 9px 4px; border-bottom: 1px solid var(--border); flex-wrap: wrap;}
ul.filelist li .name { flex: 1 1 auto; min-width: 140px; }
.dl-btn { flex: 0 0 auto; font-size: 12px; padding: 5px 10px; border-radius: 999px;
  border: 1px solid var(--border); background: var(--bg); color: var(--text-muted); }
.dl-btn:hover { color: var(--accent); border-color: var(--accent); text-decoration:none; }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(230px, 1fr)); gap: 14px; margin-top: 14px; }
.card { background: var(--bg); border: 1px solid var(--border); border-radius: 14px; padding: 14px; }
.card-title { font-size: 17px; font-weight: 600; margin-bottom: 4px; display:flex; align-items:center; gap:6px;}
.card-meta { font-size: 12px; color: var(--text-muted); }
.recent-list { list-style:none; padding:0; margin: 8px 0 0; }
.recent-list li { padding: 8px 0; border-bottom: 1px solid var(--border); display:flex; justify-content:space-between; gap:10px; flex-wrap:wrap;}
.recent-list .date { color: var(--text-muted); font-size: 13px; }
.footer { margin-top: 26px; font-size: 12px; color: var(--text-muted); text-align:center; }
.locked-badge { font-size:12px; color:var(--text-muted); }
@media (max-width: 600px) {
  body { padding: 8px; }
  .container { padding: 14px; border-radius: 12px; }
  ul.filelist li { font-size: 15px; }
  .grid { grid-template-columns: 1fr; }
}
"""

# Shared light/dark theme logic. Previously this only lived inside BASE_JS,
# which is included on regular pages via page_shell() but NOT on password
# gate pages (gate_page_shell() has its own, separate <script> block). That
# left every gate page rendering a theme-toggle button whose onclick handler
# called a toggleTheme() function that was never defined there, so clicking
# it did nothing (silently threw a ReferenceError) on every Privat page.
# Defining it once here and including it in BOTH shells fixes that for all
# pages, gated or not.
THEME_JS = """
function setTheme(t){document.documentElement.setAttribute('data-theme',t);localStorage.setItem('site-theme',t);}
function toggleTheme(){const c=document.documentElement.getAttribute('data-theme')||'light';setTheme(c==='light'?'dark':'light');}
function readStoredTheme(){return localStorage.getItem('site-theme')||'light';}
document.addEventListener('DOMContentLoaded',function(){setTheme(readStoredTheme());});
"""

BASE_JS = THEME_JS + """
document.addEventListener('DOMContentLoaded',function(){initSearch();});

let SEARCH_INDEX = null;
async function loadSearchIndex(){
  if (SEARCH_INDEX) return SEARCH_INDEX;
  try {
    const res = await fetch('/search-index.json');
    SEARCH_INDEX = await res.json();
  } catch(e) { SEARCH_INDEX = []; }
  return SEARCH_INDEX;
}
function scoreMatch(entry, q){
  const hay = (entry.name+' '+entry.dir+' '+entry.title+' '+entry.snippet).toLowerCase();
  return hay.includes(q) ? (entry.name.toLowerCase().includes(q) ? 2 : 1) : 0;
}
async function runSearch(q){
  const box = document.getElementById('searchResults');
  if (!box) return;
  q = q.trim().toLowerCase();
  if (q.length < 2) { box.innerHTML=''; return; }
  const idx = await loadSearchIndex();
  const hits = idx.map(e=>({e,s:scoreMatch(e,q)})).filter(x=>x.s>0)
    .sort((a,b)=>b.s-a.s).slice(0,40);
  if (!hits.length) { box.innerHTML = '<div class="res">Ingen treff.</div>'; return; }
  box.innerHTML = hits.map(({e})=>{
    const snip = e.snippet ? e.snippet.slice(0,140)+'…' : '';
    return `<a class="res" href="${e.href}"><strong>${e.icon||'📄'} ${e.title}</strong><small>${e.dir}</small>${snip?('<small>'+snip+'</small>'):''}</a>`;
  }).join('');
}
function initSearch(){
  const input = document.getElementById('searchInput');
  if (!input) return;
  let t;
  input.addEventListener('input', ()=>{ clearTimeout(t); t=setTimeout(()=>runSearch(input.value), 120); });
}
"""

def page_shell(title: str, body_html: str, extra_head: str = "") -> str:
    return f"""<!DOCTYPE html>
<html lang="no">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<style>{BASE_CSS}</style>
{extra_head}
</head>
<body>
<div class="container">
{body_html}
</div>
<script>{BASE_JS}</script>
</body>
</html>"""

def render_breadcrumb(rel_parts):
    crumbs = ['<a href="/index.html">🏠 Hjem</a>']
    acc = ""
    for part in rel_parts:
        acc += "/" + part
        crumbs.append(f'<a href="{acc}/index.html">{html.escape(part)}</a>')
    return '<div class="breadcrumb">' + " / ".join(crumbs) + "</div>"

def render_search_box():
    return ('<div class="search-wrap">'
            '<input id="searchInput" type="text" placeholder="🔎 Søk i hele nettstedet – mappe, fil eller innhold…" autocomplete="off">'
            '<div id="searchResults"></div></div>')

def theme_toggle():
    return '<div class="theme-toggle"><button onclick="toggleTheme()">☀️/🌙</button></div>'

# ---------------------------------------------------------------------------
# Folder tree generation
# ---------------------------------------------------------------------------

def list_dir_entries(dir_path: Path):
    files, dirs = [], []
    for p in sorted(dir_path.iterdir(), key=lambda x: x.name.casefold()):
        if p.name in EXCLUDE_FILE_NAMES or p.name.startswith("thumb_"):
            continue
        if p.is_dir():
            if p.name in HIDDEN_DIR_NAMES or p.name.startswith("."):
                continue
            dirs.append(p)
        else:
            if p.name.startswith(".") or p.name.startswith("_") or p.suffix.lower() in EXCLUDE_FILE_EXTS:
                continue
            files.append(p)
    return files, dirs

def render_file_row(f: Path, rel_dir: str):
    href = rel_url(str(Path(rel_dir) / f.name)) if rel_dir else rel_url(f.name)
    icon = icon_for(f.name)
    title = extract_html_meta(f)[0] if f.suffix.lower() == ".html" else f.name
    dl_name = f.name
    return (f'<li><span class="name">{icon} <a href="{href}">{html.escape(title)}</a></span>'
            f'<a class="dl-btn" href="{href}" download="{html.escape(dl_name)}">⬇ Last ned</a></li>')

def render_folder_card(d: Path, rel_dir: str):
    rel = str(Path(rel_dir) / d.name) if rel_dir else d.name
    href = rel_url(rel) + "/index.html"
    if d.name == PRIVAT_DIR_NAME:
        # Never peek inside Privat's real content here - it is rendered
        # exclusively through its own encrypted gate pages.
        return (f'<div class="card"><div class="card-title">🔒 <a href="{href}">{html.escape(d.name)}</a></div>'
                f'<div class="card-meta locked-badge">Passordbeskyttet innhold</div></div>')
    files, subdirs = list_dir_entries(d)
    count_txt = f"{len(files)} fil(er)" + (f", {len(subdirs)} undermappe(r)" if subdirs else "")
    return (f'<div class="card"><div class="card-title">📁 <a href="{href}">{html.escape(d.name)}</a></div>'
            f'<div class="card-meta">{count_txt}</div></div>')

def generate_folder_index(repo: Path, dir_path: Path, is_root: bool, recent_html: str = ""):
    rel_dir = "" if dir_path == repo else str(dir_path.relative_to(repo))
    files, dirs = list_dir_entries(dir_path)
    rel_parts = [] if is_root else Path(rel_dir).parts

    body = [theme_toggle()]
    if is_root:
        body.append(f'<h1>{html.escape(SITE_TITLE)}</h1>')
    else:
        body.append(f'<h1>📁 {html.escape(dir_path.name)}</h1>')
        body.append(render_breadcrumb(list(rel_parts)))
    body.append(render_search_box())

    if is_root and recent_html:
        body.append("<h3>Nyeste endringer</h3>")
        body.append(f'<ul class="recent-list">{recent_html}</ul>')

    if files:
        body.append("<h3>Filer i denne mappen</h3><ul class=\"filelist\">")
        for f in files:
            body.append(render_file_row(f, rel_dir))
        body.append("</ul>")

    if dirs:
        body.append("<h3>Mapper</h3><div class=\"grid\">")
        for d in dirs:
            body.append(render_folder_card(d, rel_dir))
        body.append("</div>")

    if not is_root:
        parent_href = "/" + "/".join(rel_parts[:-1]) + "/index.html" if len(rel_parts) > 1 else "/index.html"
        body.append(f'<p style="margin-top:26px;"><a href="{parent_href}">⬅ Tilbake</a></p>')

    body.append(f'<div class="footer">Sist oppdatert: {time.strftime("%Y-%m-%d %H:%M")}</div>')

    title = SITE_TITLE if is_root else f"{dir_path.name} – {SITE_TITLE}"
    html_out = page_shell(title, "\n".join(body))
    (dir_path / "index.html").write_text(html_out, encoding="utf-8")

def walk_and_generate(repo: Path):
    all_dirs = [repo]
    for p in repo.rglob("*"):
        if p.is_dir():
            if any(part in EXCLUDE_DIR_NAMES or part.startswith(".") for part in p.relative_to(repo).parts):
                continue
            all_dirs.append(p)

    recent = collect_recent_files(repo, limit=10)
    recent_html = "".join(
        f'<li>📅 <a href="{rel_url(rel)}">{html.escape(rel)}</a><span class="date">{ts_str}</span></li>'
        for rel, ts_str in recent
    )

    for d in all_dirs:
        generate_folder_index(repo, d, is_root=(d == repo), recent_html=recent_html if d == repo else "")
    log(f"Genererte index.html for {len(all_dirs)} mapper.")

def collect_recent_files(repo: Path, limit=10):
    items = []
    for p in repo.rglob("*.html"):
        rel_parts = p.relative_to(repo).parts
        if any(part in EXCLUDE_DIR_NAMES or part.startswith(".") for part in rel_parts[:-1]):
            continue
        if p.name == "index.html":
            continue
        try:
            mtime = p.stat().st_mtime
        except OSError:
            continue
        items.append((str(p.relative_to(repo)), mtime))
    items.sort(key=lambda x: x[1], reverse=True)
    return [(rel, time.strftime("%Y-%m-%d %H:%M", time.localtime(mtime))) for rel, mtime in items[:limit]]

# ---------------------------------------------------------------------------
# Search index, sitemap, rss
# ---------------------------------------------------------------------------

def build_search_index(repo: Path):
    entries = []
    for p in repo.rglob("*"):
        if p.is_dir():
            continue
        rel_parts = p.relative_to(repo).parts
        if any(part in EXCLUDE_DIR_NAMES or part.startswith(".") for part in rel_parts[:-1]):
            continue
        if p.name in EXCLUDE_FILE_NAMES or p.name.startswith(".") or p.name.startswith("thumb_") or p.name.startswith("_") or p.suffix.lower() in EXCLUDE_FILE_EXTS:
            continue
        rel = str(p.relative_to(repo))
        rel_dir = str(Path(rel).parent) if Path(rel).parent != Path(".") else "/"
        if p.suffix.lower() == ".html":
            title, snippet = extract_html_meta(p)
        else:
            title, snippet = p.name, ""
        entries.append({
            "name": p.name, "dir": rel_dir, "title": title, "snippet": snippet,
            "href": rel_url(rel), "icon": icon_for(p.name),
        })
    (repo / "search-index.json").write_text(json.dumps(entries, ensure_ascii=False), encoding="utf-8")
    log(f"Bygget søkeindeks med {len(entries)} oppføringer (Privat er ikke inkludert).")

def build_sitemap_rss(repo: Path, recent):
    urls = []
    for p in repo.rglob("*.html"):
        rel_parts = p.relative_to(repo).parts
        if any(part in EXCLUDE_DIR_NAMES or part.startswith(".") for part in rel_parts[:-1]):
            continue
        rel = str(p.relative_to(repo))
        mod = time.strftime("%Y-%m-%d", time.localtime(p.stat().st_mtime))
        urls.append(f"<url><loc>{BASE_URL}{rel_url(rel)}</loc><lastmod>{mod}</lastmod></url>")
    sitemap = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + "\n".join(urls) + "\n</urlset>"
    (repo / "sitemap.xml").write_text(sitemap, encoding="utf-8")

    items = []
    for rel, ts in recent:
        items.append(f"<item><title>{html.escape(rel)}</title><link>{BASE_URL}{rel_url(rel)}</link><pubDate>{ts}</pubDate></item>")
    rss = ('<?xml version="1.0" encoding="UTF-8"?>\n<rss version="2.0"><channel>'
           f'<title>{SITE_TITLE}</title><link>{BASE_URL}/</link>'
           '<description>Automatisk generert feed</description>' + "".join(items) + "</channel></rss>")
    (repo / "rss.xml").write_text(rss, encoding="utf-8")

# ---------------------------------------------------------------------------
# Privat: client-side AES-256 password gate (real files kept outside git)
# ---------------------------------------------------------------------------

GATE_CSS = BASE_CSS + """
.gate-box{max-width:380px;margin:60px auto;text-align:center;}
.gate-box input{width:100%;padding:12px;border-radius:10px;border:1px solid var(--border);font-size:16px;margin-bottom:10px;background:var(--bg);color:var(--text);}
.gate-box button{width:100%;padding:12px;border-radius:10px;border:none;background:var(--accent);color:#fff;font-size:15px;cursor:pointer;}
.gate-err{color:#c0392b;font-size:13px;margin-top:8px;min-height:18px;}
#gateContent{display:none;}
iframe.gate-frame{width:100%;height:80vh;border:0;border-radius:12px;background:#fff;}
"""

GATE_JS_LIB = THEME_JS + """
function b64ToBytes(b64){const bin=atob(b64);const a=new Uint8Array(bin.length);for(let i=0;i<bin.length;i++)a[i]=bin.charCodeAt(i);return a;}
async function derivePrivatKey(pw, saltB64, iterations){
  const salt = b64ToBytes(saltB64);
  const enc = new TextEncoder();
  const baseKey = await crypto.subtle.importKey('raw', enc.encode(pw), 'PBKDF2', false, ['deriveKey']);
  return crypto.subtle.deriveKey({name:'PBKDF2', salt, iterations, hash:'SHA-256'}, baseKey, {name:'AES-CBC', length:256}, false, ['decrypt']);
}
async function decryptPrivatPayload(payload, pw){
  const key = await derivePrivatKey(pw, payload.salt, payload.iterations);
  const iv = b64ToBytes(payload.iv);
  const ct = b64ToBytes(payload.ciphertext);
  const buf = await crypto.subtle.decrypt({name:'AES-CBC', iv}, key, ct);
  return new Uint8Array(buf);
}
function pwStorageKey(){ return 'privatPw'; }
async function attemptUnlock(pw, onSuccess, onError){
  try{
    const bytes = await decryptPrivatPayload(PAYLOAD, pw);
    sessionStorage.setItem(pwStorageKey(), pw);
    onSuccess(bytes, pw);
  }catch(e){ onError(); }
}
document.addEventListener('DOMContentLoaded', function(){
  const saved = sessionStorage.getItem(pwStorageKey());
  const goBtn = document.getElementById('gateGo');
  const pwInput = document.getElementById('gatePw');
  const err = document.getElementById('gateErr');
  function tryWith(pw){
    attemptUnlock(pw, renderUnlocked, function(){
      if (err) err.textContent = 'Feil passord.';
      sessionStorage.removeItem(pwStorageKey());
    });
  }
  if (saved) tryWith(saved);
  if (goBtn) goBtn.addEventListener('click', ()=> tryWith(pwInput.value));
  if (pwInput) pwInput.addEventListener('keydown', e=>{ if(e.key==='Enter') tryWith(pwInput.value); });
});
"""

def gate_page_shell(title: str, payload: dict, kind: str, meta: dict, render_js: str) -> str:
    payload_json = json.dumps(payload)
    meta_json = json.dumps(meta, ensure_ascii=False)
    return f"""<!DOCTYPE html>
<html lang="no">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<style>{GATE_CSS}</style>
</head>
<body>
<div class="container">
{theme_toggle()}
<div id="gateBox" class="gate-box">
  <h1>🔒 Beskyttet innhold</h1>
  <p style="color:var(--text-muted);font-size:14px;">Denne mappen krever passord.</p>
  <input type="password" id="gatePw" placeholder="Passord" autofocus>
  <button id="gateGo">Lås opp</button>
  <div class="gate-err" id="gateErr"></div>
</div>
<div id="gateContent"></div>
</div>
<script>
const PAYLOAD = {payload_json};
const META = {meta_json};
{GATE_JS_LIB}
{render_js}
</script>
</body>
</html>"""

RENDER_JS_HTML = r"""
const MIME_BY_EXT = {
  jpg:'image/jpeg', jpeg:'image/jpeg', png:'image/png', gif:'image/gif', webp:'image/webp', heic:'image/heic',
  pdf:'application/pdf', doc:'application/msword',
  docx:'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  xls:'application/vnd.ms-excel', xlsx:'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  ppt:'application/vnd.ms-powerpoint', pptx:'application/vnd.openxmlformats-officedocument.presentationml.presentation',
  mov:'video/quicktime', mp4:'video/mp4', m4a:'audio/mp4', pluginpayloadattachment:'application/octet-stream'
};
function isExternalSrc(src){
  return /^([a-z]+:)?\/\//i.test(src) || src.startsWith('data:') || src.startsWith('blob:') || src.startsWith('#');
}
async function inlineDecryptImage(src, pw){
  const resp = await fetch(src + '.html');
  if (!resp.ok) return null;
  const html = await resp.text();
  const m = html.match(/const PAYLOAD = (\{[\s\S]*?\});/);
  if (!m) return null;
  const payload = JSON.parse(m[1]);
  const imgBytes = await decryptPrivatPayload(payload, pw);
  const extMatch = src.match(/\.([a-zA-Z0-9]+)$/);
  const mime = (extMatch && MIME_BY_EXT[extMatch[1].toLowerCase()]) || 'application/octet-stream';
  return URL.createObjectURL(new Blob([imgBytes], {type: mime}));
}
const LAZY_IMG_PLACEHOLDER = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='1' height='1'/%3E";
// Inline photos are decrypted eagerly, in parallel, the moment the page
// unlocks - fine for a handful of images, but a message page can carry over
// a hundred of them, and EACH decrypt re-runs a full 210000-round PBKDF2 key
// derivation (every file's key-derivation salt is content-derived, so it is
// intentionally different per file - see aes.py). A hundred-plus PBKDF2 runs
// back-to-back on page load is the main reason some pages feel slow to open.
// Fix: only decrypt photos as they actually scroll into view, via a small
// self-contained script injected into the iframe (it cannot share the outer
// page's JS scope, only sessionStorage, since it is a separate document).
const LAZY_IMAGE_SCRIPT_BODY = `
(function(){
  function b64ToBytes(b64){const bin=atob(b64);const a=new Uint8Array(bin.length);for(let i=0;i<bin.length;i++)a[i]=bin.charCodeAt(i);return a;}
  async function derivePrivatKey(pw, saltB64, iterations){
    const salt = b64ToBytes(saltB64);
    const enc = new TextEncoder();
    const baseKey = await crypto.subtle.importKey('raw', enc.encode(pw), 'PBKDF2', false, ['deriveKey']);
    return crypto.subtle.deriveKey({name:'PBKDF2', salt, iterations, hash:'SHA-256'}, baseKey, {name:'AES-CBC', length:256}, false, ['decrypt']);
  }
  async function decryptPrivatPayload(payload, pw){
    const key = await derivePrivatKey(pw, payload.salt, payload.iterations);
    const iv = b64ToBytes(payload.iv);
    const ct = b64ToBytes(payload.ciphertext);
    const buf = await crypto.subtle.decrypt({name:'AES-CBC', iv}, key, ct);
    return new Uint8Array(buf);
  }
  const MIME_BY_EXT = {
    jpg:'image/jpeg', jpeg:'image/jpeg', png:'image/png', gif:'image/gif', webp:'image/webp', heic:'image/heic'
  };
  async function decryptLazyImage(img){
    const src = img.getAttribute('data-privat-src');
    const pw = sessionStorage.getItem('privatPw');
    if (!src || !pw) return;
    try{
      const resp = await fetch(src + '.html');
      if (!resp.ok) return;
      const html = await resp.text();
      const m = html.match(/const PAYLOAD = (\\{[\\s\\S]*?\\});/);
      if (!m) return;
      const payload = JSON.parse(m[1]);
      const bytes = await decryptPrivatPayload(payload, pw);
      const extMatch = src.match(/\\.([a-zA-Z0-9]+)$/);
      const mime = (extMatch && MIME_BY_EXT[extMatch[1].toLowerCase()]) || 'application/octet-stream';
      img.setAttribute('src', URL.createObjectURL(new Blob([bytes], {type: mime})));
      img.removeAttribute('data-privat-src');
      img.classList.remove('privat-lazy');
    }catch(e){ /* leave the placeholder if decryption fails */ }
  }
  function initLazyImages(){
    const pending = Array.from(document.querySelectorAll('img[data-privat-src]'));
    if (!pending.length) return;
    if (!('IntersectionObserver' in window)) { pending.forEach(decryptLazyImage); return; }
    const io = new IntersectionObserver(function(entries){
      entries.forEach(function(entry){
        if (entry.isIntersecting) { io.unobserve(entry.target); decryptLazyImage(entry.target); }
      });
    }, {rootMargin: '800px 0px'});
    pending.forEach(function(img){ io.observe(img); });
  }
  if (document.readyState === 'loading') { document.addEventListener('DOMContentLoaded', initLazyImages); }
  else { initLazyImages(); }
})();
`;
async function renderUnlocked(bytes, pw){
  document.getElementById('gateBox').style.display='none';
  const c = document.getElementById('gateContent');
  c.style.display='block';
  const text = new TextDecoder('utf-8').decode(bytes);
  const doc = new DOMParser().parseFromString(text, 'text/html');
  const imgs = Array.from(doc.querySelectorAll('img[src]'));
  imgs.forEach((img) => {
    const src = img.getAttribute('src');
    if (!src || isExternalSrc(src)) return;
    img.setAttribute('data-privat-src', src);
    img.setAttribute('src', LAZY_IMG_PLACEHOLDER);
    img.classList.add('privat-lazy');
  });
  const lazyStyle = doc.createElement('style');
  lazyStyle.textContent = 'img.privat-lazy{background:#e4e4e0;min-height:48px;}';
  doc.head.appendChild(lazyStyle);
  const iconLinks = Array.from(doc.querySelectorAll('link[rel~="icon"][href], link[rel="apple-touch-icon"][href]'));
  await Promise.all(iconLinks.map(async (link) => {
    const src = link.getAttribute('href');
    if (!src || isExternalSrc(src)) return;
    try {
      const blobUrl = await inlineDecryptImage(src, pw);
      if (blobUrl) link.setAttribute('href', blobUrl);
    } catch (e) { /* leave as-is if decryption fails */ }
  }));
  const videoEls = Array.from(doc.querySelectorAll('video[src], video source[src]'));
  await Promise.all(videoEls.map(async (el) => {
    const src = el.getAttribute('src');
    if (!src || isExternalSrc(src)) return;
    try {
      const blobUrl = await inlineDecryptImage(src, pw);
      if (blobUrl) el.setAttribute('src', blobUrl);
    } catch (e) { /* leave the original (broken) src if decryption fails */ }
  }));
  const posterEls = Array.from(doc.querySelectorAll('video[poster]'));
  await Promise.all(posterEls.map(async (el) => {
    const src = el.getAttribute('poster');
    if (!src || isExternalSrc(src)) return;
    try {
      const blobUrl = await inlineDecryptImage(src, pw);
      if (blobUrl) el.setAttribute('poster', blobUrl);
    } catch (e) { /* leave the original (broken) poster if decryption fails */ }
  }));
  const styles = Array.from(doc.querySelectorAll('style'));
  await Promise.all(styles.map(async (styleEl) => {
    let css = styleEl.textContent || '';
    const urlRe = /url\((['"]?)([^'")]+)\1\)/g;
    const matches = [...css.matchAll(urlRe)];
    for (const mm of matches) {
      const src = mm[2];
      if (!src || isExternalSrc(src)) continue;
      try {
        const blobUrl = await inlineDecryptImage(src, pw);
        if (blobUrl) css = css.split(mm[0]).join('url(' + blobUrl + ')');
      } catch (e) { /* leave as-is if decryption fails */ }
    }
    styleEl.textContent = css;
  }));
  // Page-to-page navigation links (another gate page in its own right, e.g.
  // a link to a subfolder or sibling page) must escape this iframe instead
  // of navigating inside it. This content is rendered into an <iframe> below
  // via srcdoc, so a plain relative click here would normally navigate just
  // that iframe - stacking a second gate+iframe inside the first, and a
  // third inside that on the next click, and so on ("ramme i ramme").
  // target="_top" makes the browser navigate the whole tab instead, which is
  // also what lets the top-level gate page's cached sessionStorage password
  // auto-unlock the next page seamlessly.
  const navLinks = Array.from(doc.querySelectorAll('a[href]'));
  navLinks.forEach((a) => {
    const href = a.getAttribute('href');
    if (href && !isExternalSrc(href) && /\.html?(#.*)?$/i.test(href)) {
      a.setAttribute('target', '_top');
    }
  });
  // Attachment links (PDFs, Office docs, GIFs referenced by href, plugin
  // attachments, etc.) - the encrypted gate page for a non-html file `foo.ext`
  // is stored as `foo.ext.html`, so a plain `<a href="media/foo.ext">` copied
  // verbatim from the source page would 404. Decrypt it here too and turn the
  // link into a direct one-click blob download - reusing the same password,
  // no second gate page / prompt needed. Links that already end in `.html`
  // are ordinary page-to-page navigation (handled just above) and must be
  // left alone here.
  const attachLinks = Array.from(doc.querySelectorAll('a[href]'));
  await Promise.all(attachLinks.map(async (a) => {
    const href = a.getAttribute('href');
    if (!href || isExternalSrc(href) || /\.html?(#.*)?$/i.test(href)) return;
    try {
      const blobUrl = await inlineDecryptImage(href, pw);
      if (blobUrl) {
        a.setAttribute('href', blobUrl);
        if (!a.hasAttribute('download')) {
          const base = decodeURIComponent(href.split('/').pop());
          a.setAttribute('download', base);
        }
      }
    } catch (e) { /* leave the original (broken) href if decryption fails */ }
  }));
  const frame = document.createElement('iframe');
  frame.className = 'gate-frame';
  c.appendChild(frame);
  if (imgs.length) {
    const lazyScript = doc.createElement('script');
    lazyScript.textContent = LAZY_IMAGE_SCRIPT_BODY;
    doc.body.appendChild(lazyScript);
  }
  frame.srcdoc = '<!DOCTYPE html>' + doc.documentElement.outerHTML;
}
"""

RENDER_JS_DOWNLOAD = """
function renderUnlocked(bytes){
  document.getElementById('gateBox').style.display='none';
  const c = document.getElementById('gateContent');
  c.style.display='block';
  const blob = new Blob([bytes], {type: META.mime || 'application/octet-stream'});
  const url = URL.createObjectURL(blob);
  c.innerHTML = '<p style="text-align:center;padding:40px 0;">✅ Opplåst.<br><a class="btn" style="display:inline-block;margin-top:14px;" href="'+url+'" download="'+META.filename+'">⬇ Last ned '+META.filename+'</a></p>';
}
"""

RENDER_JS_LISTING = """
function renderUnlocked(bytes){
  document.getElementById('gateBox').style.display='none';
  const c = document.getElementById('gateContent');
  c.style.display='block';
  const manifest = JSON.parse(new TextDecoder('utf-8').decode(bytes));
  let out = '<h1>🔓 ' + (META.title||'Privat') + '</h1>';
  out += '<div class="breadcrumb"><a href="/index.html">🏠 Hjem</a>' + (META.breadcrumb ? ' / ' + META.breadcrumb : '') + '<a href="#" class="back-link" onclick="history.back();return false;">⬅ Tilbake</a></div>';
  if (manifest.length === 0) { out += '<p style="color:var(--text-muted);">Ingen filer ennå.</p>'; }
  out += '<ul class="filelist">';
  manifest.forEach(item=>{
    const icon = item.isDir ? '📁' : (item.icon||'📄');
    out += '<li><span class="name">'+icon+' <a href="'+item.href+'">'+item.name+'</a></span></li>';
  });
  out += '</ul>';
  c.innerHTML = out;
}
"""

def rescue_stray_privat_files():
    """If a plain (unencrypted) file was dropped directly into the git-tracked
    Privat/ folder - e.g. because that's the natural place to add things, same
    as every other folder on the site - move it into the external Privat-kilde
    source folder instead of leaving it there or silently discarding it. It
    then gets picked up and encrypted like anything else, and is never left
    sitting in the repo in the clear when git add/commit runs."""
    if not PRIVAT_OUTPUT.exists():
        return
    PRIVAT_SOURCE.mkdir(parents=True, exist_ok=True)
    for p in list(PRIVAT_OUTPUT.rglob("*")):
        if p.is_dir():
            continue
        if p.name == "index.html":
            continue  # our own generated listing page - safe to discard/replace
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            text = ""
        if '"ciphertext"' in text:
            continue  # already our own encrypted output
        rel = p.relative_to(PRIVAT_OUTPUT)
        dest = PRIVAT_SOURCE / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            stem, suffix, i = dest.stem, dest.suffix, 2
            candidate = dest.with_name(f"{stem} ({i}){suffix}")
            while candidate.exists():
                i += 1
                candidate = dest.with_name(f"{stem} ({i}){suffix}")
            dest = candidate
        shutil.move(str(p), str(dest))
        log(f"Fant en ukryptert fil direkte i Privat/ ({rel}) - flyttet til {PRIVAT_SOURCE.name} for kryptering.")

def encrypt_privat(repo: Path, password: str):
    rescue_stray_privat_files()
    PRIVAT_SOURCE.mkdir(parents=True, exist_ok=True)
    if PRIVAT_OUTPUT.exists():
        shutil.rmtree(PRIVAT_OUTPUT)
    PRIVAT_OUTPUT.mkdir(parents=True, exist_ok=True)

    def gate_filename_for(src: Path) -> str:
        return src.name if src.suffix.lower() == ".html" else src.name + ".html"

    def process_dir(src_dir: Path, out_dir: Path, breadcrumb_parts):
        out_dir.mkdir(parents=True, exist_ok=True)
        manifest = []
        has_custom_index = False
        entries = sorted(src_dir.iterdir(), key=lambda p: p.name.casefold())
        for entry in entries:
            if entry.name.startswith(".") or entry.name == "Thumbs.db":
                continue
            if entry.is_file() and entry.name.lower() == "index.html":
                has_custom_index = True
            if entry.is_dir():
                sub_breadcrumb = breadcrumb_parts + [entry.name]
                process_dir(entry, out_dir / entry.name, sub_breadcrumb)
                manifest.append({"name": entry.name, "isDir": True, "href": entry.name + "/index.html"})
            else:
                gate_name = gate_filename_for(entry)
                ext_link = EXTERNAL_MEDIA_LINKS.get(entry.name)
                if ext_link:
                    # Oversized video hosted externally (see EXTERNAL_MEDIA_LINKS
                    # comment near the top of this file) - encrypt a small "open
                    # externally" card instead of the real file bytes, so the
                    # video's actual multi-hundred-MB/GB payload never enters the
                    # git repo. Still password-gated, same lock/unlock flow and
                    # visual language as every other page on the site.
                    card_html = (
                        "<!DOCTYPE html><html lang=\"no\"><body style=\"margin:0;"
                        "font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Arial,sans-serif;"
                        "background:#eef2ff;color:#111;padding:24px;\">"
                        "<div style=\"max-width:420px;margin:0 auto;text-align:center;\">"
                        f"<img src=\"{html.escape(ext_link['thumb'])}\" alt=\"{html.escape(entry.name)}\" "
                        "style=\"max-width:100%;border-radius:14px;display:block;margin:0 auto 18px;"
                        "box-shadow:0 4px 20px rgba(0,0,0,0.15);\">"
                        f"<p style=\"font-size:14px;color:#5a5f73;margin:0 0 4px;\">{html.escape(entry.name)}</p>"
                        f"<p style=\"font-size:13px;color:#5a5f73;margin:0 0 18px;\">Filen er {ext_link['size_label']} "
                        "og lagres derfor hos en ekstern videotjeneste i stedet for i arkivet.</p>"
                        f"<a href=\"{html.escape(ext_link['url'])}\" target=\"_blank\" rel=\"noopener\" "
                        "style=\"display:inline-block;padding:12px 26px;border-radius:999px;"
                        "background:#0044aa;color:#fff;font-weight:600;font-size:15px;text-decoration:none;\">"
                        "\u25b6\ufe0f \u00c5pne / spill av video</a>"
                        "</div></body></html>"
                    )
                    payload = aes.encrypt_for_browser(card_html.encode("utf-8"), password)
                    page = gate_page_shell(title_from_filename(entry.name), payload, "html", {}, RENDER_JS_HTML)
                    (out_dir / gate_name).write_text(page, encoding="utf-8")
                    manifest.append({"name": entry.name, "isDir": False, "href": gate_name, "icon": icon_for(entry.name)})
                    continue
                data = entry.read_bytes()
                payload = aes.encrypt_for_browser(data, password)
                if entry.suffix.lower() == ".html":
                    page = gate_page_shell(entry.stem, payload, "html", {}, RENDER_JS_HTML)
                else:
                    mime = {
                        ".pdf": "application/pdf",
                        ".doc": "application/msword",
                        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        ".xls": "application/vnd.ms-excel",
                        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        ".ppt": "application/vnd.ms-powerpoint",
                        ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
                    }.get(entry.suffix.lower(), "application/octet-stream")
                    meta = {"filename": entry.name, "mime": mime}
                    page = gate_page_shell(entry.name, payload, "download", meta, RENDER_JS_DOWNLOAD)
                (out_dir / gate_name).write_text(page, encoding="utf-8")
                manifest.append({"name": entry.name, "isDir": False, "href": gate_name, "icon": icon_for(entry.name)})

        if has_custom_index:
            # A real index.html was found among this folder's own source files
            # (already encrypted above, in the main loop) - it IS the folder's
            # landing page. Do not clobber it with the generic auto-listing.
            return

        breadcrumb_html = " / ".join(
            [f'<a href="/{PRIVAT_DIR_NAME}/index.html">{PRIVAT_DIR_NAME}</a>'] +
            [html.escape(p) for p in breadcrumb_parts]
        ) if breadcrumb_parts else f'<a href="/{PRIVAT_DIR_NAME}/index.html">{PRIVAT_DIR_NAME}</a>'
        manifest_bytes = json.dumps(manifest, ensure_ascii=False).encode("utf-8")
        payload = aes.encrypt_for_browser(manifest_bytes, password)
        title = breadcrumb_parts[-1] if breadcrumb_parts else PRIVAT_DIR_NAME
        meta = {"title": title, "breadcrumb": breadcrumb_html}
        listing_page = gate_page_shell(title, payload, "listing", meta, RENDER_JS_LISTING)
        (out_dir / "index.html").write_text(listing_page, encoding="utf-8")

    if PRIVAT_SOURCE.exists() and any(PRIVAT_SOURCE.iterdir()):
        process_dir(PRIVAT_SOURCE, PRIVAT_OUTPUT, [])
        log(f"Privat-mappen ble kryptert fra {PRIVAT_SOURCE} ({sum(1 for _ in PRIVAT_SOURCE.rglob('*') if _.is_file())} fil(er)).")
    else:
        # Empty but present, so the folder card + lock UI still work.
        payload = aes.encrypt_for_browser(b"[]", password)
        meta = {"title": PRIVAT_DIR_NAME, "breadcrumb": f'<a href="/{PRIVAT_DIR_NAME}/index.html">{PRIVAT_DIR_NAME}</a>'}
        (PRIVAT_OUTPUT / "index.html").write_text(
            gate_page_shell(PRIVAT_DIR_NAME, payload, "listing", meta, RENDER_JS_LISTING), encoding="utf-8"
        )
        log(f"Privat-mappen er tom. Legg filer i {PRIVAT_SOURCE} for å publisere dem passordbeskyttet.")

def load_privat_password():
    if PRIVAT_SECRET_FILE.exists():
        pw = PRIVAT_SECRET_FILE.read_text(encoding="utf-8").strip()
        if pw:
            return pw
    return None

# ---------------------------------------------------------------------------
# Misc: .nojekyll, .gitignore
# ---------------------------------------------------------------------------

def ensure_support_files(repo: Path):
    nojekyll = repo / ".nojekyll"
    if not nojekyll.exists():
        nojekyll.write_text("", encoding="utf-8")
        log("La til .nojekyll (hindrer GitHub fra å kjøre siden gjennom Jekyll).")
    gitignore = repo / ".gitignore"
    wanted = [".DS_Store", "**/.DS_Store", ".idea/", ".vscode/", ".site-tools/__pycache__/", "**/__pycache__/", ".site-tools/publish.log", ".site-tools/.publish.lock/", ".site-tools/.paused"]
    existing = gitignore.read_text(encoding="utf-8").splitlines() if gitignore.exists() else []
    merged = existing + [w for w in wanted if w not in existing]
    if merged != existing:
        gitignore.write_text("\n".join(merged) + "\n", encoding="utf-8")
        log("Oppdaterte .gitignore.")

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    if not REPO.exists():
        print(f"FEIL: repo-mappen finnes ikke: {REPO}", file=sys.stderr)
        sys.exit(1)

    repair_legacy_corruption(REPO)
    ensure_support_files(REPO)
    cleanup_stray_thumbnails(REPO)

    password = load_privat_password()
    if password:
        encrypt_privat(REPO, password)
    else:
        log(f"Ingen Privat-passord funnet i {PRIVAT_SECRET_FILE} - hopper over kryptering av Privat.")

    recent = collect_recent_files(REPO, limit=10)
    walk_and_generate(REPO)
    build_search_index(REPO)
    build_sitemap_rss(REPO, recent)

    print("Ferdig.")

if __name__ == "__main__":
    main()
