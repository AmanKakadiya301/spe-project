"""
stock_data.py
-------------
Handles all stock price fetching logic using Finnhub.
"""

import os
import random
import time
import logging
import finnhub
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# Initialize Finnhub client
API_KEY = os.getenv("FINNHUB_API_KEY")
if not API_KEY:
    logger.warning("FINNHUB_API_KEY environment variable not set! Live data will fail.")
finnhub_client = finnhub.Client(api_key=API_KEY) if API_KEY else None

# Default stock symbols to track on the homepage
DEFAULT_SYMBOLS = ["AAPL", "GOOGL", "MSFT", "AMZN", "TSLA", "META", "NVDA", "AMD", "INTC", "NFLX", "IBM", "ORCL"]

# Seed prices for simulation fallback (only for defaults)
SEED_PRICES = {
    "AAPL":  189.50,
    "GOOGL": 175.20,
    "MSFT":  415.80,
    "AMZN":  185.60,
    "TSLA":  200.10,
    "META":  505.30,
    "NVDA":  875.40,
    "AMD":   198.00,
    "INTC":  44.50,
    "NFLX":  94.00,
    "IBM":   255.00,
    "ORCL":  152.00,
}


def simulate_price(base_price: float) -> dict:
    """
    Simulate a realistic stock price using a random walk algorithm.
    Mimics real market behaviour with small percentage fluctuations.
    """
    change_pct = random.uniform(-2.5, 2.5)
    new_price   = round(base_price * (1 + change_pct / 100), 2)
    change      = round(new_price - base_price, 2)
    return {
        "price":      new_price,
        "change":     change,
        "change_pct": round(change_pct, 2),
        "source":     "simulated",
    }


def search_symbol(query: str) -> dict:
    """
    Validate whether a ticker symbol exists via Finnhub.
    Returns basic info if found, or error dict if not.
    """
    query = query.upper().strip()
    if not query:
        return {"error": "Empty query"}
    try:
        if not finnhub_client:
            raise ValueError("Finnhub unconfigured")
            
        res = finnhub_client.symbol_search(query)
        # Find exact or best match
        best_match = None
        for r in res.get('result', []):
            if r['symbol'] == query or r['displaySymbol'] == query:
                best_match = r
                break
        
        if not best_match and res.get('result'):
            best_match = res['result'][0]
            
        if not best_match:
            return {"error": f"Symbol '{query}' not found"}
            
        # Get actual price
        quote = finnhub_client.quote(best_match['symbol'])
        
        return {
            "symbol": best_match['displaySymbol'],
            "price": quote.get('c', 0),
            "valid": True,
        }
    except Exception as exc:
        logger.error(f"Search failed: {exc}")
        return {"error": f"Symbol '{query}' not found"}


def get_stock_price(symbol: str) -> dict:
    """
    Fetch real-time stock price for a given symbol from Finnhub.
    Falls back to simulation if unavailable.
    """
    symbol = symbol.upper()
    try:
        if not finnhub_client:
            raise ValueError("Finnhub unconfigured")
            
        quote = finnhub_client.quote(symbol)
        
        current = quote.get('c')
        prev_close = quote.get('pc')
        
        if current == 0 and prev_close == 0:
            # Finnhub returns 0s for invalid symbols
            raise ValueError(f"No price data returned from Finnhub for {symbol}")

        change = quote.get('d', round(current - prev_close, 2))
        change_pct = quote.get('dp', round((change / prev_close) * 100, 2) if prev_close else 0.0)

        logger.info(f"Live price fetched via Finnhub — {symbol}: ${current}")

        return {
            "symbol":         symbol,
            "price":          round(current, 2),
            "previous_close": round(prev_close, 2),
            "change":         round(change, 2),
            "change_pct":     round(change_pct, 2),
            "source":         "live",
            "timestamp":      quote.get('t', int(time.time())),
        }

    except Exception as exc:
        logger.warning(f"Finnhub quote failed for {symbol}: {exc}. Using simulation.")

        # For known symbols, use simulation fallback
        if symbol in SEED_PRICES:
            base      = SEED_PRICES[symbol]
            sim       = simulate_price(base)
            SEED_PRICES[symbol] = sim["price"]     # walk the price forward each call

            return {
                "symbol":         symbol,
                "price":          sim["price"],
                "previous_close": base,
                "change":         sim["change"],
                "change_pct":     sim["change_pct"],
                "source":         "simulated",
                "timestamp":      int(time.time()),
            }

        # For unknown symbols with no seed, return error
        return {"error": f"Symbol '{symbol}' not found or unavailable"}


def get_stock_history(symbol: str, days: int = 7) -> list:
    """
    Return OHLCV history for the past N days from Finnhub.
    Used for sparkline charts in the frontend.
    """
    symbol = symbol.upper()
    try:
        if not finnhub_client:
            raise ValueError("Finnhub unconfigured")
            
        now = int(time.time())
        # Add 3 extra days to account for weekends where markets are closed
        past = int((datetime.now() - timedelta(days=days + 3)).timestamp())
        
        res = finnhub_client.stock_candles(symbol, 'D', past, now)
        
        if res.get('s') != 'ok':
            raise ValueError(f"Finnhub returned status {res.get('s')}")

        closes = res.get('c', [])
        opens = res.get('o', [])
        highs = res.get('h', [])
        lows = res.get('l', [])
        times = res.get('t', [])
        vols = res.get('v', [])
        
        # Take only the last 'days' items
        closes = closes[-days:]
        opens = opens[-days:]
        highs = highs[-days:]
        lows = lows[-days:]
        times = times[-days:]
        vols = vols[-days:]

        history = []
        for i in range(len(closes)):
            history.append({
                "date":   datetime.fromtimestamp(times[i]).strftime('%Y-%m-%d'),
                "open":   round(opens[i], 2),
                "close":  round(closes[i], 2),
                "high":   round(highs[i], 2),
                "low":    round(lows[i], 2),
                "volume": int(vols[i]),
            })
            
        return history

    except Exception as exc:
        logger.warning(f"History fetch failed for {symbol}: {exc}. Simulating.")
        base    = SEED_PRICES.get(symbol, 100.0)
        history = []
        for i in range(days):
            sim = simulate_price(base)
            history.append({
                "date":   f"Day-{days - i}",
                "open":   base,
                "close":  sim["price"],
                "high":   round(sim["price"] * 1.01, 2),
                "low":    round(sim["price"] * 0.99, 2),
                "volume": random.randint(10_000_000, 80_000_000),
            })
            base = sim["price"]
        return history


def get_all_stocks() -> list:
    """Return current prices for all default symbols."""
    results = []
    # Fetching individually might hit rate limits on free tier (60/min), 
    # but for 12 stocks every 30s it averages 24/min which is safe.
    for symbol in DEFAULT_SYMBOLS:
        data = get_stock_price(symbol)
        if isinstance(data, dict) and "error" not in data:
            results.append(data)
    return results
