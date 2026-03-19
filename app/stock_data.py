"""
stock_data.py
REPLACE existing app/stock_data.py
Real Finnhub data + yfinance fallback + in-memory cache.
"""
import os
import time
import logging
import threading
from datetime import datetime, timedelta
from typing import Optional

import finnhub
import yfinance as yf
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY", "")

try:
    finnhub_client = finnhub.Client(api_key=FINNHUB_API_KEY)
    finnhub_client.quote("AAPL")
    logger.info("Finnhub connected")
except Exception as exc:
    logger.warning(f"Finnhub init failed: {exc}")
    finnhub_client = None

DEFAULT_SYMBOLS = [
    "AAPL","GOOGL","MSFT","AMZN","TSLA","META","NVDA","AMD","INTC","NFLX","IBM","ORCL",
]
_tracked_symbols: list = list(DEFAULT_SYMBOLS)
_symbols_lock = threading.Lock()

def get_tracked_symbols():
    with _symbols_lock:
        return list(_tracked_symbols)

def add_symbol(symbol):
    symbol = symbol.upper().strip()
    with _symbols_lock:
        if symbol not in _tracked_symbols:
            _tracked_symbols.append(symbol)
            return True
    return False

def remove_symbol(symbol):
    symbol = symbol.upper().strip()
    with _symbols_lock:
        if symbol in _tracked_symbols:
            _tracked_symbols.remove(symbol)
            return True
    return False

_cache: dict = {}
_cache_lock = threading.Lock()
CACHE_TTL = 5

def _cache_get(key):
    with _cache_lock:
        e = _cache.get(key)
        if e and time.time() < e["exp"]:
            return e["val"]
        return None

def _cache_set(key, val, ttl=CACHE_TTL):
    with _cache_lock:
        _cache[key] = {"val": val, "exp": time.time() + ttl}

def cache_stats():
    with _cache_lock:
        live = sum(1 for v in _cache.values() if time.time() < v["exp"])
    return {"total_keys": len(_cache), "live_keys": live, "ttl_seconds": CACHE_TTL}


def get_stock_price(symbol: str) -> dict:
    symbol = symbol.upper().strip()
    cached = _cache_get(f"quote:{symbol}")
    if cached:
        cached["from_cache"] = True
        return cached

    if finnhub_client:
        try:
            q = finnhub_client.quote(symbol)
            if q and q.get("c", 0) > 0:
                result = {
                    "symbol": symbol, "price": round(q["c"], 2),
                    "change": round(q["d"], 2), "change_pct": round(q["dp"], 4),
                    "previous_close": round(q["pc"], 2), "high": round(q["h"], 2),
                    "low": round(q["l"], 2), "open": round(q["o"], 2),
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                    "source": "finnhub", "from_cache": False,
                }
                _cache_set(f"quote:{symbol}", result)
                return result
        except Exception as exc:
            logger.warning(f"Finnhub quote failed {symbol}: {exc}")

    return _yfinance_quote(symbol)


def _yfinance_quote(symbol: str) -> dict:
    try:
        info  = yf.Ticker(symbol).fast_info
        price = round(float(info.last_price or 0), 2)
        prev  = round(float(info.previous_close or price), 2)
        chg   = round(price - prev, 2)
        result = {
            "symbol": symbol, "price": price, "change": chg,
            "change_pct": round((chg / prev * 100) if prev else 0, 4),
            "previous_close": prev,
            "high": round(float(info.day_high  or price), 2),
            "low":  round(float(info.day_low   or price), 2),
            "open": round(float(info.open      or price), 2),
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "source": "yfinance", "from_cache": False,
        }
        _cache_set(f"quote:{symbol}", result)
        return result
    except Exception as exc:
        logger.error(f"yfinance quote failed {symbol}: {exc}")
        return {"error": f"Could not fetch {symbol}", "symbol": symbol}


def get_stock_history(symbol: str, days: int = 7) -> list:
    symbol = symbol.upper().strip()
    cached = _cache_get(f"history:{symbol}:{days}")
    if cached:
        return cached

    history = []
    if finnhub_client:
        try:
            end   = int(time.time())
            start = int((datetime.utcnow() - timedelta(days=days + 2)).timestamp())
            res   = finnhub_client.stock_candles(symbol, "D", start, end)
            if res and res.get("s") == "ok":
                for i in range(len(res["t"])):
                    history.append({
                        "date":   datetime.utcfromtimestamp(res["t"][i]).strftime("%Y-%m-%d"),
                        "open":   round(res["o"][i], 2), "high": round(res["h"][i], 2),
                        "low":    round(res["l"][i], 2), "close": round(res["c"][i], 2),
                        "volume": res["v"][i],
                    })
                history = history[-days:]
                _cache_set(f"history:{symbol}:{days}", history, ttl=60)
                return history
        except Exception as exc:
            logger.warning(f"Finnhub candles failed {symbol}: {exc}")

    try:
        df = yf.Ticker(symbol).history(period=f"{days+2}d", interval="1d")
        for date, row in df.tail(days).iterrows():
            history.append({
                "date":   date.strftime("%Y-%m-%d"),
                "open":   round(float(row["Open"]),  2), "high":  round(float(row["High"]),  2),
                "low":    round(float(row["Low"]),   2), "close": round(float(row["Close"]), 2),
                "volume": int(row["Volume"]),
            })
        _cache_set(f"history:{symbol}:{days}", history, ttl=60)
        return history
    except Exception as exc:
        logger.error(f"yfinance history failed {symbol}: {exc}")
        return []


def get_all_stocks() -> list:
    symbols = get_tracked_symbols()
    results = [None] * len(symbols)

    def fetch(i, sym):
        results[i] = get_stock_price(sym)

    threads = [threading.Thread(target=fetch, args=(i, s)) for i, s in enumerate(symbols)]
    for t in threads: t.start()
    for t in threads: t.join(timeout=8)
    return [r for r in results if r and "error" not in r]


def search_symbol(query: str) -> dict:
    query = query.upper().strip()
    if finnhub_client:
        try:
            res     = finnhub_client.symbol_search(query)
            matches = [r for r in res.get("result", []) if r.get("symbol","").upper() == query]
            if matches:
                m = matches[0]
                return {"symbol": m["symbol"], "description": m.get("description",""),
                        "type": m.get("type",""), "valid": True, "source": "finnhub"}
        except Exception as exc:
            logger.warning(f"Finnhub search failed: {exc}")

    try:
        info = yf.Ticker(query).fast_info
        if info.last_price and info.last_price > 0:
            return {"symbol": query, "description": query, "type": "Common Stock",
                    "valid": True, "source": "yfinance"}
    except Exception:
        pass

    return {"error": f"Symbol '{query}' not found", "valid": False}


def get_stock_news(symbol: str, count: int = 5) -> list:
    symbol = symbol.upper().strip()
    cached = _cache_get(f"news:{symbol}")
    if cached:
        return cached

    if not finnhub_client:
        return []

    try:
        today = datetime.utcnow()
        start = (today - timedelta(days=7)).strftime("%Y-%m-%d")
        end   = today.strftime("%Y-%m-%d")
        articles = finnhub_client.company_news(symbol, _from=start, to=end)
        news = []
        for a in articles[:count]:
            news.append({
                "headline": a.get("headline", ""), "summary": a.get("summary", "")[:200],
                "url": a.get("url", ""), "source": a.get("source", ""),
                "datetime": datetime.utcfromtimestamp(a.get("datetime", 0)).strftime("%Y-%m-%d %H:%M"),
            })
        _cache_set(f"news:{symbol}", news, ttl=300)
        return news
    except Exception as exc:
        logger.warning(f"Finnhub news failed {symbol}: {exc}")
        return []


def get_company_profile(symbol: str) -> dict:
    symbol = symbol.upper().strip()
    cached = _cache_get(f"profile:{symbol}")
    if cached:
        return cached

    if not finnhub_client:
        return {}

    try:
        p = finnhub_client.company_profile2(symbol=symbol)
        profile = {
            "name": p.get("name", symbol), "ticker": p.get("ticker", symbol),
            "exchange": p.get("exchange", ""), "ipo": p.get("ipo", ""),
            "market_cap": round(p.get("marketCapitalization", 0), 2),
            "logo": p.get("logo", ""), "weburl": p.get("weburl", ""),
            "industry": p.get("finnhubIndustry", ""), "currency": p.get("currency", "USD"),
        }
        _cache_set(f"profile:{symbol}", profile, ttl=3600)
        return profile
    except Exception as exc:
        logger.warning(f"Finnhub profile failed {symbol}: {exc}")
        return {}
