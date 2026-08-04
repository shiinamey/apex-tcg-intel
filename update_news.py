#!/usr/bin/env python3
"""APEX TCG Intel updater. News -> injected. Date-like mentions -> listed
unverified, fully automatic. USD/PHP/JPY exchange rate -> refreshed daily
from a free no-key API, updating only the live calculator + header/footer
display (NOT every already-published price in card content -- recomputing
those unattended risks silently wrong numbers, worse than a stale label)."""
import re, sys, time, json
from datetime import datetime, timezone, timedelta
from html import escape
import requests
from bs4 import BeautifulSoup

H = {"User-Agent": "Mozilla/5.0 (compatible; ApexTCGIntelBot/1.0)"}
TIMEOUT, MAX_ITEMS, RETRIES = 20, 4, 2
JUNK = re.compile(r"cookie|privacy policy|terms of (service|use)|subscribe|sign up|log in|copyright \d{4}|all rights reserved|advertisement|^\d+$", re.I)
TRAIL = re.compile(r"\s+\d{1,2}\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s*\d{0,4}$", re.I)
DPAT = re.compile(r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2}(st|nd|rd|th)?\b|\bQ[1-4]\s*20\d{2}\b", re.I)
RKW = re.compile(r"\b(release[sd]?|pre-?order[s]?|launch(es|ed)?|available|drop[s]?|ship(s|ping)?|arriv\w*|coming)\b", re.I)

def fetch(u):
    for i in range(1, RETRIES + 1):
        try:
            r = requests.get(u, headers=H, timeout=TIMEOUT); r.raise_for_status(); return r.text
        except Exception as e:
            print(f"WARN {i}: {e}", file=sys.stderr)
            if i < RETRIES: time.sleep(2)
    return None

def clean(t): return TRAIL.sub("", re.sub(r"\s+", " ", t).strip()).strip()
def junk(t): return bool(JUNK.search(t)) or len(t.split()) < 3
def newdate(t): return bool(DPAT.search(t)) and bool(RKW.search(t))

def dedupe(items):
    seen, out = set(), []
    for it in items:
        k = it.lower()[:60]
        if k in seen: continue
        seen.add(k); out.append(it)
    return out

def pkmn():
    items = []
    h = fetch("https://www.pokeguardian.com/articles/news-archive")
    if h:
        t = BeautifulSoup(h, "html.parser").get_text("\n")
        for c in re.split(r"Read more\s*»", t):
            c = clean(c.replace("\n", " "))
            if 30 < len(c) < 400 and not junk(c): items.append(c)
    items = dedupe(items)
    if len(items) < 2:
        h2 = fetch("https://www.pokeguardian.com/")
        if h2:
            for x in BeautifulSoup(h2, "html.parser").find_all(["h1","h2","h3"]):
                t = clean(x.get_text(" "))
                if 20 < len(t) < 200 and not junk(t): items.append(t)
        items = dedupe(items)
    return items[:MAX_ITEMS]

def onepc():
    h = fetch("https://en.onepiece-cardgame.com/topics/")
    if not h: return []
    t = BeautifulSoup(h, "html.parser").get_text("\n")
    items = []
    for l in [clean(x) for x in t.split("\n") if x.strip()]:
        if junk(l): continue
        if re.search(r"(has been (updated|announced|released)|CARD REVEAL)", l, re.I) and 15 < len(l) < 300:
            items.append(l)
    return dedupe(items)[:MAX_ITEMS]
def build(items):
    if not items: return None
    d = datetime.now(timezone.utc).strftime("%d %b").upper()
    out = []
    for it in items:
        ti = it if len(it) < 90 else it[:87].rsplit(" ",1)[0] + "…"
        b = '<span class="live-badge" style="color:var(--gold);border-color:rgba(232,179,74,.4);background:rgba(232,179,74,.1);">⚠ NEW DATE?</span>' if newdate(it) else '<span class="live-badge">AUTO</span>'
        out.append(f'<div class="news-item"><div class="news-date">{d}</div><div class="news-body"><h4>{escape(ti)}{b}</h4></div></div>')
    return "\n".join(out)

def inject(h, cid, nid, items):
    blk = build(items)
    if not blk: return h
    p = re.compile(rf'(<div class="card" id="{cid}" style="padding:4px 16px;)[^"]*(")([^<]*)</div>')
    h2, n = p.subn(rf'\1\2>{blk}</div>', h, count=1)
    if n == 0: return h
    st = datetime.now(timezone(timedelta(hours=8))).strftime("%d %b, %I:%M %p")
    np_ = re.compile(rf'(<div class="section-note" id="{nid}">)[^<]*(</div>)')
    h2, _ = np_.subn(rf'\g<1>auto-updated {st} PHT\g<2>', h2, count=1)
    return h2

def inject_auto(h, flagged):
    st = datetime.now(timezone(timedelta(hours=8))).strftime("%d %b, %I:%M %p")
    if flagged:
        cards = []
        for it in flagged:
            m = DPAT.search(it)
            f = m.group(0) if m else "?"
            cards.append(f'<div class="autodate-card"><b>⚠ {escape(f)}</b> near a release word: "{escape(it[:140])}"</div>')
        lst = "\n".join(cards)
    else:
        lst = '<div class="autodate-empty">No unverified date mentions in the latest run.</div>'
    h2 = re.sub(r'(<div id="autoDateList">).*?(</div>\s*</div>\s*<div class="section">)', lambda m: m.group(1)+lst+m.group(2), h, count=1, flags=re.S)
    h2 = re.sub(r'(<div class="section-note" id="autoDateUpdatedNote">)[^<]*(</div>)', rf'\g<1>last run {st} PHT\g<2>', h2, count=1)
    return h2

def fetch_fx():
    urls = [
        "https://cdn.jsdelivr.net/npm/@fawazahmed0/currency-api@latest/v1/currencies/usd.json",
        "https://latest.currency-api.pages.dev/v1/currencies/usd.json",
    ]
    for u in urls:
        raw = fetch(u)
        if not raw: continue
        try:
            data = json.loads(raw)["usd"]
            php, jpy = data.get("php"), data.get("jpy")
            if php and jpy: return round(php, 2), round(php / jpy, 3)
        except Exception as e:
            print(f"WARN fx parse: {e}", file=sys.stderr)
    return None, None

def inject_fx(h, usd_php, jpy_php):
    if not usd_php: return h
    h = re.sub(r"const FX_USD_PHP = [\d.]+;", f"const FX_USD_PHP = {usd_php};", h, count=1)
    h = re.sub(r"const FX_JPY_PHP = [\d.]+;", f"const FX_JPY_PHP = {jpy_php};", h, count=1)
    h = re.sub(r"ref\. rate US\$1 \u2248 \u20b1[\d.]+ \u00b7 \u00a51 \u2248 \u20b1[\d.]+", f"ref. rate US$1 \u2248 \u20b1{usd_php} \u00b7 \u00a51 \u2248 \u20b1{jpy_php}", h, count=1)
    return h

def main():
    with open("index.html", encoding="utf-8") as f: h = f.read()
    poke, op = pkmn(), onepc()
    flagged = [i for i in poke+op if newdate(i)]
    usd_php, jpy_php = fetch_fx()
    print(f"Pokemon: {len(poke)}, OnePiece: {len(op)}, flagged: {len(flagged)}, FX: {usd_php}/{jpy_php}")
    h = inject(h, "pokemon-news-live", "pokeUpdatedNote", poke)
    h = inject(h, "onepiece-news-live", "opUpdatedNote", op)
    h = inject_auto(h, flagged)
    h = inject_fx(h, usd_php, jpy_php)
    with open("index.html", "w", encoding="utf-8") as f: f.write(h)
    print("index.html updated.")

if __name__ == "__main__": main()
