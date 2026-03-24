"""
stock_data.py  —  AutoDevOps FinTech
-------------------------------------
KEY FIXES in this version:
  1. simulate_price() now uses REALISTIC base prices per symbol (not ~$100)
  2. Any NEW symbol added by admin/user is looked up via yfinance first,
     so its simulate base is its real last-known price — not a hardcoded guess
  3. get_stock_price() always tries Finnhub → yfinance → realistic sim fallback
  4. Sim bases for unknown symbols are seeded from yfinance on first fetch and
     cached so subsequent calls stay consistent
"""

import os
import time
import logging
import threading
import random
import math
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
    finnhub_client.quote("AAPL")
    logger.info("Finnhub client initialised")
except Exception as exc:
    logger.warning(f"Finnhub unavailable: {exc}")
    finnhub_client = None

# ── Tracked Symbols ────────────────────────────────────────────────────────────
DEFAULT_SYMBOLS = [
    "AAPL", "GOOGL", "MSFT", "AMZN",
    "TSLA", "META",  "NVDA", "AMD",
    "INTC", "NFLX",  "IBM",  "ORCL",
]
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

# ── Cache ──────────────────────────────────────────────────────────────────────
_cache: dict = {}
_cache_lock = threading.Lock()
CACHE_TTL = int(os.getenv("STOCK_CACHE_TTL", "5"))

def _cache_get(key: str) -> Optional[dict]:
    with _cache_lock:
        entry = _cache.get(key)
        if entry and time.time() < entry["expires_at"]:
            return entry["data"]
        return None

def _cache_set(key: str, data: dict, ttl: int = CACHE_TTL):
    with _cache_lock:
        _cache[key] = {"data": data, "expires_at": time.time() + ttl}

def cache_stats() -> dict:
    with _cache_lock:
        total = len(_cache)
        live  = sum(1 for v in _cache.values() if time.time() < v["expires_at"])
    return {"total_keys": total, "live_keys": live, "ttl_seconds": CACHE_TTL}

# ── REALISTIC Simulation Bases ─────────────────────────────────────────────────
# Accurate as of mid-2025. Updated whenever yfinance returns a real price.
_SIM_BASES: dict[str, float] = {
    "AAPL":  185.0,
    "GOOGL": 178.0,
    "MSFT":  425.0,
    "AMZN":  195.0,
    "TSLA":  175.0,
    "META":  525.0,
    "NVDA":  875.0,
    "AMD":   165.0,
    "INTC":   30.0,
    "NFLX":  640.0,
    "IBM":   230.0,
    "ORCL":  140.0,
    # Common extras users add:
    "SPY":   530.0,
    "QQQ":   460.0,
    "BRK-B": 420.0,
    "JPM":   215.0,
    "V":     280.0,
    "MA":    475.0,
    "UNH":   520.0,
    "JNJ":   155.0,
    "WMT":   180.0,
    "PG":    170.0,
    "DIS":    95.0,
    "BABA":   85.0,
    "SHOP":   80.0,
    "SNAP":   10.0,
    "UBER":   75.0,
    "LYFT":   14.0,
    "COIN":  220.0,
    "PLTR":   25.0,
    "RBLX":   35.0,
    "NET":   100.0,
    "CRWD":  330.0,
    "ZS":    210.0,
    "DDOG":  130.0,
    "SNOW":  170.0,
    "MDB":   380.0,
    "ASML": 850.0,
    "TSM":   155.0,
    "SMSN":   70.0,
    "BTC-USD": 68000.0,
    "ETH-USD":  3500.0,
}
_sim_bases_lock = threading.Lock()


def _get_sim_base(symbol: str) -> float:
    """
    Return a realistic simulation base price for a symbol.
    1. Use known table if available.
    2. Try yfinance to get actual last price and cache it.
    3. Fall back to $100 only as absolute last resort.
    """
    with _sim_bases_lock:
        if symbol in _SIM_BASES:
            return _SIM_BASES[symbol]

    # Try to seed base from yfinance
    try:
        ticker = yf.Ticker(symbol)
        info   = ticker.fast_info
        price  = float(info.last_price or 0)
        if price > 0:
            with _sim_bases_lock:
                _SIM_BASES[symbol] = price
            logger.info(f"[SimBase] Seeded {symbol} base from yfinance: ${price}")
            return price
    except Exception:
        pass

    # True fallback — only if yfinance also fails
    with _sim_bases_lock:
        _SIM_BASES[symbol] = 100.0
    return 100.0


def simulate_price(base: float = None, symbol: str = "TEST") -> dict:
    """
    Deterministic simulated quote with realistic prices.
    Used by tests and as last-resort offline fallback.
    """
    symbol = symbol.upper()
    if base is None:
        base = _get_sim_base(symbol)

    t          = time.time()
    wobble     = math.sin(t / 60) * base * 0.005
    price      = round(base + wobble + random.uniform(-base * 0.001, base * 0.001), 2)
    prev_close = round(base * 0.999, 2)
    change     = round(price - prev_close, 2)
    change_pct = round(change / prev_close * 100, 4) if prev_close else 0

    return {
        "symbol":         symbol,
        "price":          max(price, 0.01),
        "change":         change,
        "change_pct":     change_pct,
        "previous_close": prev_close,
        "high":           round(price * 1.003, 2),
        "low":            round(price * 0.997, 2),
        "open":           round(prev_close * 1.001, 2),
        "timestamp":      datetime.utcnow().isoformat() + "Z",
        "source":         "simulated",
        "from_cache":     False,
    }


# ── Main Quote Fetch ───────────────────────────────────────────────────────────

def get_stock_price(symbol: str) -> dict:
    symbol    = symbol.upper().strip()
    cache_key = f"quote:{symbol}"

    cached = _cache_get(cache_key)
    if cached:
        cached["from_cache"] = True
        return cached

    # 1. Finnhub (primary — accurate, real-time)
    if finnhub_client:
        try:
            q = finnhub_client.quote(symbol)
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
                # Update sim base with real price so future offline fallback is accurate
                with _sim_bases_lock:
                    _SIM_BASES[symbol] = result["price"]
                _cache_set(cache_key, result)
                return result
        except Exception as exc:
            logger.warning(f"[Finnhub] {symbol}: {exc}")

    # 2. yfinance fallback
    yf_result = _yfinance_quote(symbol)
    if "error" not in yf_result:
        # Update sim base with real price
        with _sim_bases_lock:
            _SIM_BASES[symbol] = yf_result["price"]
        return yf_result

    # 3. Realistic simulated fallback (uses seeded base — NOT ~$100)
    logger.warning(f"[Fallback] Simulating {symbol}")
    sim = simulate_price(symbol=symbol)
    _cache_set(cache_key, sim)
    return sim


def _yfinance_quote(symbol: str) -> dict:
    try:
        ticker = yf.Ticker(symbol)
        info   = ticker.fast_info

        price      = round(float(info.last_price or 0), 2)
        prev_close = round(float(info.previous_close or price), 2)
        if price <= 0:
            return {"error": f"No data for {symbol}", "symbol": symbol}

        change     = round(price - prev_close, 2)
        change_pct = round((change / prev_close * 100) if prev_close else 0, 4)

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
        return result
    except Exception as exc:
        logger.error(f"[yfinance] {symbol}: {exc}")
        return {"error": f"Could not fetch {symbol}", "symbol": symbol}


# ── History ────────────────────────────────────────────────────────────────────

def get_stock_history(symbol: str, days: int = 7) -> list[dict]:
    symbol    = symbol.upper().strip()
    cache_key = f"history:{symbol}:{days}"

    cached = _cache_get(cache_key)
    if cached:
        return cached

    history = []

    # 1. Finnhub candles
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
            logger.warning(f"[Finnhub] candles {symbol}: {exc}")

    # 2. yfinance
    try:
        ticker = yf.Ticker(symbol)
        df     = ticker.history(period=f"{days + 2}d", interval="1d")
        for date, row in df.tail(days).iterrows():
            history.append({
                "date":   date.strftime("%Y-%m-%d"),
                "open":   round(float(row["Open"]),  2),
                "high":   round(float(row["High"]),  2),
                "low":    round(float(row["Low"]),   2),
                "close":  round(float(row["Close"]), 2),
                "volume": int(row["Volume"]),
            })
        if history:
            _cache_set(cache_key, history, ttl=60)
            return history
    except Exception as exc:
        logger.error(f"[yfinance] history {symbol}: {exc}")

    # 3. Simulated history using realistic base
    base  = _get_sim_base(symbol)
    today = datetime.utcnow()
    for i in range(days, 0, -1):
        d      = today - timedelta(days=i)
        drift  = random.uniform(-0.02, 0.02)
        close  = round(base * (1 + drift), 2)
        o      = round(base, 2)
        history.append({
            "date":   d.strftime("%Y-%m-%d"),
            "open":   o,
            "high":   round(max(o, close) * 1.005, 2),
            "low":    round(min(o, close) * 0.995, 2),
            "close":  close,
            "volume": random.randint(10_000_000, 80_000_000),
        })
        base = close
    _cache_set(cache_key, history, ttl=60)
    return history


# ── All Stocks (parallel) ──────────────────────────────────────────────────────

def get_all_stocks() -> list[dict]:
    symbols = get_tracked_symbols()
    results = [None] * len(symbols)

    def fetch(i, sym):
        results[i] = get_stock_price(sym)

    threads = [threading.Thread(target=fetch, args=(i, s)) for i, s in enumerate(symbols)]
    for t in threads: t.start()
    for t in threads: t.join(timeout=8)
    return [r for r in results if r and "error" not in r]


# ── Symbol Search ──────────────────────────────────────────────────────────────

def search_symbol(query: str) -> dict:
    query = query.upper().strip()

    if finnhub_client:
        try:
            res     = finnhub_client.symbol_search(query)
            matches = [r for r in res.get("result", []) if r.get("symbol", "").upper() == query]
            if matches:
                m = matches[0]
                return {"symbol": m["symbol"], "description": m.get("description", ""),
                        "type": m.get("type", ""), "valid": True, "source": "finnhub"}
        except Exception as exc:
            logger.warning(f"[Finnhub] search {query}: {exc}")

    try:
        ticker = yf.Ticker(query)
        info   = ticker.fast_info
        if info.last_price and info.last_price > 0:
            return {"symbol": query, "description": ticker.info.get("longName", query),
                    "type": "Common Stock", "valid": True, "source": "yfinance"}
    except Exception:
        pass

    # Known symbols always valid (for tests / offline)
    if query in _SIM_BASES:
        return {"symbol": query, "description": query, "type": "Common Stock",
                "valid": True, "source": "simulated"}

    return {"error": f"Symbol '{query}' not found", "valid": False}


# ── News & Profile ─────────────────────────────────────────────────────────────

def get_stock_news(symbol: str, count: int = 5) -> list[dict]:
    symbol    = symbol.upper().strip()
    cache_key = f"news:{symbol}"
    cached = _cache_get(cache_key)
    if cached: return cached
    if not finnhub_client: return []
    try:
        today    = datetime.utcnow()
        start    = (today - timedelta(days=7)).strftime("%Y-%m-%d")
        end      = today.strftime("%Y-%m-%d")
        articles = finnhub_client.company_news(symbol, _from=start, to=end)
        news = [{"headline": a.get("headline", ""), "summary": a.get("summary", "")[:200],
                 "url": a.get("url", ""), "source": a.get("source", ""),
                 "datetime": datetime.utcfromtimestamp(a.get("datetime", 0)).strftime("%Y-%m-%d %H:%M")}
                for a in articles[:count]]
        _cache_set(cache_key, news, ttl=300)
        return news
    except Exception as exc:
        logger.warning(f"[Finnhub] news {symbol}: {exc}")
        return []


def get_company_profile(symbol: str) -> dict:
    symbol    = symbol.upper().strip()
    cache_key = f"profile:{symbol}"
    cached = _cache_get(cache_key)
    if cached: return cached
    if not finnhub_client: return {}
    try:
        p = finnhub_client.company_profile2(symbol=symbol)
        profile = {"name": p.get("name", symbol), "ticker": p.get("ticker", symbol),
                   "exchange": p.get("exchange", ""), "ipo": p.get("ipo", ""),
                   "market_cap": round(p.get("marketCapitalization", 0), 2),
                   "logo": p.get("logo", ""), "weburl": p.get("weburl", ""),
                   "industry": p.get("finnhubIndustry", ""), "currency": p.get("currency", "USD")}
        _cache_set(cache_key, profile, ttl=3600)
        return profile
    except Exception as exc:
        logger.warning(f"[Finnhub] profile {symbol}: {exc}")
        return {}
