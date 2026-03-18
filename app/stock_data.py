"""
stock_data.py
-------------
Handles all stock price fetching logic.
Uses yfinance for real data, falls back to random-walk simulation if unavailable.
Accepts ANY ticker symbol — no hardcoded limit.
"""

import yfinance as yf
import random
import time
import logging

logger = logging.getLogger(__name__)

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
    Validate whether a ticker symbol exists via yfinance.
    Returns basic info if found, or error dict if not.
    """
    query = query.upper().strip()
    if not query:
        return {"error": "Empty query"}
    try:
        ticker = yf.Ticker(query)
        info = ticker.fast_info
        price = info.last_price
        if price is None:
            return {"error": f"Symbol '{query}' not found"}
        return {
            "symbol": query,
            "price": round(price, 2),
            "valid": True,
        }
    except Exception:
        return {"error": f"Symbol '{query}' not found"}


def get_stock_price(symbol: str) -> dict:
    """
    Fetch real-time stock price for a given symbol.
    Accepts ANY valid ticker symbol (not just defaults).
    Falls back to simulation if yfinance is unavailable.
    """
    symbol = symbol.upper()
    try:
        ticker      = yf.Ticker(symbol)
        info        = ticker.fast_info
        current     = info.last_price
        prev_close  = info.previous_close

        if current is None:
            raise ValueError("No price data returned from yfinance")

        change      = round(current - prev_close, 2)
        change_pct  = round((change / prev_close) * 100, 2) if prev_close else 0.0

        logger.info(f"Live price fetched — {symbol}: ${current}")

        return {
            "symbol":         symbol,
            "price":          round(current, 2),
            "previous_close": round(prev_close, 2),
            "change":         change,
            "change_pct":     change_pct,
            "source":         "live",
            "timestamp":      int(time.time()),
        }

    except Exception as exc:
        logger.warning(f"yfinance failed for {symbol}: {exc}. Using simulation.")

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
    Return OHLCV history for the past N days.
    Used for sparkline charts in the frontend.
    """
    symbol = symbol.upper()
    try:
        ticker = yf.Ticker(symbol)
        hist   = ticker.history(period=f"{days}d")

        if hist.empty:
            raise ValueError("Empty history returned")

        return [
            {
                "date":   str(date.date()),
                "open":   round(row["Open"], 2),
                "close":  round(row["Close"], 2),
                "high":   round(row["High"], 2),
                "low":    round(row["Low"], 2),
                "volume": int(row["Volume"]),
            }
            for date, row in hist.iterrows()
        ]

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
    for symbol in DEFAULT_SYMBOLS:
        data = get_stock_price(symbol)
        if isinstance(data, dict) and "error" not in data:
            results.append(data)
    return results
