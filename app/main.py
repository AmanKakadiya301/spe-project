"""
main.py
-------
Flask REST API for the AutoDevOps FinTech Stock Analysis System.

Endpoints:
  GET /                           → Web dashboard (HTML)
  GET /health                     → Kubernetes liveness/readiness probe
  GET /api/stock/<symbol>         → Single stock price
  GET /api/stocks                 → All tracked stocks
  GET /api/stock/<symbol>/history → 7-day price history

Logging: Structured JSON logs to stdout — captured by ELK (Logstash).
"""

import os
import json
import logging
import time
from datetime import datetime

from flask import Flask, jsonify, render_template, request, abort
from dotenv import load_dotenv

from stock_data import get_stock_price, get_stock_history, get_all_stocks

# ── Load environment variables ────────────────────────────────────────────────
load_dotenv()

# ── Flask App ─────────────────────────────────────────────────────────────────
app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev-secret-change-in-prod")


# ── Structured JSON Logging (ELK-compatible) ──────────────────────────────────
class JSONFormatter(logging.Formatter):
    def format(self, record):
        entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level":     record.levelname,
            "service":   "stock-app",
            "message":   record.getMessage(),
            "module":    record.module,
        }
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry)


_handler = logging.StreamHandler()
_handler.setFormatter(JSONFormatter())
logging.basicConfig(level=logging.INFO, handlers=[_handler])
logger = logging.getLogger(__name__)


# ── Request Timing Middleware ─────────────────────────────────────────────────
@app.before_request
def _start_timer():
    request.start_time = time.time()


@app.after_request
def _log_request(response):
    duration_ms = round((time.time() - request.start_time) * 1000, 2)
    logger.info(json.dumps({
        "event":       "http_request",
        "method":      request.method,
        "path":        request.path,
        "status":      response.status_code,
        "duration_ms": duration_ms,
        "remote_addr": request.remote_addr,
    }))
    return response


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    """Serve the web dashboard."""
    return render_template("index.html")


@app.route("/health")
def health():
    """
    Kubernetes liveness & readiness probe.
    Returns HTTP 200 + JSON {status: ok} when the app is healthy.
    """
    return jsonify({
        "status":    "ok",
        "service":   "stock-app",
        "version":   os.getenv("APP_VERSION", "1.0.0"),
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }), 200


@app.route("/api/stock/<symbol>")
def get_stock(symbol):
    """
    GET /api/stock/AAPL
    Returns current price data for the requested symbol.
    404 if the symbol is unknown.
    """
    result = get_stock_price(symbol.upper())

    if "error" in result:
        abort(404, description=result["error"])

    logger.info(f"Stock served: {symbol.upper()} → ${result['price']}")
    return jsonify(result), 200


@app.route("/api/stocks")
def get_stocks():
    """
    GET /api/stocks
    Returns current price data for all tracked symbols.
    """
    stocks = get_all_stocks()
    return jsonify({
        "stocks":    stocks,
        "count":     len(stocks),
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }), 200


@app.route("/api/stock/<symbol>/history")
def get_history(symbol):
    """
    GET /api/stock/AAPL/history?days=7
    Returns OHLCV history for the past N days (1–30, default 7).
    """
    days    = request.args.get("days", 7, type=int)
    days    = min(max(days, 1), 30)        # clamp 1..30
    history = get_stock_history(symbol.upper(), days)

    if not history:
        abort(404, description=f"No history found for {symbol.upper()}")

    return jsonify({
        "symbol":  symbol.upper(),
        "days":    days,
        "history": history,
    }), 200


# ── Error Handlers ────────────────────────────────────────────────────────────
@app.errorhandler(404)
def not_found(exc):
    return jsonify({"error": "Not Found", "message": str(exc)}), 404


@app.errorhandler(500)
def server_error(exc):
    logger.error(f"Internal server error: {exc}")
    return jsonify({"error": "Internal Server Error"}), 500


# ── Entry Point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    port  = int(os.getenv("PORT", 5000))
    debug = os.getenv("FLASK_ENV", "production") == "development"
    logger.info(f"Starting Stock App on port {port} | debug={debug}")
    app.run(host="0.0.0.0", port=port, debug=debug)
