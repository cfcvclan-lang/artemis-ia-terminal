"""
ARTEMIS IA TERMINAL - backend de donnees (v2)
---------------------------------------------
Sert le terminal et son flux de marche depuis la meme origine, ce qui supprime
tout probleme de CORS et autorise un rafraichissement a 15 secondes.

v3 : cotations groupees via spark (deux formats acceptes), repli unitaire
via l'endpoint chart en parallele, puis Stooq.
v2 : appels Yahoo en direct (sans passer par le bootstrap cookie de yfinance,
qui echoue depuis les IP de datacenter), repli sur Stooq, puis sur yfinance.
L'endpoint /api/diag indique quelle source repond depuis l'hebergeur.

Deploiement Render (Web Service, plan gratuit) :
    Build   : pip install -r requirements.txt
    Start   : uvicorn main:app --host 0.0.0.0 --port $PORT
"""
from __future__ import annotations

import csv
import io
import os
import time
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional

import requests
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi import Response
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

app = FastAPI(title="Artemis IA Terminal API", version="6.0")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["GET"], allow_headers=["*"]
)

HERE = os.path.dirname(os.path.abspath(__file__))
PAGE = os.path.join(HERE, "ARTEMIS_IA_TERMINAL.html")


def page_path() -> str:
    """Un navigateur suffixe les telechargements repetes et GitHub cree alors un
    nouveau fichier au lieu de remplacer l'ancien. On retient donc la variante la
    plus recente plutot qu'un nom fige."""
    import glob as _glob
    import re as _re
    cands = _glob.glob(os.path.join(HERE, "ARTEMIS_IA_TERMINAL*.htm*"))
    if not cands:
        return PAGE

    def rank(p):
        m = _re.search(r"[_ -]\(?(\d+)\)?\.html?$", os.path.basename(p))
        return (int(m.group(1)) if m else 0, os.path.getmtime(p))

    return max(cands, key=rank)

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36")
S = requests.Session()
S.headers.update({
    "User-Agent": UA,
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8",
})

YH_HOSTS = ("https://query1.finance.yahoo.com", "https://query2.finance.yahoo.com")
_crumb = {"v": None, "at": 0.0}


def yh_crumb() -> Optional[str]:
    """Jeton exige par l'endpoint analystes. Souvent refuse depuis un hebergeur."""
    if _crumb["v"] and time.time() - _crumb["at"] < 3600:
        return _crumb["v"]
    for seed in ("https://finance.yahoo.com/quote/AAPL", "https://fc.yahoo.com"):
        try:
            S.get(seed, timeout=8)
        except Exception:
            continue
    for host in YH_HOSTS:
        try:
            r = S.get(host + "/v1/test/getcrumb", timeout=8)
            if r.status_code == 200 and r.text and len(r.text) < 40:
                _crumb["v"] = r.text.strip()
                _crumb["at"] = time.time()
                return _crumb["v"]
        except Exception:
            continue
    return None

# ----------------------------------------------------------------- cache
_lock = threading.Lock()
_cache: Dict[str, Any] = {}

def cache_get(key: str, ttl: float):
    with _lock:
        hit = _cache.get(key)
    return hit[1] if hit and time.time() - hit[0] < ttl else None

def cache_put(key: str, value):
    with _lock:
        _cache[key] = (time.time(), value)

# ----------------------------------------------------------------- Yahoo direct
def yh(path: str, params: dict, timeout: float = 12.0, hosts=None):
    last = "aucune tentative"
    for host in (hosts or YH_HOSTS):
        try:
            r = S.get(host + path, params=params, timeout=timeout)
            if r.status_code == 200:
                return r.json()
            last = f"{host.split('//')[1][:7]} HTTP {r.status_code}"
        except Exception as exc:
            last = f"{host.split('//')[1][:7]} {type(exc).__name__}"
    raise RuntimeError(last)

def _spark_row(sym, r, out):
    """Accepte les deux formats renvoyes par Yahoo : objet a plat, ou imbrique."""
    if not isinstance(r, dict):
        return
    meta = None
    resp = r.get("response")
    if isinstance(resp, list) and resp:
        meta = resp[0].get("meta") or {}
    sym = r.get("symbol") or sym or (meta or {}).get("symbol")
    if not sym:
        return
    closes = r.get("close")
    if closes is None and isinstance(resp, list) and resp:
        try:
            closes = (resp[0].get("indicators", {}).get("quote") or [{}])[0].get("close")
        except Exception:
            closes = None
    last = (meta or {}).get("regularMarketPrice")
    if last is None and isinstance(closes, list):
        for v in reversed(closes):
            if v is not None:
                last = v
                break
    if last is None:
        return
    pc = r.get("chartPreviousClose")
    if pc is None:
        pc = r.get("previousClose")
    if pc is None and meta:
        pc = meta.get("chartPreviousClose") or meta.get("previousClose")
    out[sym] = {
        "p": float(last),
        "pc": _f(pc),
        "vol": _f((meta or {}).get("regularMarketVolume")),
        "hi": _f((meta or {}).get("regularMarketDayHigh")),
        "lo": _f((meta or {}).get("regularMarketDayLow")),
        "op": None,
        "cur": (meta or {}).get("currency"),
        "t": int(time.time() * 1000),
        "src": "yahoo",
    }


def yh_spark(syms: List[str]) -> Dict[str, dict]:
    j = yh("/v8/finance/spark",
           {"symbols": ",".join(syms), "range": "1d", "interval": "5m"})
    out: Dict[str, dict] = {}
    if isinstance(j, dict) and "spark" in j:
        for r in (j.get("spark") or {}).get("result") or []:
            _spark_row(None, r, out)
    elif isinstance(j, dict):
        for k, v in j.items():
            _spark_row(k, v, out)
    elif isinstance(j, list):
        for r in j:
            _spark_row(None, r, out)
    return out


def yh_quote_via_chart(sym: str) -> Optional[dict]:
    """Repli unitaire : l'endpoint chart porte le meta complet (cours, volume, bornes)."""
    try:
        j = yh("/v8/finance/chart/" + sym, {"range": "1d", "interval": "5m"},
               timeout=5.0, hosts=YH_HOSTS[:1])
        res = (j.get("chart") or {}).get("result") or []
        if not res:
            return None
        meta = res[0].get("meta") or {}
        last = meta.get("regularMarketPrice")
        if last is None:
            return None
        return {"p": float(last),
                "pc": _f(meta.get("chartPreviousClose") or meta.get("previousClose")),
                "vol": _f(meta.get("regularMarketVolume")),
                "hi": _f(meta.get("regularMarketDayHigh")),
                "lo": _f(meta.get("regularMarketDayLow")),
                "op": None, "cur": meta.get("currency"),
                "t": int(time.time() * 1000), "src": "yahoo-chart"}
    except Exception:
        return None


def yh_chart(sym: str, rng: str, interval: str) -> dict:
    j = yh(f"/v8/finance/chart/{sym}", {"range": rng, "interval": interval})
    res = (j.get("chart") or {}).get("result") or []
    if not res:
        raise RuntimeError("chart vide")
    r = res[0]
    closes = (r.get("indicators", {}).get("quote") or [{}])[0].get("close") or []
    stamps = r.get("timestamp") or []
    T, C = [], []
    for i, ts in enumerate(stamps):
        c = closes[i] if i < len(closes) else None
        if c is not None:
            T.append(int(ts) * 1000)
            C.append(float(c))
    return {"t": T, "c": C, "at": int(time.time() * 1000), "src": "yahoo"}

def _f(v):
    try:
        return float(v) if v is not None else None
    except Exception:
        return None

# ----------------------------------------------------------------- Stooq (repli)
STOOQ_SUFFIX = {".PA": ".fr", ".DE": ".de", ".L": ".uk", ".AS": ".nl",
                ".MI": ".it", ".MC": ".es", ".SW": ".ch", ".CO": ".dk",
                ".OL": ".no", ".ST": ".se", ".VI": ".at", ".BR": ".be"}
STOOQ_INDEX = {"^GSPC": "^spx", "^NDX": "^ndx", "^DJI": "^dji", "^GDAXI": "^dax",
               "^FCHI": "^cac", "^FTSE": "^ukx", "^IBEX": "^ibex", "^SSMI": "^smi",
               "^N225": "^nkx", "^STOXX50E": "^sx5e"}

def stooq_symbol(sym: str) -> Optional[str]:
    if sym in STOOQ_INDEX:
        return STOOQ_INDEX[sym]
    if sym.endswith("=X"):
        return sym[:-2].lower()
    if sym.endswith("=F") or sym.startswith("^"):
        return None
    for suf, repl in STOOQ_SUFFIX.items():
        if sym.endswith(suf):
            return sym[: -len(suf)].lower().replace("-", "") + repl
    if "." not in sym:
        return sym.lower() + ".us"
    return None

def stooq_quotes(syms: List[str]) -> Dict[str, dict]:
    pairs = [(s, stooq_symbol(s)) for s in syms]
    pairs = [(a, b) for a, b in pairs if b]
    if not pairs:
        return {}
    out: Dict[str, dict] = {}
    for i in range(0, len(pairs), 20):
        grp = pairs[i:i + 20]
        try:
            r = S.get("https://stooq.com/q/l/",
                      params={"s": ",".join(b for _, b in grp),
                              "f": "sd2t2ohlcv", "h": "", "e": "csv"}, timeout=12)
            if r.status_code != 200:
                continue
            back = {b: a for a, b in grp}
            for row in csv.DictReader(io.StringIO(r.text)):
                sym = back.get((row.get("Symbol") or "").lower())
                close = _f(row.get("Close"))
                if not sym or close is None:
                    continue
                op = _f(row.get("Open"))
                out[sym] = {"p": close, "pc": op, "vol": _f(row.get("Volume")),
                            "hi": _f(row.get("High")), "lo": _f(row.get("Low")),
                            "op": op, "cur": None,
                            "t": int(time.time() * 1000), "src": "stooq"}
        except Exception:
            continue
    return out

def stooq_history(sym: str) -> dict:
    s = stooq_symbol(sym)
    if not s:
        raise RuntimeError("symbole non mappe")
    r = S.get("https://stooq.com/q/d/l/", params={"s": s, "i": "d"}, timeout=15)
    if r.status_code != 200 or not r.text.startswith("Date"):
        raise RuntimeError(f"stooq HTTP {r.status_code}")
    T, C = [], []
    for row in csv.DictReader(io.StringIO(r.text)):
        c = _f(row.get("Close"))
        if c is None:
            continue
        try:
            ts = time.mktime(time.strptime(row["Date"], "%Y-%m-%d")) * 1000
        except Exception:
            continue
        T.append(int(ts))
        C.append(c)
    if not C:
        raise RuntimeError("stooq vide")
    return {"t": T[-1300:], "c": C[-1300:], "at": int(time.time() * 1000), "src": "stooq"}

# ----------------------------------------------------------------- routes
QUOTE_TTL = 20.0
FAIL_TTL = 900.0  # un symbole introuvable n'est pas retente avant ce delai
HIST_TTL = 900.0
CONS_TTL = 21600.0

def chunks(a, n):
    return [a[i:i + n] for i in range(0, len(a), n)]

def _safe_spark(grp: List[str]) -> Dict[str, dict]:
    try:
        return yh_spark(grp)
    except Exception:
        return {}


@app.get("/api/quotes")
def quotes(symbols: str = Query(..., description="liste separee par des virgules")):
    syms = [s.strip() for s in symbols.split(",") if s.strip()][:400]
    out: Dict[str, dict] = {}
    todo: List[str] = []
    for s in syms:
        hit = cache_get("q:" + s, QUOTE_TTL)
        if hit:
            out[s] = hit
        elif cache_get("x:" + s, FAIL_TTL) is None:
            todo.append(s)
    if not todo:
        return JSONResponse(out, headers={"Cache-Control": "no-store"})

    try:
        with ThreadPoolExecutor(max_workers=6) as pool:
            for res in pool.map(_safe_spark, chunks(todo, 50)):
                out.update(res)
    except Exception:
        pass

    missing = [s for s in todo if s not in out]
    tried = set()
    if missing:
        batch = missing[:60]
        tried.update(batch)
        try:
            with ThreadPoolExecutor(max_workers=16) as pool:
                for sym, rec in zip(batch, pool.map(yh_quote_via_chart, batch)):
                    if rec:
                        out[sym] = rec
        except Exception:
            pass
    missing = [s for s in todo if s not in out]
    if missing:
        try:
            out.update(stooq_quotes(missing))
        except Exception:
            pass

    for s in todo:
        if s in out:
            cache_put("q:" + s, out[s])
        elif s in tried:
            # teste et introuvable : on cesse de le redemander a chaque cycle
            cache_put("x:" + s, True)
    return JSONResponse(out, headers={"Cache-Control": "no-store"})

RANGE_MAP = {"1d": ("1d", "5m"), "5d": ("5d", "30m"), "1mo": ("1mo", "1d"),
             "6mo": ("6mo", "1d"), "ytd": ("ytd", "1d"), "1y": ("1y", "1d"),
             "3y": ("3y", "1d"), "5y": ("5y", "1d")}

@app.get("/api/history")
def history(symbol: str, range: str = "5y"):
    key = f"h:{symbol}:{range}"
    hit = cache_get(key, HIST_TTL)
    if hit:
        return JSONResponse(hit, headers={"Cache-Control": "no-store"})
    rng, interval = RANGE_MAP.get(range, ("5y", "1d"))
    payload = None
    try:
        payload = yh_chart(symbol, rng, interval)
        if not payload["c"]:
            payload = None
    except Exception:
        payload = None
    if payload is None and interval == "1d":
        try:
            payload = stooq_history(symbol)
        except Exception:
            payload = None
    if payload is None:
        payload = {"t": [], "c": [], "at": int(time.time() * 1000), "src": "none"}
    cache_put(key, payload)
    return JSONResponse(payload, headers={"Cache-Control": "no-store"})

def yh_dividends(sym: str) -> Dict[str, Any]:
    """Rendement du dividende reconstitue depuis les evenements du graphique."""
    j = yh("/v8/finance/chart/" + sym,
           {"range": "2y", "interval": "1d", "events": "div"}, timeout=10.0)
    res = (j.get("chart") or {}).get("result") or []
    if not res:
        return {}
    r = res[0]
    meta = r.get("meta") or {}
    price = _f(meta.get("regularMarketPrice"))
    divs = ((r.get("events") or {}).get("dividends") or {})
    rows = []
    for ev in divs.values():
        ts, amt = _f(ev.get("date")), _f(ev.get("amount"))
        if ts and amt:
            rows.append((ts, amt))
    rows.sort()
    cut = time.time() - 366 * 86400
    ttm = sum(a for ts, a in rows if ts >= cut)
    out: Dict[str, Any] = {
        "divTtm": ttm or None,
        "divYield": (ttm / price * 100) if (ttm and price) else None,
        "divLast": rows[-1][1] if rows else None,
        "divLastDate": int(rows[-1][0] * 1000) if rows else None,
        "divCount": len([1 for ts, _ in rows if ts >= cut]),
    }
    closes = (r.get("indicators", {}).get("quote") or [{}])[0].get("close") or []
    stamps = r.get("timestamp") or []
    yr = time.time() - 366 * 86400
    win = [c for i, c in enumerate(closes) if c is not None and i < len(stamps) and stamps[i] >= yr]
    if win:
        out["hi52"] = max(win)
        out["lo52"] = min(win)
    out["price"] = price
    return out


@app.get("/api/consensus")
def consensus(symbol: str):
    key = "c:" + symbol
    hit = cache_get(key, CONS_TTL)
    if hit is not None:
        return JSONResponse(hit, headers={"Cache-Control": "no-store"})
    payload: Dict[str, Any] = {}
    try:
        payload.update(yh_dividends(symbol))
    except Exception:
        pass
    try:
        params = {"modules": "financialData,recommendationTrend,summaryDetail"}
        cr = yh_crumb()
        if cr:
            params["crumb"] = cr
        j = yh(f"/v10/finance/quoteSummary/{symbol}", params)
        res = (j.get("quoteSummary") or {}).get("result") or []
        if res:
            f = res[0].get("financialData") or {}
            tr = ((res[0].get("recommendationTrend") or {}).get("trend") or [{}])[0]
            payload.update({
                "mean": (f.get("recommendationMean") or {}).get("raw"),
                "key": f.get("recommendationKey"),
                "target": (f.get("targetMeanPrice") or {}).get("raw"),
                "low": (f.get("targetLowPrice") or {}).get("raw"),
                "high": (f.get("targetHighPrice") or {}).get("raw"),
                "n": (f.get("numberOfAnalystOpinions") or {}).get("raw"),
                "buy": int(tr.get("strongBuy") or 0) + int(tr.get("buy") or 0),
                "hold": int(tr.get("hold") or 0),
                "sell": int(tr.get("sell") or 0) + int(tr.get("strongSell") or 0),
            })
    except Exception:
        pass
    cache_put(key, payload)
    return JSONResponse(payload, headers={"Cache-Control": "no-store"})

@app.get("/api/diag")
def diag():
    """Indique quelle source repond depuis cet hebergeur."""
    report: Dict[str, Any] = {"host": os.environ.get("RENDER_EXTERNAL_URL", "local")}
    try:
        q = yh_spark(["AAPL", "MC.PA", "^FCHI"])
        report["yahoo_spark"] = {"ok": bool(q), "n": len(q),
                                 "sample": {k: v["p"] for k, v in list(q.items())[:3]}}
    except Exception as exc:
        report["yahoo_spark"] = {"ok": False, "err": str(exc)[:160]}
    try:
        raw = yh("/v8/finance/spark",
                 {"symbols": "AAPL,MC.PA", "range": "1d", "interval": "5m"})
        report["spark_shape"] = {"type": type(raw).__name__,
                                 "keys": list(raw)[:6] if isinstance(raw, dict) else len(raw)}
    except Exception as exc:
        report["spark_shape"] = str(exc)[:120]
    try:
        r = yh_quote_via_chart("MC.PA")
        report["chart_quote"] = r or "vide"
    except Exception as exc:
        report["chart_quote"] = str(exc)[:160]
    try:
        h = yh_chart("AAPL", "1mo", "1d")
        report["yahoo_chart"] = {"ok": bool(h["c"]), "points": len(h["c"])}
    except Exception as exc:
        report["yahoo_chart"] = {"ok": False, "err": str(exc)[:160]}
    try:
        q = stooq_quotes(["AAPL", "MC.PA"])
        report["stooq"] = {"ok": bool(q), "n": len(q),
                           "sample": {k: v["p"] for k, v in q.items()}}
    except Exception as exc:
        report["stooq"] = {"ok": False, "err": str(exc)[:160]}
    try:
        r = S.get("https://query1.finance.yahoo.com/v8/finance/chart/AAPL",
                  params={"range": "1d", "interval": "5m"}, timeout=10)
        report["yahoo_raw_status"] = r.status_code
    except Exception as exc:
        report["yahoo_raw_status"] = f"{type(exc).__name__}"
    try:
        report["page"] = os.path.basename(page_path())
    except Exception as exc:
        report["page"] = str(exc)[:60]
    try:
        report["crumb"] = bool(yh_crumb())
    except Exception as exc:
        report["crumb"] = str(exc)[:80]
    try:
        report["dividendes"] = yh_dividends("MC.PA")
    except Exception as exc:
        report["dividendes"] = str(exc)[:120]
    return JSONResponse(report, headers={"Cache-Control": "no-store"})


ICON_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">'
    '<rect width="512" height="512" rx="112" fill="#050607" stroke="#8a5a14" stroke-width="8"/>'
    '<text x="256" y="268" font-family="monospace" font-size="248" font-weight="700"'
    ' fill="#ffa028" text-anchor="middle">A</text>'
    '<path d="M112 410 L170 380 L228 396 L286 344 L344 366 L402 300"'
    ' fill="none" stroke="#00d46a" stroke-width="20" stroke-linecap="round" stroke-linejoin="round"/>'
    '<circle cx="402" cy="300" r="18" fill="#00d46a"/></svg>'
)

MANIFEST_JSON = {
    "name": "ARTEMIS IA TERMINAL",
    "short_name": "ARTEMIS IA",
    "id": "/",
    "start_url": "/",
    "scope": "/",
    "display": "standalone",
    "background_color": "#000000",
    "theme_color": "#ffa028",
    "lang": "fr",
    "icons": [
        {"src": "/icon.svg", "sizes": "any", "type": "image/svg+xml", "purpose": "any"},
        {"src": "/icon.svg", "sizes": "any", "type": "image/svg+xml", "purpose": "maskable"},
    ],
}

SW_JS = """
const CACHE = "artemis-ia-v5";
const SHELL = ["/", "/manifest.webmanifest", "/icon.svg"];
self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});
self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys()
    .then((ks) => Promise.all(ks.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
    .then(() => self.clients.claim()));
});
self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;
  if (url.pathname.startsWith("/api/") || url.pathname === "/health") return;
  if (req.mode === "navigate") {
    e.respondWith(fetch(req).then((r) => {
      const copy = r.clone();
      caches.open(CACHE).then((c) => c.put("/", copy));
      return r;
    }).catch(() => caches.match("/").then((r) => r || Response.error())));
    return;
  }
  e.respondWith(caches.match(req).then((hit) => hit || fetch(req)));
});
"""

PWA_HEAD = (
    '<link rel="manifest" href="/manifest.webmanifest">'
    '<meta name="theme-color" content="#ffa028">'
    '<link rel="icon" type="image/svg+xml" href="/icon.svg">'
    '<link rel="apple-touch-icon" href="/icon.svg">'
    '<meta name="apple-mobile-web-app-capable" content="yes">'
    '<meta name="mobile-web-app-capable" content="yes">'
    '<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">'
    '<meta name="apple-mobile-web-app-title" content="ARTEMIS IA">'
)

PWA_TAIL = (
    "<script>if(location.protocol.indexOf('http')===0&&'serviceWorker' in navigator){"
    "window.addEventListener('load',function(){"
    "navigator.serviceWorker.register('/sw.js').catch(function(){});});}</script>"
)


def page_html() -> str:
    """Sert la page en corrigeant au vol ce qui doit l'etre, sans dependre du fichier depose."""
    with open(page_path(), "r", encoding="utf-8") as fh:
        html = fh.read()
    html = html.replace(",12000)", ",60000)")
    html = html.replace(",25000)", ",60000)")
    if "manifest.webmanifest" not in html:
        html = html.replace("</head>", PWA_HEAD + "</head>", 1)
        html = html.replace("</body>", PWA_TAIL + "</body>", 1)
    return html


@app.get("/manifest.webmanifest")
def manifest():
    return JSONResponse(MANIFEST_JSON, media_type="application/manifest+json")


@app.get("/icon.svg")
def icon_svg():
    return Response(ICON_SVG, media_type="image/svg+xml",
                    headers={"Cache-Control": "public, max-age=86400"})


@app.get("/sw.js")
def service_worker():
    return Response(SW_JS, media_type="application/javascript",
                    headers={"Service-Worker-Allowed": "/", "Cache-Control": "no-cache"})


@app.get("/")
def index():
    if os.path.exists(page_path()):
        return HTMLResponse(page_html())
    return JSONResponse({"ok": True, "msg": "Poser ARTEMIS_IA_TERMINAL.html a cote de main.py."})

@app.get("/health")
def health():
    return {"ok": True, "ts": int(time.time() * 1000)}
