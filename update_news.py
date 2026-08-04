#!/usr/bin/env python3
"""APEX TCG Intel daily updater. Scrapes PokeGuardian + official One Piece
topics page. Flags (never auto-inserts) possible new-date headlines --
regex date extraction is too unreliable to trust unattended."""
import re, sys, time
from datetime import datetime, timezone, timedelta
from html import escape
import requests
from bs4 import BeautifulSoup

H = {"User-Agent": "Mozilla/5.0 (compatible; ApexTCGIntelBot/1.0)"}
TIMEOUT, MAX_ITEMS, RETRIES = 20, 4, 2
JUNK = re.compile(r"cookie|privacy policy|terms of (service|use)|subscribe|sign up|log in|copyright \d{4}|all rights reserved|advertisement|^\d+$", re.I)
TRAIL_DATE = re.compile(r"\s+\d{1,2}\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s*\d{0,4}$", re.I)
DATE_PAT = re.compile(r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2}(st|nd|rd|th)?\b|\bQ[1-4]\s*20\d{2}\b", re.I)
RELEASE_KW = re.compile(r"\b(release[sd]?|pre-?order[s]?|launch(es|ed)?|available|drop[s]?|ship(s|ping)?|arriv\w*|coming)\b", re.I)

def fetch(url):
    for i in range(1, RETRIES + 1):
        try:
            r = requests.get(url, headers=H, timeout=TIMEOUT)
            r.raise_for_status()
            return r.text
        except Exception as e:
            print(f"WARN attempt {i}: {e}", file=sys.stderr)
            if i < RETRIES: time.sleep(2)
    return None

def clean(t):
    return TRAIL_DATE.sub("", re.sub(r"\s+", " ", t).strip()).strip()

def is_junk(t):
    return bool(JUNK.search(t)) or len(t.split()) < 3

def is_new_date(t):
    return bool(DATE_PAT.search(t)) and bool(RELEASE_KW.search(t))

def dedupe(items):
    seen, out = set(), []
    for it in items:
        k = it.lower()[:60]
        if k in seen: continue
        seen.add(k); out.append(it)
    return out

def scrape_pokemon():
    items = []
    html = fetch("https://www.pokeguardian.com/articles/news-archive")
    if html:
        text = BeautifulSoup(html, "html.parser").get_text("\n")
        for c in re.split(r"Read more\s*»", text):
            c = clean(c.replace("\n", " "))
            if 30 < len(c) < 400 and not is_junk(c): items.append(c)
    items = dedupe(items)
    if len(items) < 2:
        html2 = fetch("https://www.pokeguardian.com/")
        if html2:
            for h in BeautifulSoup(html2, "html.parser").find_all(["h1", "h2", "h3"]):
                t = clean(h.get_text(" "))
                if 20 < len(t) < 200 and not is_junk(t): items.append(t)
        items = dedupe(items)
    return items[:MAX_ITEMS]

def scrape_onepiece():
    html = fetch("https://en.onepiece-cardgame.com/topics/")
    if not html: return []
    text = BeautifulSoup(html, "html.parser").get_text("\n")
    items = []
    for line in [clean(l) for l in text.split("\n") if l.strip()]:
        if is_junk(line): continue
        if re.search(r"(has been (updated|announced|released)|CARD REVEAL)", line, re.I) and 15 < len(line) < 300:
            items.append(line)
    return dedupe(items)[:MAX_ITEMS]

def build_html(items):
    if not items: return None
    d = datetime.now(timezone.utc).strftime("%d %b").upper()
    out = []
    for it in items:
        title = it if len(it) < 90 else it[:87].rsplit(" ", 1)[0] + "…"
        badge = '<span class="live-badge" style="color:var(--gold);border-color:rgba(232,179,74,.4);background:rgba(232,179,74,.1);">⚠ NEW DATE?</span>' if is_new_date(it) else '<span class="live-badge">AUTO</span>'
        out.append(f'<div class="news-item"><div class="news-date">{d}</div><div class="news-body"><h4>{escape(title)}{badge}</h4></div></div>')
    return "\n".join(out)

def inject(html, cid, nid, items):
    block = build_html(items)
    if not block: return html
    pat = re.compile(rf'(<div class="card" id="{cid}" style="padding:4px 16px;)[^"]*(")([^<]*)</div>')
    html2, n = pat.subn(rf'\1\2>{block}</div>', html, count=1)
    if n == 0: return html
    stamp = datetime.now(timezone(timedelta(hours=8))).strftime("%d %b, %I:%M %p")
    np = re.compile(rf'(<div class="section-note" id="{nid}">)[^<]*(</div>)')
    html2, _ = np.subn(rf'\g<1>auto-updated {stamp} PHT\g<2>', html2, count=1)
    return html2

def main():
    with open("index.html", encoding="utf-8") as f:
        html = f.read()
    poke, op = scrape_pokemon(), scrape_onepiece()
    flagged = sum(1 for i in poke + op if is_new_date(i))
    print(f"Pokemon: {len(poke)}, OnePiece: {len(op)}, flagged: {flagged}")
    html = inject(html, "pokemon-news-live", "pokeUpdatedNote", poke)
    html = inject(html, "onepiece-news-live", "opUpdatedNote", op)
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html)
    print("index.html updated.")

if __name__ == "__main__":
    main()
