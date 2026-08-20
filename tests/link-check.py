#!/usr/bin/env python3
"""Check every internal link in a built site resolves.

Run against the real build, not `zola serve`:

    nix build .#site && python3 tests/link-check.py result

The default target is ./public. The point of this existing at all is that the
site is served under the /ai-slop/ path prefix in production but at the root by
`zola serve`, so a link that is wrong for production looks perfectly fine in
local preview. This resolves every href and src the way a browser would from the
page it appears on, against the prefix.
"""

import re, sys, posixpath
from pathlib import Path
ROOT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("public")
PREFIX = "/ai-slop"
HREF = re.compile(r'(?:href|src)=(?:"([^"]*)"|\'([^\']*)\'|([^\s>]+))', re.I)
def exists(sp):
    if not sp.startswith(PREFIX): return False
    rel = sp[len(PREFIX):].lstrip("/")
    t = ROOT / rel if rel else ROOT
    return (t / "index.html").is_file() if t.is_dir() else t.is_file()
bad, checked, ext = [], 0, 0
for html in sorted(ROOT.rglob("*.html")):
    rel = html.relative_to(ROOT)
    pd = (PREFIX + "/" + str(rel.parent).replace(".", "").strip("/")).rstrip("/") or PREFIX
    for m in HREF.finditer(html.read_text(errors="replace")):
        h = m.group(1) or m.group(2) or m.group(3) or ""
        if not h or h.startswith("#") or h.startswith("mailto:"): continue
        if h.startswith("http") or re.match(r'^//', h): ext += 1; continue
        t = h.split("#")[0]
        if not t: continue
        r = t if t.startswith("/") else posixpath.normpath(posixpath.join(pd, t))
        if t.endswith("/") and not r.endswith("/"): r += "/"
        checked += 1
        if not exists(r): bad.append((str(rel), h, r))
print(f"internal links: {checked}   external: {ext}")
for p,h,r in bad[:20]: print(f"  BROKEN {p}: {h} -> {r}")
sys.exit(1 if bad else 0)
