"""
stock_data.py
-------------
Real-time stock data service using Finnhub API.

Features:
  - Live quotes via Finnhub REST API
  - In-memory cache (5s TTL) — drop Redis in later via cache_service.py
  - 7–30 day OHLCV history via yfinance fallback
  - Symbol search / validation
  - Company news
  - WebSocket stream manager (for future /api/stream endpoint)

Finnhub free tier: 60 API calls/minute — more than enough for 12 symbols
with 5s caching (each symbol = 1 call per 5s = 12 calls/5s = 144 calls/min
BEFORE cache; WITH cache = 1 call per symbol per 5s window = safe).
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

# ── Finnhub Client ─────────────────────────────────────────────────────────────
FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY", "")

try:
    finnhub_client = finnhub.Client(api_key=FINNHUB_API_KEY)
    # Quick connectivity test
    finnhub_client.quote("AAPL")
    logger.info("Finnhub client initialised successfully")
except Exception as exc:
    logger.warning(f"Finnhub client init failed: {exc} — falling back to yfinance only")
    finnhub_client = None


# ── Tracked Symbols ────────────────────────────────────────────────────────────
DEFAULT_SYMBOLS = [
    "AAPL", "GOOGL", "MSFT", "AMZN",
    "TSLA", "META",  "NVDA", "AMD",
    "INTC", "NFLX",  "IBM",  "ORCL",
]

# Runtime list — admin can add/remove symbols without restart
_tracked_symbols: list[str] = list(DEFAULT_SYMBOLS)
_symbols_lock = threading.Lock()


def get_tracked_symbols() -> list[str]:
    with _symbols_lock:
        return list(_tracked_symbols)

def add_symbol(symbol: str) -> bool:
    symbol = symbol.upper().strip()
    with _symbols_lock:
        if symbol not in _tracked_symbols:
            _tracked_symbols.append(symbol)
            return True
    return False

def remove_symbol(symbol: str) -> bool:
    symbol = symbol.upper().strip()
    with _symbols_lock:
        if symbol in _tracked_symbols:
            _tracked_symbols.remove(symbol)
            return True
    return False


# ── In-Memory Cache ────────────────────────────────────────────────────────────
# Format: { "AAPL": {"data": {...}, "expires_at": float} }
_cache: dict = {}
_cache_lock = threading.Lock()
CACHE_TTL = 5  # seconds


def _cache_get(key: str) -> Optional[dict]:
    with _cache_lock:
        entry = _cache.get(key)
        if entry and time.time() < entry["expires_at"]:
            return entry["data"]
        return None


def _cache_set(key: str, data: dict, ttl: int = CACHE_TTL):
    with _cache_lock:
        _cache[key] = {
            "data": data,
            "expires_at": time.time() + ttl,
        }


def cache_stats() -> dict:
    """Return cache hit/miss stats — used by admin panel."""
    with _cache_lock:
        total = len(_cache)
        live  = sum(1 for v in _cache.values() if time.time() < v["expires_at"])
    return {"total_keys": total, "live_keys": live, "ttl_seconds": CACHE_TTL}


# ── Quote: Finnhub → yfinance fallback ────────────────────────────────────────

def get_stock_price(symbol: str) -> dict:
    """
    Fetch current quote for a symbol.
    Returns dict with: symbol, price, change, change_pct, previous_close,
                       high, low, open, timestamp, source
    """
    symbol = symbol.upper().strip()
    cache_key = f"quote:{symbol}"

    # 1. Cache hit
    cached = _cache_get(cache_key)
    if cached:
        cached["from_cache"] = True
        return cached

    # 2. Try Finnhub
    if finnhub_client:
        try:
            q = finnhub_client.quote(symbol)
            # q = {c: current, d: change, dp: change%, h: high, l: low, o: open, pc: prev_close}
            if q and q.get("c", 0) > 0:
                result = {
                    "symbol":         symbol,
                    "price":          round(q["c"],  2),
                    "change":         round(q["d"],  2),
                    "change_pct":     round(q["dp"], 4),
                    "previous_close": round(q["pc"], 2),
                    "high":           round(q["h"],  2),
                    "low":            round(q["l"],  2),
                    "open":           round(q["o"],  2),
                    "timestamp":      datetime.utcnow().isoformat() + "Z",
                    "source":         "finnhub",
                    "from_cache":     False,
                }
                _cache_set(cache_key, result)
                logger.info(f"[Finnhub] {symbol} → ${result['price']} ({result['change_pct']:+.2f}%)")
                return result
        except Exception as exc:
            logger.warning(f"[Finnhub] quote failed for {symbol}: {exc}")

    # 3. Fallback: yfinance
    return _yfinance_quote(symbol)


def _yfinance_quote(symbol: str) -> dict:
    """yfinance fallback for current quote."""
    try:
        ticker = yf.Ticker(symbol)
        info   = ticker.fast_info

        price        = round(float(info.last_price or 0), 2)
        prev_close   = round(float(info.previous_close or price), 2)
        change       = round(price - prev_close, 2)
        change_pct   = round((change / prev_close * 100) if prev_close else 0, 4)

        result = {
            "symbol":         symbol,
            "price":          price,
            "change":         change,
            "change_pct":     change_pct,
            "previous_close": prev_close,
            "high":           round(float(info.day_high  or price), 2),
            "low":            round(float(info.day_low   or price), 2),
            "open":           round(float(info.open      or price), 2),
            "timestamp":      datetime.utcnow().isoformat() + "Z",
            "source":         "yfinance",
            "from_cache":     False,
        }
        _cache_set(f"quote:{symbol}", result)
        logger.info(f"[yfinance] {symbol} → ${result['price']}")
        return result

    except Exception as exc:
        logger.error(f"[yfinance] quote failed for {symbol}: {exc}")
        return {"error": f"Could not fetch price for {symbol}", "symbol": symbol}


# ── History: Finnhub candles → yfinance fallback ───────────────────────────────

def get_stock_history(symbol: str, days: int = 7) -> list[dict]:
    """
    Return OHLCV candles for the last N days.
    Each entry: { date, open, high, low, close, volume }
    """
    symbol    = symbol.upper().strip()
    cache_key = f"history:{symbol}:{days}"

    cached = _cache_get(cache_key)
    if cached:
        return cached

    history = []

    # 1. Finnhub candles (1-day resolution = "D")
    if finnhub_client:
        try:
            end   = int(time.time())
            start = int((datetime.utcnow() - timedelta(days=days + 2)).timestamp())
            res   = finnhub_client.stock_candles(symbol, "D", start, end)

            if res and res.get("s") == "ok":
                for i in range(len(res["t"])):
                    history.append({
                        "date":   datetime.utcfromtimestamp(res["t"][i]).strftime("%Y-%m-%d"),
                        "open":   round(res["o"][i], 2),
                        "high":   round(res["h"][i], 2),
                        "low":    round(res["l"][i], 2),
                        "close":  round(res["c"][i], 2),
                        "volume": res["v"][i],
                    })
                history = history[-days:]
                _cache_set(cache_key, history, ttl=60)
                return history
        except Exception as exc:
            logger.warning(f"[Finnhub] candles failed for {symbol}: {exc}")

    # 2. Fallback: yfinance
    try:
        ticker = yf.Ticker(symbol)
        df     = ticker.history(period=f"{days + 2}d", interval="1d")

        for date, row in df.tail(days).iterrows():
            history.append({
                "date":   date.strftime("%Y-%m-%d"),
                "open":   round(float(row["Open"]),   2),
                "high":   round(float(row["High"]),   2),
                "low":    round(float(row["Low"]),    2),
                "close":  round(float(row["Close"]),  2),
                "volume": int(row["Volume"]),
            })

        _cache_set(cache_key, history, ttl=60)
        return history

    except Exception as exc:
        logger.error(f"[yfinance] history failed for {symbol}: {exc}")
        return []


# ── All Stocks ─────────────────────────────────────────────────────────────────

def get_all_stocks() -> list[dict]:
    """
    Return current quotes for all tracked symbols.
    Uses threading to fetch in parallel — typically <500ms for 12 symbols.
    """
    symbols = get_tracked_symbols()
    results = [None] * len(symbols)

    def fetch(i, sym):
        results[i] = get_stock_price(sym)

    threads = [threading.Thread(target=fetch, args=(i, s)) for i, s in enumerate(symbols)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=8)

    return [r for r in results if r and "error" not in r]


# ── Symbol Search ──────────────────────────────────────────────────────────────

def search_symbol(query: str) -> dict:
    """
    Search / validate a ticker symbol.
    Returns { symbol, description, valid } or { error }
    """
    query = query.upper().strip()

    if finnhub_client:
        try:
            res = finnhub_client.symbol_search(query)
            matches = [
                r for r in res.get("result", [])
                if r.get("symbol", "").upper() == query
            ]
            if matches:
                m = matches[0]
                return {
                    "symbol":      m["symbol"],
                    "description": m.get("description", ""),
                    "type":        m.get("type", ""),
                    "valid":       True,
                    "source":      "finnhub",
                }
        except Exception as exc:
            logger.warning(f"[Finnhub] symbol_search failed: {exc}")

    # Fallback: try fetching a quote
    try:
        ticker = yf.Ticker(query)
        info   = ticker.fast_info
        if info.last_price and info.last_price > 0:
            return {
                "symbol":      query,
                "description": ticker.info.get("longName", query),
                "type":        "Common Stock",
                "valid":       True,
                "source":      "yfinance",
            }
    except Exception:
        pass

    return {"error": f"Symbol '{query}' not found", "valid": False}


# ── Company News ───────────────────────────────────────────────────────────────

def get_stock_news(symbol: str, count: int = 5) -> list[dict]:
    """
    Return latest company news headlines from Finnhub.
    Each entry: { headline, summary, url, source, datetime }
    """
    symbol    = symbol.upper().strip()
    cache_key = f"news:{symbol}"

    cached = _cache_get(cache_key)
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
                "headline": a.get("headline", ""),
                "summary":  a.get("summary",  "")[:200],
                "url":      a.get("url",       ""),
                "source":   a.get("source",    ""),
                "datetime": datetime.utcfromtimestamp(
                    a.get("datetime", 0)
                ).strftime("%Y-%m-%d %H:%M"),
            })

        _cache_set(cache_key, news, ttl=300)  # cache news for 5 min
        return news

    except Exception as exc:
        logger.warning(f"[Finnhub] news failed for {symbol}: {exc}")
        return []


# ── Company Profile ────────────────────────────────────────────────────────────

def get_company_profile(symbol: str) -> dict:
    """
    Return basic company profile from Finnhub.
    { name, ticker, exchange, ipo, marketCap, logo, weburl, industry }
    """
    symbol    = symbol.upper().strip()
    cache_key = f"profile:{symbol}"

    cached = _cache_get(cache_key)
    if cached:
        return cached

    if not finnhub_client:
        return {}

    try:
        p = finnhub_client.company_profile2(symbol=symbol)
        profile = {
            "name":       p.get("name",           symbol),
            "ticker":     p.get("ticker",          symbol),
            "exchange":   p.get("exchange",        ""),
            "ipo":        p.get("ipo",             ""),
            "market_cap": round(p.get("marketCapitalization", 0), 2),
            "logo":       p.get("logo",            ""),
            "weburl":     p.get("weburl",          ""),
            "industry":   p.get("finnhubIndustry", ""),
            "currency":   p.get("currency",        "USD"),
        }
        _cache_set(cache_key, profile, ttl=3600)  # cache profile for 1 hour
        return profile

    except Exception as exc:
        logger.warning(f"[Finnhub] profile failed for {symbol}: {exc}")
        return {}
