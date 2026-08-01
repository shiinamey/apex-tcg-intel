#!/usr/bin/env python3
"""
Daily news updater for APEX TCG Intel.
Scrapes PokeGuardian's news archive and the official One Piece Card Game
topics page, then injects the latest items into index.html between the
existing live-news containers.

No API keys required. Runs entirely inside the GitHub Actions runner.
"""
import re
import sys
from datetime import datetime, timezone, timedelta
from html import escape

import requests
from bs4 import BeautifulSoup

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; ApexTCGIntelBot/1.0)"}
TIMEOUT = 20
MAX_ITEMS = 4


def fetch(url):
    try:
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        resp.raise_for_status()
        return resp.text
    except Exception as e:
        print(f"WARN: failed to fetch {url}: {e}", file=sys.stderr)
        return None


def scrape_pokemon_news():
    """PokeGuardian's news archive: paragraphs ending in 'Read more »'."""
    html = fetch("https://www.pokeguardian.com/articles/news-archive")
    if not html:
        return []
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text("\n")
    # Split on the site's consistent "Read more »" call-to-action
    chunks = re.split(r"Read more\s*»", text)
    items = []
    for chunk in chunks:
        chunk = chunk.strip().replace("\n", " ")
        chunk = re.sub(r"\s+", " ", chunk)
        # Keep plausible news sentences only
        if 30 < len(chunk) < 400:
            items.append(chunk)
        if len(items) >= MAX_ITEMS:
            break
    return items


def scrape_onepiece_news():
    """Official One Piece Card Game topics page: list of dated announcements."""
    html = fetch("https://en.onepiece-cardgame.com/topics/")
    if not html:
        return []
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text("\n")
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    items = []
    for line in lines:
        if re.search(r"(has been (updated|announced|released)|CARD REVEAL)", line, re.I):
            if 15 < len(line) < 300 and line not in items:
                items.append(line)
        if len(items) >= MAX_ITEMS:
            break
    return items


def build_news_html(items, label):
    if not items:
        return None
    now = datetime.now(timezone.utc)
    date_str = now.strftime("%d %b").upper()
    blocks = []
    for item in items:
        title = item if len(item) < 90 else item[:87] + "…"
        blocks.append(
            f'''<div class="news-item">
          <div class="news-date">{date_str}</div>
          <div class="news-body">
            <h4>{escape(title)}<span class="live-badge">AUTO</span></h4>
          </div>
        </div>'''
        )
    return "\n".join(blocks)


def inject(html, container_id, note_id, items, source_label):
    block = build_news_html(items, source_label)
    if not block:
        print(f"WARN: no items scraped for {container_id}, leaving unchanged", file=sys.stderr)
        return html

    # Replace the container's inner content and make it visible
    pattern = re.compile(
        rf'(<div class="card" id="{container_id}" style="padding:4px 16px;)[^"]*(")([^<]*)</div>'
    )
    replacement = rf'\1\2>{block}</div>'
    new_html, n = pattern.subn(replacement, html, count=1)
    if n == 0:
        print(f"WARN: container {container_id} not found/pattern mismatch", file=sys.stderr)
        return html

    ph_time = datetime.now(timezone(timedelta(hours=8)))
    stamp = ph_time.strftime("%d %b, %I:%M %p")
    note_pattern = re.compile(rf'(<div class="section-note" id="{note_id}">)[^<]*(</div>)')
    new_html, n2 = note_pattern.subn(rf'\g<1>auto-updated {stamp} PHT\g<2>', new_html, count=1)

    return new_html


def main():
    with open("index.html", encoding="utf-8") as f:
        html = f.read()

    poke_items = scrape_pokemon_news()
    op_items = scrape_onepiece_news()

    print(f"Pokemon items scraped: {len(poke_items)}")
    print(f"One Piece items scraped: {len(op_items)}")

    html = inject(html, "pokemon-news-live", "pokeUpdatedNote", poke_items, "Pokemon")
    html = inject(html, "onepiece-news-live", "opUpdatedNote", op_items, "OnePiece")

    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html)

    print("index.html updated.")


if __name__ == "__main__":
    main()
