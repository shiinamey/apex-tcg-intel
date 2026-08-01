#!/usr/bin/env python3
"""Daily news updater for APEX TCG Intel. Scrapes PokeGuardian and the
official One Piece Card Game topics page, injects results into index.html."""
import re, sys, time
from datetime import datetime, timezone, timedelta
from html import escape
import requests
from bs4 import BeautifulSoup

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; ApexTCGIntelBot/1.0)"}
TIMEOUT = 20
MAX_ITEMS = 4
RETRIES = 2
JUNK_RE = re.compile(r"cookie|privacy policy|terms of (service|use)|subscribe|sign up|log in|copyright \d{4}|all rights reserved|advertisement|^\d+$", re.I)
TRAIL_DATE_RE = re.compile(r"\s+\d{1,2}\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s*\d{0,4}$", re.I)

def fetch(url):
    for i in range(1, RETRIES + 1):
        try:
            r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
            r.raise_for_status()
            return r.text
        except Exception as e:
            print(f"WARN: attempt {i}/{RETRIES} failed for {url}: {e}", file=sys.stderr)
            if i < RETRIES: time.sleep(2)
    return None

def clean(t):
    t = re.sub(r"\s+", " ", t).strip()
    return TRAIL_DATE_RE.sub("", t).strip()

def is_junk(t):
    return bool(JUNK_RE.search(t)) or len(t.split()) < 3

def dedupe(items):
    seen, out = set(), []
    for it in items:
        k = it.lower()[:60]
        if k in seen: continue
        seen.add(k); out.append(it)
    return out

def scrape_pokemon_news():
    items = []
    html = fetch("https://www.pokeguardian.com/articles/news-archive")
    if html:
        text = BeautifulSoup(html, "html.parser").get_text("\n")
        for chunk in re.split(r"Read more\s*»", text):
            c = clean(chunk.replace("\n", " "))
            if 30 < len(c) < 400 and not is_junk(c): items.append(c)
    items = dedupe(items)
    if len(items) < 2:
        print("INFO: archive yielded too few items, trying homepage", file=sys.stderr)
        html2 = fetch("https://www.pokeguardian.com/")
        if html2:
            soup2 = BeautifulSoup(html2, "html.parser")
            for h in soup2.find_all(["h1", "h2", "h3"]):
                t = clean(h.get_text(" "))
                if 20 < len(t) < 200 and not is_junk(t): items.append(t)
        items = dedupe(items)
    return items[:MAX_ITEMS]

def scrape_onepiece_news():
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
    date_str = datetime.now(timezone.utc).strftime("%d %b").upper()
    blocks = []
    for it in items:
        title = it if len(it) < 90 else it[:87].rsplit(" ", 1)[0] + "…"
        blocks.append(f'<div class="news-item"><div class="news-date">{date_str}</div><div class="news-body"><h4>{escape(title)}<span class="live-badge">AUTO</span></h4></div></div>')
    return "\n".join(blocks)

def inject(html, container_id, note_id, items):
    block = build_html(items)
    if not block:
        print(f"WARN: no items for {container_id}", file=sys.stderr)
        return html
    pattern = re.compile(rf'(<div class="card" id="{container_id}" style="padding:4px 16px;)[^"]*(")([^<]*)</div>')
    new_html, n = pattern.subn(rf'\1\2>{block}</div>', html, count=1)
    if n == 0:
        print(f"WARN: container {container_id} not found", file=sys.stderr)
        return html
    stamp = datetime.now(timezone(timedelta(hours=8))).strftime("%d %b, %I:%M %p")
    note_pattern = re.compile(rf'(<div class="section-note" id="{note_id}">)[^<]*(</div>)')
    new_html, _ = note_pattern.subn(rf'\g<1>auto-updated {stamp} PHT\g<2>', new_html, count=1)
    return new_html

def main():
    with open("index.html", encoding="utf-8") as f:
        html = f.read()
    poke_items = scrape_pokemon_news()
    op_items = scrape_onepiece_news()
    print(f"Pokemon items: {len(poke_items)}, One Piece items: {len(op_items)}")
    html = inject(html, "pokemon-news-live", "pokeUpdatedNote", poke_items)
    html = inject(html, "onepiece-news-live", "opUpdatedNote", op_items)
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html)
    print("index.html updated.")

if __name__ == "__main__":
    main()
