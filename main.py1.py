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
import json
import re
import os
import time
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional

import requests
from fastapi import FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi import Response
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse

# La couche comptes est facultative : si comptes.py ou accueil.py ne sont pas
# deposes a cote de main.py, le terminal doit rester en acces libre plutot que
# de refuser de demarrer.
try:
    import comptes
    from accueil import ACCUEIL
    COMPTES_DISPO = True
except Exception as _e:          # pragma: no cover
    comptes = None
    ACCUEIL = ""
    COMPTES_DISPO = False
    MOTIF_COMPTES = str(_e)
else:
    MOTIF_COMPTES = ""

app = FastAPI(title="Artemis IA Terminal API", version="9.0")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["GET"], allow_headers=["*"]
)

if COMPTES_DISPO:
    comptes.init()


def _ouvert() -> bool:
    """Sans module de comptes ou sans administrateur configure, acces libre."""
    if not COMPTES_DISPO:
        return True
    return not bool(os.environ.get("ADMIN_EMAIL") and os.environ.get("ADMIN_PASSWORD"))


def _moi(request: Request):
    if not COMPTES_DISPO:
        return None
    return comptes.utilisateur_du_jeton(request.cookies.get(comptes.COOKIE))


LIBRES = ("/health", "/auth/", "/manifest.webmanifest", "/icon.svg", "/sw.js", "/favicon.ico")


@app.middleware("http")
async def verrou(request: Request, call_next):
    chemin = request.url.path
    if not COMPTES_DISPO and (chemin.startswith("/auth/") or chemin.startswith("/admin/")
                              or chemin.startswith("/cfg")):
        return JSONResponse(
            {"ok": False, "erreur": "Gestion des comptes indisponible : deposer comptes.py "
                                    "et accueil.py a cote de main.py.", "motif": MOTIF_COMPTES},
            status_code=503)
    if _ouvert() or chemin.startswith(LIBRES):
        return await call_next(request)
    if chemin in ("/", "/terminal") or chemin.startswith("/api/") \
            or chemin.startswith("/admin/") or chemin.startswith("/cfg"):
        u = _moi(request)
        if not u:
            if chemin == "/":
                return HTMLResponse(ACCUEIL)
            if chemin == "/terminal":
                return RedirectResponse("/", status_code=303)
            return JSONResponse({"detail": "Authentification requise"}, status_code=401)
        if chemin.startswith("/admin/") and u["role"] != "admin":
            return JSONResponse({"detail": "Reserve a l'administrateur"}, status_code=403)
        request.state.moi = u
    return await call_next(request)

HERE = os.path.dirname(os.path.abspath(__file__))
PAGE = os.path.join(HERE, "ARTEMIS_IA_TERMINAL.html")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36")
S = requests.Session()
S.headers.update({
    "User-Agent": UA,
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8",
})

YH_HOSTS = ("https://query1.finance.yahoo.com", "https://query2.finance.yahoo.com")

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
    q0 = (r.get("indicators", {}).get("quote") or [{}])[0]
    closes = q0.get("close") or []
    vols = q0.get("volume") or []
    highs = q0.get("high") or []
    lows = q0.get("low") or []
    stamps = r.get("timestamp") or []
    T, C, V, HI, LO = [], [], [], [], []
    for i, ts in enumerate(stamps):
        c = closes[i] if i < len(closes) else None
        if c is None:
            continue
        T.append(int(ts) * 1000)
        C.append(float(c))
        V.append(float(vols[i]) if i < len(vols) and vols[i] is not None else None)
        HI.append(float(highs[i]) if i < len(highs) and highs[i] is not None else None)
        LO.append(float(lows[i]) if i < len(lows) and lows[i] is not None else None)
    return {"t": T, "c": C, "v": V, "hi": HI, "lo": LO,
            "at": int(time.time() * 1000), "src": "yahoo"}

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

@app.get("/api/consensus")
def consensus(symbol: str):
    key = "c:" + symbol
    hit = cache_get(key, CONS_TTL)
    if hit is not None:
        return JSONResponse(hit, headers={"Cache-Control": "no-store"})
    payload: Dict[str, Any] = {}
    try:
        j = yh(f"/v10/finance/quoteSummary/{symbol}",
               {"modules": "financialData,recommendationTrend"})
        res = (j.get("quoteSummary") or {}).get("result") or []
        if res:
            f = res[0].get("financialData") or {}
            tr = ((res[0].get("recommendationTrend") or {}).get("trend") or [{}])[0]
            payload = {
                "mean": (f.get("recommendationMean") or {}).get("raw"),
                "key": f.get("recommendationKey"),
                "target": (f.get("targetMeanPrice") or {}).get("raw"),
                "low": (f.get("targetLowPrice") or {}).get("raw"),
                "high": (f.get("targetHighPrice") or {}).get("raw"),
                "n": (f.get("numberOfAnalystOpinions") or {}).get("raw"),
                "buy": int(tr.get("strongBuy") or 0) + int(tr.get("buy") or 0),
                "hold": int(tr.get("hold") or 0),
                "sell": int(tr.get("sell") or 0) + int(tr.get("strongSell") or 0),
            }
    except Exception:
        payload = {}
    cache_put(key, payload)
    return JSONResponse(payload, headers={"Cache-Control": "no-store"})


# ----------------------------------------------------------------- taux
ECB = "https://data-api.ecb.europa.eu/service/data/"
RATES_TTL = 7200.0

# flux BCE : (code, libelle, flowRef, cle, famille)
ECB_SERIES = [
    ("ESTR",      "\u20acSTR",             "EST", "B.EU000A2X2A25.WT",                   "court"),
    ("EURIBOR1M", "Euribor 1 mois",      "FM",  "D.U2.EUR.RT.MM.EURIBOR1MD_.HSTA",     "court"),
    ("EURIBOR3M", "Euribor 3 mois",      "FM",  "M.U2.EUR.RT.MM.EURIBOR3MD_.HSTA",     "court"),
    ("EURIBOR6M", "Euribor 6 mois",      "FM",  "M.U2.EUR.RT.MM.EURIBOR6MD_.HSTA",     "court"),
    ("EURIBOR12M","Euribor 12 mois",     "FM",  "M.U2.EUR.RT.MM.EURIBOR1YD_.HSTA",     "court"),
    ("EUR_AAA_1Y","Courbe AAA 1 an",     "YC",  "B.U2.EUR.4F.G_N_A.SV_C_YM.SR_1Y",     "courbe"),
    ("EUR_AAA_2Y","Courbe AAA 2 ans",    "YC",  "B.U2.EUR.4F.G_N_A.SV_C_YM.SR_2Y",     "courbe"),
    ("EUR_AAA_5Y","Courbe AAA 5 ans",    "YC",  "B.U2.EUR.4F.G_N_A.SV_C_YM.SR_5Y",     "courbe"),
    ("EUR_AAA_10Y","Courbe AAA 10 ans",  "YC",  "B.U2.EUR.4F.G_N_A.SV_C_YM.SR_10Y",    "courbe"),
    ("EUR_AAA_30Y","Courbe AAA 30 ans",  "YC",  "B.U2.EUR.4F.G_N_A.SV_C_YM.SR_30Y",    "courbe"),
    ("EUR_ALL_10Y","Toutes notations 10 ans", "YC", "B.U2.EUR.4F.G_N_C.SV_C_YM.SR_10Y", "courbe"),
    ("FR_10Y",    "France 10 ans",       "IRS", "M.FR.L.L40.CI.0000.EUR.N.Z",          "souverain"),
    ("DE_10Y_M",   "Allemagne 10 ans",     "IRS", "M.DE.L.L40.CI.0000.EUR.N.Z",        "souverain"),
    ("IT_10Y",    "Italie 10 ans",       "IRS", "M.IT.L.L40.CI.0000.EUR.N.Z",          "souverain"),
    ("ES_10Y",    "Espagne 10 ans",      "IRS", "M.ES.L.L40.CI.0000.EUR.N.Z",          "souverain"),
]

# taux americains : cotes en continu chez Yahoo
US_SERIES = [("US_3M", "Etats-Unis 3 mois", "^IRX", 0.25),
             ("US_5Y", "Etats-Unis 5 ans", "^FVX", 5.0),
             ("US_10Y", "Etats-Unis 10 ans", "^TNX", 10.0),
             ("US_30Y", "Etats-Unis 30 ans", "^TYX", 30.0)]

ECHEANCE = {"EUR_AAA_1Y": 1.0, "EUR_AAA_2Y": 2.0, "EUR_AAA_5Y": 5.0,
            "EUR_AAA_10Y": 10.0, "EUR_AAA_30Y": 30.0,
            "ESTR": 0.003, "MRO": 0.0, "DFR": 0.0, "EURIBOR1M": 0.08, "EURIBOR3M": 0.25,
            "EURIBOR6M": 0.5, "EURIBOR12M": 1.0}


BBK = "https://api.statistiken.bundesbank.de/rest/data/"
BBK_SERIES = [
    ("DE_1Y",  "Allemagne 1 an",   "D.I.ZST.ZI.EUR.S1311.B.A604.R01XX.R.A.A._Z._Z.A", 1.0),
    ("DE_2Y",  "Allemagne 2 ans",  "D.I.ZST.ZI.EUR.S1311.B.A604.R02XX.R.A.A._Z._Z.A", 2.0),
    ("DE_5Y",  "Allemagne 5 ans",  "D.I.ZST.ZI.EUR.S1311.B.A604.R05XX.R.A.A._Z._Z.A", 5.0),
    ("DE_10Y", "Allemagne 10 ans", "D.I.ZST.ZI.EUR.S1311.B.A604.R10XX.R.A.A._Z._Z.A", 10.0),
    ("DE_30Y", "Allemagne 30 ans", "D.I.ZST.ZI.EUR.S1311.B.A604.R30XX.R.A.A._Z._Z.A", 30.0),
]


def bbk_series(key: str, n: int = 420):
    """Observations quotidiennes de la Bundesbank, de la plus ancienne a la plus recente."""
    r = S.get(BBK + "BBSIS/" + key,
              params={"format": "csv", "lang": "en", "lastNObservations": n}, timeout=20)
    if r.status_code != 200 or not r.text:
        raise RuntimeError("BBK HTTP " + str(r.status_code))
    out = []
    for line in r.text.splitlines():
        parts = line.split(",")
        if len(parts) >= 2 and len(parts[0]) == 10 and parts[0][4] == "-":
            v = _f(parts[1])
            if v is not None:
                out.append((parts[0], v))
    out.sort()
    if not out:
        raise RuntimeError("serie vide")
    return out


def _une_serie_bbk(spec):
    code, lib, key, ans = spec
    try:
        obs = bbk_series(key)
        return code, {"label": lib, "famille": "allemagne", "src": "Bundesbank",
                      "freq": "quotidien", "v": obs[-1][1], "date": obs[-1][0],
                      "d": _delta(obs, 1), "w": _delta(obs, 7),
                      "m": _delta(obs, 30), "ytd": _delta(obs, "ytd"), "annees": ans}
    except Exception as exc:
        return code, {"label": lib, "famille": "allemagne", "src": "Bundesbank",
                      "freq": "quotidien", "err": str(exc)[:90], "annees": ans}


def ecb_series(flow: str, key: str, n: int = 420):
    """Observations BCE, du plus ancien au plus recent, en (date, valeur)."""
    url = ECB + flow + "/" + key
    r = S.get(url, params={"format": "csvdata", "detail": "dataonly",
                           "lastNObservations": n}, timeout=20)
    if r.status_code != 200 or not r.text:
        raise RuntimeError("BCE HTTP " + str(r.status_code))
    rows = list(csv.DictReader(io.StringIO(r.text)))
    out = []
    for row in rows:
        d, v = row.get("TIME_PERIOD"), _f(row.get("OBS_VALUE"))
        if d and v is not None:
            out.append((d, v))
    out.sort()
    if not out:
        raise RuntimeError("serie vide")
    return out


def _delta(obs, jours):
    """Variation en points de base sur la fenetre demandee."""
    if len(obs) < 2:
        return None
    import datetime as _dt
    try:
        fin = _dt.date.fromisoformat(obs[-1][0][:10])
    except Exception:
        return None
    if jours == "ytd":
        cible = _dt.date(fin.year, 1, 1)
    else:
        cible = fin - _dt.timedelta(days=jours)
    ref = None
    for d, v in obs:
        try:
            dd = _dt.date.fromisoformat(d[:10])
        except Exception:
            continue
        if dd <= cible:
            ref = v
    if ref is None:
        ref = obs[0][1]
    return (obs[-1][1] - ref) * 100.0


def _une_serie_ecb(spec):
    code, lib, flow, key, fam = spec
    try:
        obs = ecb_series(flow, key)
        return code, {"label": lib, "famille": fam, "src": "BCE",
                      "freq": ("mensuel" if key.startswith("M.") else "quotidien"),
                      "v": obs[-1][1], "date": obs[-1][0],
                      "d": _delta(obs, 1), "w": _delta(obs, 7),
                      "m": _delta(obs, 30), "ytd": _delta(obs, "ytd"),
                      "annees": ECHEANCE.get(code)}
    except Exception as exc:
        return code, {"label": lib, "famille": fam, "src": "BCE",
                      "freq": ("mensuel" if key.startswith("M.") else "quotidien"),
                      "err": str(exc)[:90], "annees": ECHEANCE.get(code)}


def _une_serie_us(spec):
    code, lib, sym, ans = spec
    try:
        h = yh_chart(sym, "1y", "1d")
        c, t = h["c"], h["t"]
        if not c:
            raise RuntimeError("vide")
        import datetime as _dt
        obs = [(_dt.datetime.utcfromtimestamp(t[i] / 1000).date().isoformat(), c[i])
               for i in range(len(c))]
        return code, {"label": lib, "famille": "etatsunis", "src": "Yahoo",
                      "freq": "intraday", "v": c[-1], "date": obs[-1][0],
                      "d": _delta(obs, 1), "w": _delta(obs, 7),
                      "m": _delta(obs, 30), "ytd": _delta(obs, "ytd"),
                      "annees": ans}
    except Exception as exc:
        return code, {"label": lib, "famille": "etatsunis", "src": "Yahoo",
                      "freq": "intraday", "err": str(exc)[:90], "annees": ans}


@app.get("/api/rates")
def rates():
    hit = cache_get("rates", RATES_TTL)
    if hit:
        return JSONResponse(hit, headers={"Cache-Control": "no-store"})
    series: Dict[str, Any] = {}
    try:
        with ThreadPoolExecutor(max_workers=8) as pool:
            for code, rec in pool.map(_une_serie_ecb, ECB_SERIES):
                series[code] = rec
            for code, rec in pool.map(_une_serie_us, US_SERIES):
                series[code] = rec
            for code, rec in pool.map(_une_serie_bbk, BBK_SERIES):
                series[code] = rec
    except Exception:
        pass
    payload = {"asof": int(time.time() * 1000), "series": series}
    if series:
        cache_put("rates", payload)
    return JSONResponse(payload, headers={"Cache-Control": "no-store"})


# ----------------------------------------------------------------- actualites
NEWS_TTL = 900.0
FLUX_MACRO = [
    # presse de marche francophone, flux publics de syndication
    ("Les Echos marches", "https://feeds.feedburner.com/lesechos/4MR4suAcqTl"),
    ("Les Echos valeurs", "https://feeds.feedburner.com/lesechos/BrFLB6ZLde7"),
    ("Les Echos economie", "https://services.lesechos.fr/rss/les-echos-economie.xml"),
    ("Investing marches", "https://fr.investing.com/rss/market_overview.rss"),
    ("Investing actions", "https://fr.investing.com/rss/news_25.rss"),
    ("AGEFI marches actions", "https://www.agefi.fr/theme/marches-actions.rss"),
    ("AGEFI marches obligataires", "https://www.agefi.fr/theme/marches-obligataires.rss"),
    ("AGEFI economie marches", "https://www.agefi.fr/news/economie-marches.rss"),
    ("ABC Bourse", "https://www.abcbourse.com/rss/displaynewsrss"),
    ("BFM Bourse", "https://www.tradingsat.com/rssbourse.xml"),
    ("Le Figaro Bourse", "https://www.lefigaro.fr/rss/figaro_bourse.xml"),
    ("Le Monde economie", "https://www.lemonde.fr/economie/rss_full.xml"),
]
_RE_ITEM = re.compile(r"<item[ >].*?</item>", re.S | re.I)
_RE_TITRE = re.compile(r"<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>", re.S | re.I)
_RE_LIEN = re.compile(r"<link>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</link>", re.S | re.I)
_RE_DATE = re.compile(r"<pubDate>(.*?)</pubDate>", re.S | re.I)
_RE_BALISE = re.compile(r"<[^>]+>")
_ENTITES = {"&amp;": "&", "&lt;": "<", "&gt;": ">", "&quot;": '"',
            "&#39;": "'", "&apos;": "'", "&nbsp;": " ", "&#8217;": "\u2019"}


_RE_NUM = re.compile(r"&#(x?)([0-9A-Fa-f]+);")


def _detag(t: str) -> str:
    t = _RE_BALISE.sub("", t or "")
    t = _RE_NUM.sub(lambda m: chr(int(m.group(2), 16 if m.group(1) else 10)), t)
    for k, v in _ENTITES.items():
        t = t.replace(k, v)
    return t.strip()


def rss(nom, url, maxi=8):
    out = []
    try:
        r = S.get(url, timeout=12)
        if r.status_code != 200:
            return out
        for bloc in _RE_ITEM.findall(r.text)[:maxi]:
            t = _RE_TITRE.search(bloc)
            l = _RE_LIEN.search(bloc)
            d = _RE_DATE.search(bloc)
            if not t or not l:
                continue
            ts = None
            if d:
                try:
                    from email.utils import parsedate_to_datetime
                    ts = int(parsedate_to_datetime(d.group(1).strip()).timestamp() * 1000)
                except Exception:
                    ts = None
            out.append({"titre": t.group(1).strip(), "lien": l.group(1).strip(),
                        "src": nom, "t": ts, "cat": "macro", "tags": []})
    except Exception:
        pass
    return out


_RE_SRC_GN = re.compile(r"<source[^>]*>(.*?)</source>", re.I | re.S)


def _nettoie_titre_gn(t: str):
    """Google Actualites colle le nom du media a la fin du titre, on le remet comme source."""
    m = re.match(r"^(.*?)\s+-\s+([^-]{2,40})$", t)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return t, ""


def presse_valeur(terme, maxi=7):
    """Actualite francaise d'une valeur, via le flux public de Google Actualites.

    Ce flux agrege Les Echos, Boursorama, Zonebourse, Investing, Reuters France
    et le reste de la presse economique francophone, avec un lien vers l'article
    d'origine. C'est la seule voie ouverte pour ces titres, qui ne publient pas
    tous un flux de syndication par valeur.
    """
    out = []
    requete = '"' + terme + '" (bourse OR action OR resultats OR marche)'
    url = ("https://news.google.com/rss/search?q=" + requests.utils.quote(requete) +
           "&hl=fr&gl=FR&ceid=FR:fr")
    try:
        r = S.get(url, timeout=12)
        if r.status_code != 200:
            return out
        for bloc in _RE_ITEM.findall(r.text)[:maxi]:
            t = _RE_TITRE.search(bloc)
            l = _RE_LIEN.search(bloc)
            d = _RE_DATE.search(bloc)
            if not t or not l:
                continue
            titre, media = _nettoie_titre_gn(_detag(t.group(1).strip()))
            sm = _RE_SRC_GN.search(bloc)
            if sm:
                media = _detag(sm.group(1)).strip() or media
            ts = None
            if d:
                try:
                    from email.utils import parsedate_to_datetime
                    ts = int(parsedate_to_datetime(d.group(1).strip()).timestamp() * 1000)
                except Exception:
                    ts = None
            out.append({"titre": titre, "lien": l.group(1).strip(),
                        "src": media or "Presse", "t": ts, "cat": "titre", "tags": [terme]})
    except Exception:
        pass
    return out


@app.get("/api/news")
def news(q: str = "", macro: int = 1):
    termes = [x.strip() for x in q.split("|") if x.strip()][:14]
    cle = "news:" + "|".join(termes) + ":" + str(macro)
    hit = cache_get(cle, NEWS_TTL)
    if hit:
        return JSONResponse(hit, headers={"Cache-Control": "no-store"})
    items = []
    try:
        with ThreadPoolExecutor(max_workers=8) as pool:
            if macro:
                for lot in pool.map(lambda f: rss(f[0], f[1]), FLUX_MACRO):
                    items.extend(lot)
            if termes:
                for lot in pool.map(presse_valeur, termes):
                    items.extend(lot)
    except Exception:
        pass
    vus, net = set(), []
    for it in items:
        if it["lien"] in vus:
            continue
        vus.add(it["lien"])
        net.append(it)
    net.sort(key=lambda x: x.get("t") or 0, reverse=True)
    payload = {"asof": int(time.time() * 1000), "items": net[:120]}
    if net:
        cache_put(cle, payload)
    return JSONResponse(payload, headers={"Cache-Control": "no-store"})


# =====================================================================
#  CDS 5 ans, prix de reglement quotidiens publies par ICE Clear Credit
# =====================================================================
#  ICE met gratuitement a disposition les prix de reglement de fin de
#  journee des contrats mono-emetteur a cinq ans. Le prix est exprime en
#  pourcentage du nominal pour un coupon courant de 100 points de base :
#  un prix au-dessus de 100 signifie un spread inferieur au coupon.
#  On repasse du prix au spread par un modele a intensite constante,
#  recuperation 40 pour cent, ce qui est la convention de place.

ICE_URL = "https://www.ice.com/api/cds-settlement-prices/icc-single-names"
CDS_TTL = 6 * 3600.0
RECUP = 0.40
_RE_INSTR = re.compile(
    r"^([A-Za-z0-9\-_]+)\.([A-Z]+)\.([A-Z]{3})\.([A-Z0-9]+)\.([0-9.]+)\.(\d{4}-\d{2}-\d{2})$")

SUFFIXES = ("plc", "inc", "corp", "corporation", "co", "company", "sa", "s a", "se", "nv",
            "ag", "ab", "asa", "spa", "s p a", "ltd", "limited", "lp", "llc", "holding",
            "holdings", "group", "groupe", "the", "intl", "international", "sas", "oyj",
            "bv", "gmbh", "kgaa", "cie", "and", "&",
            "de", "du", "des", "la", "le", "les", "et", "compagnie", "generale",
            "etablissements", "societe", "sca", "spa", "aktiengesellschaft")
_RE_MOT = re.compile(r"[a-z0-9]+")


def _cle_emetteur(nom: str) -> str:
    """Nom d'emetteur ramene a ses mots porteurs, pour un rapprochement sobre."""
    t = (nom or "").lower()
    t = (t.replace("\u00e9", "e").replace("\u00e8", "e").replace("\u00ea", "e")
          .replace("\u00e0", "a").replace("\u00e2", "a").replace("\u00fb", "u")
          .replace("\u00f4", "o").replace("\u00ee", "i").replace("\u00e7", "c"))
    mots = [m for m in _RE_MOT.findall(t) if m not in SUFFIXES and len(m) > 1]
    # abreviations frequentes d'ICE
    corr = {"amern": "american", "intl": "international", "fin": "finance",
            "svcs": "services", "grp": "group", "natl": "national", "bk": "bank",
            "elec": "electric", "tele": "telecom", "comms": "communications"}
    return " ".join(corr.get(m, m) for m in mots)


def _annuite(lam: float, r: float, T: float) -> float:
    k = lam + r
    return T if k <= 1e-9 else (1.0 - pow(2.718281828459045, -k * T)) / k


def spread_depuis_prix(prix: float, coupon_bp: float, T: float, r: float = 0.03):
    """Spread par, en points de base, par dichotomie sur l'intensite de defaut."""
    try:
        upfront = (100.0 - float(prix)) / 100.0
        c = float(coupon_bp) / 10000.0
    except Exception:
        return None
    bas, haut = 0.0, 5.0
    for _ in range(80):
        lam = (bas + haut) / 2.0
        a = _annuite(lam, r, T)
        val = ((1.0 - RECUP) * lam - c) * a
        if val < upfront:
            bas = lam
        else:
            haut = lam
    lam = (bas + haut) / 2.0
    if lam <= 0 or lam >= 4.99:
        return None
    return round((1.0 - RECUP) * lam * 10000.0, 1)


def charger_cds():
    hit = cache_get("cds", CDS_TTL)
    if hit:
        return hit
    lignes, asof = {}, None
    try:
        r = S.get(ICE_URL, timeout=20)
        brut = r.json() if r.status_code == 200 else []
    except Exception:
        brut = []
    aujourd = time.time()
    for o in brut if isinstance(brut, list) else []:
        nom = (o.get("name") or "").strip()
        instr = (o.get("instrumentName") or "").strip()
        prix = o.get("eodPrice")
        m = _RE_INSTR.match(instr)
        if not nom or not m or prix in (None, ""):
            continue
        tic, tier, dev, doc, coupon, ech = m.groups()
        if tier != "SNRFOR":
            continue
        try:
            y, mo, d = [int(x) for x in ech.split("-")]
            import datetime as _dt
            ans = (_dt.date(y, mo, d) - _dt.date.fromtimestamp(aujourd)).days / 365.25
        except Exception:
            continue
        if not (4.0 <= ans <= 6.0):      # on ne garde que le point cinq ans
            continue
        sp = spread_depuis_prix(prix, coupon, ans)
        if sp is None or sp <= 0 or sp > 5000:
            continue
        asof = asof or o.get("clearingDate")
        cle = _cle_emetteur(nom)
        prec = lignes.get(cle)
        # une devise par emetteur suffit, on privilegie l'euro puis le dollar
        rang = 0 if dev == "EUR" else (1 if dev == "USD" else 2)
        if not prec or rang < prec["rang"]:
            lignes[cle] = {"nom": nom, "ticker": tic, "dev": dev, "doc": doc,
                           "spread": sp, "ans": round(ans, 2), "rang": rang}
    for v in lignes.values():
        v.pop("rang", None)
    payload = {"asof": asof, "n": len(lignes), "source": "ICE Clear Credit",
               "emetteurs": lignes}
    if lignes:
        cache_put("cds", payload)
    return payload


# quelques noms d'usage que la denomination legale d'ICE ne laisse pas deviner
ALIAS_CDS = {
    "lvmh": "lvmh moet hennessy louis vuitton",
    "hermes": "hermes international",
    "schneider": "schneider electric",
    "stellantis": "stellantis nv",
    "arcelormittal": "arcelormittal",
    "airbus": "airbus",
    "safran": "safran",
    "publicis": "publicis groupe",
    "vinci": "vinci",
    "bouygues": "bouygues",
    "orange": "orange",
    "engie": "engie",
    "veolia": "veolia environnement",
    "danone": "danone",
    "carrefour": "carrefour",
    "accor": "accor",
    "michelin": "michelin",
    "generale": "societe generale",
    "credit agricole": "credit agricole",
    "axa": "axa",
    "sanofi": "sanofi",
    "total": "totalenergies",
    "totalenergies": "totalenergies",
}


def rapprocher(nom: str, table: dict):
    """Rapproche un intitule du terminal d'une entite de reference ICE.

    Les noms d'usage sont courts (LVMH), les denominations ICE sont longues
    (LVMH Moet Hennessy Louis Vuitton SE). On accepte donc l'inclusion dans
    un sens comme dans l'autre, a condition qu'elle ne designe qu'un seul
    emetteur : une correspondance ambigue vaut mieux vide que fausse.
    """
    cle = _cle_emetteur(nom)
    if not cle:
        return None
    cle = ALIAS_CDS.get(cle, cle)
    if cle in table:
        return table[cle]
    mots = set(cle.split())
    if not mots or (len(mots) == 1 and len(cle) < 4):
        return None

    def unique(cands):
        if not cands:
            return None
        mini = min(c[0] for c in cands)
        tetes = [c[1] for c in cands if c[0] == mini]
        return tetes[0] if len(tetes) == 1 else None

    # le nom du terminal est contenu dans la denomination ICE
    inclus = [(len(set(k.split()) - mots), v) for k, v in table.items()
              if mots <= set(k.split())]
    r = unique(inclus)
    if r:
        return r
    # l'inclusion inverse n'est pas acceptee : "Anglo American Platinum" contient
    # "Anglo American" sans etre le meme emetteur, et une signature fausse est
    # pire qu'une case vide
    # a defaut, recouvrement large
    meilleur, score = None, 0.0
    for k, v in table.items():
        km = set(k.split())
        if not km:
            continue
        inter = len(mots & km)
        if inter < 2:
            continue
        sc = inter / float(len(mots | km))
        if sc > score:
            meilleur, score = v, sc
    # seuil volontairement haut : "Anglo American Platinum" recoupe
    # "Anglo American" aux deux tiers sans etre le meme emetteur
    return meilleur if score >= 0.75 else None


@app.get("/api/cds")
def cds(q: str = ""):
    """Spreads 5 ans. Sans parametre, toute la table. Avec q, les noms demandes."""
    d = charger_cds()
    if not q:
        return JSONResponse(d, headers={"Cache-Control": "no-store"})
    noms = [x.strip() for x in q.split("|") if x.strip()][:200]
    table = d.get("emetteurs") or {}
    sortie = {}
    for n in noms:
        trouve = rapprocher(n, table)
        if trouve:
            sortie[n] = {"spread": trouve["spread"], "emetteur": trouve["nom"],
                         "dev": trouve["dev"], "ans": trouve["ans"]}
    return JSONResponse({"asof": d.get("asof"), "n": d.get("n"), "source": d.get("source"),
                         "trouves": sortie}, headers={"Cache-Control": "no-store"})


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
        report["crumb"] = bool(yh_crumb())
    except Exception as exc:
        report["crumb"] = str(exc)[:80]
    try:
        report["dividendes"] = yh_dividends("MC.PA")
    except Exception as exc:
        report["dividendes"] = str(exc)[:120]
    try:
        code, rec = _une_serie_ecb(ECB_SERIES[2])
        report["bce"] = rec
    except Exception as exc:
        report["bce"] = str(exc)[:120]
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
const CACHE = "artemis-ia-v6";
const SHELL = ["/manifest.webmanifest", "/icon.svg"];
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
  // la page porte le nom et la configuration de la personne connectee,
  // elle n'est jamais mise en cache : chaque ouverture repart du serveur
  if (req.mode === "navigate" || url.pathname === "/" || url.pathname === "/terminal"
      || url.pathname.startsWith("/auth/") || url.pathname.startsWith("/admin/")
      || url.pathname.startsWith("/cfg")) return;
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
    with open(PAGE, "r", encoding="utf-8") as fh:
        html = fh.read()
    # la page abandonnait au bout de 12 s, trop court pour un onglet de 167 sous-jacents
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


# =====================================================================
#  Comptes : demande d'acces, connexion, administration, configurations
# =====================================================================

def _pose_cookie(reponse: Response, jeton: str, secure: bool) -> None:
    reponse.set_cookie(
        comptes.COOKIE, jeton, max_age=comptes.DUREE_SESSION, httponly=True,
        samesite="lax", secure=secure, path="/",
    )


def _ip(request: Request) -> str:
    h = request.headers.get("x-forwarded-for")
    if h:
        return h.split(",")[0].strip()
    return request.client.host if request.client else "?"


@app.post("/auth/demande")
async def auth_demande(request: Request):
    cle = "demande:" + _ip(request)
    if comptes.trop_de_tentatives(cle, maxi=5, fenetre=3600):
        return JSONResponse({"ok": False, "erreur": "Trop de demandes depuis ce poste. Reessayez plus tard."},
                            status_code=429)
    comptes.noter_tentative(cle)
    try:
        corps = await request.json()
    except Exception:
        return JSONResponse({"ok": False, "erreur": "Requete illisible."}, status_code=400)
    r = comptes.creer_demande(corps if isinstance(corps, dict) else {})
    return JSONResponse(r, status_code=200 if r.get("ok") else 400)


@app.post("/auth/connexion")
async def auth_connexion(request: Request):
    cle = "co:" + _ip(request)
    if comptes.trop_de_tentatives(cle):
        return JSONResponse({"ok": False, "erreur": "Trop d'essais. Patientez dix minutes."}, status_code=429)
    try:
        corps = await request.json()
    except Exception:
        return JSONResponse({"ok": False, "erreur": "Requete illisible."}, status_code=400)
    r = comptes.connecter(corps.get("email", ""), corps.get("mdp", ""))
    if not r.get("ok"):
        comptes.noter_tentative(cle)
        return JSONResponse({"ok": False, "erreur": r.get("erreur")}, status_code=401)
    rep = JSONResponse({"ok": True, "moi": r["moi"]})
    _pose_cookie(rep, r["jeton"], request.url.scheme == "https")
    return rep


@app.post("/auth/deconnexion")
async def auth_deconnexion(request: Request):
    comptes.fermer_session(request.cookies.get(comptes.COOKIE) or "")
    rep = JSONResponse({"ok": True})
    rep.delete_cookie(comptes.COOKIE, path="/")
    return rep


@app.get("/auth/moi")
async def auth_moi(request: Request):
    if _ouvert():
        return {"ok": True, "ouvert": True,
                "moi": {"email": "", "nom": "", "prenom": "", "role": "admin", "statut": "actif"}}
    u = _moi(request)
    if not u:
        return JSONResponse({"ok": False}, status_code=401)
    sortie = {"ok": True, "ouvert": False, "moi": comptes.public(u)}
    if u["role"] == "admin":
        sortie["attente"] = comptes.en_attente()
    return sortie


@app.post("/auth/motdepasse")
async def auth_motdepasse(request: Request):
    u = _moi(request)
    if not u:
        return JSONResponse({"ok": False, "erreur": "Session expiree."}, status_code=401)
    corps = await request.json()
    r = comptes.changer_mdp(u["email"], corps.get("ancien", ""), corps.get("nouveau", ""))
    return JSONResponse(r, status_code=200 if r.get("ok") else 400)


@app.get("/admin/comptes")
async def admin_comptes(request: Request):
    return {"ok": True, "comptes": comptes.liste(), "attente": comptes.en_attente(),
            "etat": comptes.etat()}


@app.post("/admin/decision")
async def admin_decision(request: Request):
    u = getattr(request.state, "moi", None) or _moi(request)
    corps = await request.json()
    r = comptes.decider(corps.get("email", ""), corps.get("action", ""),
                        source_config=u["email"] if u else None)
    if r.get("ok"):
        r["comptes"] = comptes.liste()
        r["attente"] = comptes.en_attente()
    return JSONResponse(r, status_code=200 if r.get("ok") else 400)


@app.post("/admin/reinitialiser")
async def admin_reinitialiser(request: Request):
    """L'administrateur fixe lui-meme un nouveau mot de passe pour un collaborateur."""
    corps = await request.json()
    email = (corps.get("email") or "").strip().lower()
    nouveau = corps.get("nouveau") or ""
    souci = comptes.souci_mdp(nouveau)
    if souci:
        return JSONResponse({"ok": False, "erreur": souci}, status_code=400)
    sel, emp = comptes.hacher(nouveau)
    with comptes._verrou:
        c = comptes.cx()
        if not c.execute("SELECT email FROM utilisateurs WHERE email=?", (email,)).fetchone():
            return JSONResponse({"ok": False, "erreur": "Compte introuvable."}, status_code=400)
        c.execute("UPDATE utilisateurs SET empreinte=?, sel=? WHERE email=?", (emp, sel, email))
        c.commit()
    comptes.fermer_toutes(email)
    return {"ok": True}


@app.get("/cfg")
async def cfg_lire(request: Request):
    u = _moi(request)
    if not u:
        return JSONResponse({"ok": False}, status_code=401)
    return {"ok": True, "cfg": comptes.lire_config(u["email"])}


@app.post("/cfg")
async def cfg_ecrire(request: Request):
    u = _moi(request)
    if not u:
        return JSONResponse({"ok": False}, status_code=401)
    try:
        corps = await request.json()
    except Exception:
        return JSONResponse({"ok": False, "erreur": "Requete illisible."}, status_code=400)
    r = comptes.ecrire_config(u["email"], corps.get("cfg"))
    return JSONResponse(r, status_code=200 if r.get("ok") else 400)


@app.get("/accueil")
def accueil_page():
    return HTMLResponse(ACCUEIL)


def _page_ou_message(request: Request = None):
    if not os.path.exists(PAGE):
        return JSONResponse({"ok": True, "msg": "Poser ARTEMIS_IA_TERMINAL.html a cote de main.py."})
    html = page_html()
    graine = {"ouvert": _ouvert(), "moi": None, "cfg": None, "attente": 0}
    u = _moi(request) if request is not None else None
    if u:
        graine["moi"] = comptes.public(u)
        graine["cfg"] = comptes.lire_config(u["email"])
        if u["role"] == "admin":
            graine["attente"] = comptes.en_attente()
    bloc = ("<script>window.__ARTX=" +
            json.dumps(graine, ensure_ascii=False).replace("</", "<\\/") + ";</script>")
    html = html.replace("</head>", bloc + "</head>", 1)
    return HTMLResponse(html)


@app.get("/")
def index(request: Request):
    return _page_ou_message(request)


@app.get("/terminal")
def terminal(request: Request):
    return _page_ou_message(request)

@app.get("/health")
def health():
    return {"ok": True, "ts": int(time.time() * 1000)}


STATIC = {
    "manifest.webmanifest": "application/manifest+json",
    "sw.js": "application/javascript",
    "icon-192.png": "image/png",
    "icon-512.png": "image/png",
    "icon-maskable-512.png": "image/png",
    "apple-touch-icon.png": "image/png",
    "favicon.ico": "image/x-icon",
}


@app.get("/{asset}")
def static_asset(asset: str):
    """Sert le manifeste, le service worker et les icones de l'application."""
    media = STATIC.get(asset)
    if not media:
        return JSONResponse({"detail": "Not Found"}, status_code=404)
    path = os.path.join(HERE, asset)
    if not os.path.exists(path):
        return JSONResponse({"detail": "Not Found"}, status_code=404)
    headers = {"Service-Worker-Allowed": "/"} if asset == "sw.js" else {}
    if asset == "sw.js":
        headers["Cache-Control"] = "no-cache"
    return FileResponse(path, media_type=media, headers=headers)
