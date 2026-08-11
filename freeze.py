#!/usr/bin/env python3
"""
Freeze the live dashboard into docs/ for GitHub Pages.

Fetches each route through the Flask test client (live Companies House API +
local snapshot), rewrites internal links to static filenames, injects a
"frozen capture" banner, and copies the stylesheet. Reproducible:

    python freeze.py
"""

import os
import re
import shutil
from datetime import datetime, timezone

from app import app

HERE = os.path.dirname(os.path.abspath(__file__))
DOCS = os.path.join(HERE, "docs")
CH_URL = "https://find-and-update.company-information.service.gov.uk/company"

# route -> output filename. Order matters for link rewriting (longest first).
PAGES = {
    "/company/11391321/vs/01854213": "compare-prets.html",
    "/company/11391321": "certificate-pret-holdco.html",
    "/company/01854213": "certificate-pret-opco.html",
    "/company/16043531": "certificate-354-oxford-street.html",
    "/sweep/W1S": "sweep-w1s.html",
    "/appendix": "appendix.html",
    "/?q=Pret+A+Manger": "search-pret.html",
    "/": "index.html",
}

BANNER = (
    '<div style="background:#201e1d;color:#f3f2f2;font-size:12px;letter-spacing:0.05em;'
    'padding:8px 32px;display:flex;justify-content:space-between;gap:16px;flex-wrap:wrap">'
    '<span>FROZEN CAPTURE &middot; real register data, captured {date}. '
    'Search and sweep inputs are inactive here.</span>'
    '<span>For live readings: <a href="https://github.com/amateurakhbar/covenant" '
    'style="color:#ffdd9c">clone the repo</a> and run <span style="font-family:monospace">'
    'python app.py</span></span></div>'
).format(date=datetime.now(timezone.utc).strftime("%d %b %Y"))


def rewrite(html):
    # Longest specific routes first, then the catch-alls.
    html = re.sub(r'href="/company/[A-Z0-9]+/vs/[A-Z0-9]+"', 'href="compare-prets.html"', html)
    for route, fname in PAGES.items():
        if route.startswith("/company/") and "/vs/" not in route:
            html = html.replace(f'href="{route}"', f'href="{fname}"')
    html = html.replace('href="/sweep/W1S"', 'href="sweep-w1s.html"')
    html = html.replace('href="/appendix"', 'href="appendix.html"')
    html = html.replace('action="/"', 'action="index.html"')
    html = html.replace('href="/"', 'href="index.html"')
    html = html.replace('href="/?q=Pret+A+Manger"', 'href="search-pret.html"')
    # Any company link we didn't freeze goes to the register itself.
    html = re.sub(r'href="/company/([A-Z0-9]+)"', rf'href="{CH_URL}/\1"', html)
    html = html.replace('"/static/', '"static/')
    # Banner sits directly under the header.
    html = html.replace("</header>", "</header>" + BANNER, 1)
    return html


def main():
    os.makedirs(DOCS, exist_ok=True)
    shutil.copytree(os.path.join(HERE, "static"), os.path.join(DOCS, "static"),
                    dirs_exist_ok=True)
    client = app.test_client()
    for route, fname in PAGES.items():
        r = client.get(route, follow_redirects=True)
        assert r.status_code == 200, (route, r.status_code)
        out = rewrite(r.get_data(as_text=True))
        with open(os.path.join(DOCS, fname), "w") as f:
            f.write(out)
        print(f"  {route:<38} -> docs/{fname}")
    # Pages must not run Jekyll (it would ignore nothing here, but be explicit).
    open(os.path.join(DOCS, ".nojekyll"), "w").close()
    print("Frozen. Serve docs/ anywhere static: GitHub Pages, python -m http.server.")


if __name__ == "__main__":
    main()
