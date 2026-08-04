"""FX rate helper for APEX TCG Intel. Kept in its own file so each file
individually stays well under the size that pastes reliably in one shot."""
import re, json
import requests
from datetime import datetime, timezone, timedelta

def fetch_fx(fetch_func, headers, timeout):
    urls = [
        "https://cdn.jsdelivr.net/npm/@fawazahmed0/currency-api@latest/v1/currencies/usd.json",
        "https://latest.currency-api.pages.dev/v1/currencies/usd.json",
    ]
    dbg = []
    for u in urls:
        try:
            r = requests.get(u, headers=headers, timeout=timeout)
            dbg.append(f"{u.split('/')[2]}:HTTP{r.status_code}")
            r.raise_for_status()
            data = r.json()["usd"]
            php, jpy = data.get("php"), data.get("jpy")
            if php and jpy:
                return round(php, 2), round(php / jpy, 3), " | ".join(dbg) + " OK"
        except Exception as e:
            dbg.append(f"{u.split('/')[2]}:{type(e).__name__}:{str(e)[:60]}")
    return None, None, " | ".join(dbg)

def inject_fx(h, usd_php, jpy_php, dbg):
    stamp = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M PHT")
    comment = f"<!-- FX_DEBUG [{stamp}]: usd_php={usd_php} jpy_php={jpy_php} | {dbg} -->"
    if "<!-- FX_DEBUG" in h:
        h = re.sub(r"<!-- FX_DEBUG.*?-->", comment, h, count=1, flags=re.S)
    else:
        h = h.replace("<head>", "<head>\n" + comment, 1)
    if not usd_php: return h
    h = re.sub(r"const FX_USD_PHP = [\d.]+;", f"const FX_USD_PHP = {usd_php};", h, count=1)
    h = re.sub(r"const FX_JPY_PHP = [\d.]+;", f"const FX_JPY_PHP = {jpy_php};", h, count=1)
    h = re.sub(r"ref\. rate US\$1 \u2248 \u20b1[\d.]+ \u00b7 \u00a51 \u2248 \u20b1[\d.]+", f"ref. rate US$1 \u2248 \u20b1{usd_php} \u00b7 \u00a51 \u2248 \u20b1{jpy_php}", h, count=1)
    return h
