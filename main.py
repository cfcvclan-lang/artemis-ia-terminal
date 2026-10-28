"""
ARTEMIS IA TERMINAL - backend de donnees
----------------------------------
Sert le terminal et son flux de marche depuis la meme origine, ce qui supprime
tout probleme de CORS et autorise un rafraichissement a 15 secondes.

Deploiement Render (Web Service, plan gratuit) :
    Build   : pip install -r requirements.txt
    Start   : uvicorn main:app --host 0.0.0.0 --port $PORT

Poser ARTEMIS_IA_TERMINAL.html a cote de main.py : il est servi sur "/".
Dans le terminal, choisir SOURCE = BACKEND ARTX (l'URL se deduit de l'origine).
"""
from __future__ import annotations

import os
import time
import threading
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

import yfinance as yf

app = FastAPI(title="Artemis IA Terminal API", version="1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # restreindre a votre domaine en production
    allow_methods=["GET"],
    allow_headers=["*"],
)

HERE = os.path.dirname(os.path.abspath(__file__))
PAGE = os.path.join(HERE, "ARTEMIS_IA_TERMINAL.html")

# ----------------------------------------------------------------- cache
_lock = threading.Lock()
_cache: Dict[str, Any] = {}

def cache_get(key: str, ttl: float):
    with _lock:
        hit = _cache.get(key)
    if hit and time.time() - hit[0] < ttl:
        return hit[1]
    return None

def cache_put(key: str, value):
    with _lock:
        _cache[key] = (time.time(), value)

# ----------------------------------------------------------------- quotes
QUOTE_TTL = 10.0          # le front interroge toutes les 15 s

def _fast_quote(sym: str) -> Optional[dict]:
    try:
        t = yf.Ticker(sym)
        fi = t.fast_info
        last = fi.get("last_price") if hasattr(fi, "get") else getattr(fi, "last_price", None)
        prev = fi.get("previous_close") if hasattr(fi, "get") else getattr(fi, "previous_close", None)
        if last is None:
            return None
        return {
            "p": float(last),
            "pc": float(prev) if prev else None,
            "vol": _num(fi, "last_volume"),
            "hi": _num(fi, "day_high"),
            "lo": _num(fi, "day_low"),
            "op": _num(fi, "open"),
            "cur": _str(fi, "currency"),
            "t": int(time.time() * 1000),
        }
    except Exception:
        return None

def _num(fi, key):
    try:
        v = fi.get(key) if hasattr(fi, "get") else getattr(fi, key, None)
        return float(v) if v is not None else None
    except Exception:
        return None

def _str(fi, key):
    try:
        v = fi.get(key) if hasattr(fi, "get") else getattr(fi, key, None)
        return str(v) if v else None
    except Exception:
        return None

@app.get("/api/quotes")
def quotes(symbols: str = Query(..., description="liste separee par des virgules")):
    syms: List[str] = [s.strip() for s in symbols.split(",") if s.strip()][:400]
    out: Dict[str, dict] = {}
    todo: List[str] = []
    for s in syms:
        hit = cache_get("q:" + s, QUOTE_TTL)
        if hit:
            out[s] = hit
        else:
            todo.append(s)

    if todo:
        # un seul appel groupe pour la volumetrie, puis complement unitaire
        try:
            data = yf.download(
                tickers=" ".join(todo), period="2d", interval="1d",
                group_by="ticker", threads=True, progress=False, auto_adjust=False,
            )
            for s in todo:
                try:
                    df = data[s] if len(todo) > 1 else data
                    df = df.dropna()
                    if len(df) >= 1:
                        last = float(df["Close"].iloc[-1])
                        prev = float(df["Close"].iloc[-2]) if len(df) >= 2 else None
                        rec = {
                            "p": last, "pc": prev,
                            "vol": float(df["Volume"].iloc[-1]) if "Volume" in df else None,
                            "hi": float(df["High"].iloc[-1]), "lo": float(df["Low"].iloc[-1]),
                            "op": float(df["Open"].iloc[-1]), "cur": None,
                            "t": int(time.time() * 1000),
                        }
                        out[s] = rec
                        cache_put("q:" + s, rec)
                except Exception:
                    continue
        except Exception:
            pass

        for s in todo:
            if s in out:
                continue
            rec = _fast_quote(s)
            if rec:
                out[s] = rec
                cache_put("q:" + s, rec)

    return JSONResponse(out, headers={"Cache-Control": "no-store"})

# ----------------------------------------------------------------- history
HIST_TTL = 900.0
RANGE_MAP = {
    "1d": ("1d", "5m"), "5d": ("5d", "30m"), "1mo": ("1mo", "1d"),
    "6mo": ("6mo", "1d"), "ytd": ("ytd", "1d"), "1y": ("1y", "1d"),
    "3y": ("3y", "1d"), "5y": ("5y", "1d"),
}

@app.get("/api/history")
def history(symbol: str, range: str = "5y"):
    period, interval = RANGE_MAP.get(range, ("5y", "1d"))
    key = f"h:{symbol}:{range}"
    hit = cache_get(key, HIST_TTL)
    if hit:
        return JSONResponse(hit, headers={"Cache-Control": "no-store"})
    try:
        df = yf.Ticker(symbol).history(period=period, interval=interval, auto_adjust=False)
        df = df.dropna(subset=["Close"])
        payload = {
            "t": [int(ts.timestamp() * 1000) for ts in df.index],
            "c": [float(v) for v in df["Close"]],
            "at": int(time.time() * 1000),
        }
    except Exception:
        payload = {"t": [], "c": [], "at": int(time.time() * 1000)}
    cache_put(key, payload)
    return JSONResponse(payload, headers={"Cache-Control": "no-store"})

# ----------------------------------------------------------------- consensus
CONS_TTL = 21600.0

@app.get("/api/consensus")
def consensus(symbol: str):
    key = "c:" + symbol
    hit = cache_get(key, CONS_TTL)
    if hit:
        return JSONResponse(hit, headers={"Cache-Control": "no-store"})
    payload: Dict[str, Any] = {}
    try:
        t = yf.Ticker(symbol)
        info = t.get_info()
        payload = {
            "mean": info.get("recommendationMean"),
            "key": info.get("recommendationKey"),
            "target": info.get("targetMeanPrice"),
            "low": info.get("targetLowPrice"),
            "high": info.get("targetHighPrice"),
            "n": info.get("numberOfAnalystOpinions"),
        }
        try:
            tr = t.recommendations
            if tr is not None and len(tr):
                row = tr.iloc[0]
                payload["buy"] = int(row.get("strongBuy", 0)) + int(row.get("buy", 0))
                payload["hold"] = int(row.get("hold", 0))
                payload["sell"] = int(row.get("sell", 0)) + int(row.get("strongSell", 0))
        except Exception:
            pass
    except Exception:
        pass
    cache_put(key, payload)
    return JSONResponse(payload, headers={"Cache-Control": "no-store"})

# ----------------------------------------------------------------- page
@app.get("/")
def index():
    if os.path.exists(PAGE):
        return FileResponse(PAGE, media_type="text/html")
    return JSONResponse({"ok": True, "msg": "Poser ARTEMIS_IA_TERMINAL.html a cote de main.py."})

@app.get("/health")
def health():
    return {"ok": True, "ts": int(time.time() * 1000)}
