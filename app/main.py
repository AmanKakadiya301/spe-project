"""
main.py
-------
Flask REST API for the AutoDevOps FinTech Stock Analysis System.

Endpoints:
  GET /                               → Web dashboard (HTML)
  GET /login                          → Login/Register page
  GET /portfolio                      → Portfolio page (auth required)
  GET /alerts                         → Alerts page (auth required)
  GET /health                         → Kubernetes liveness/readiness probe
  POST /register                      → Register new user
  POST /do-login                      → Login user
  GET /logout                         → Logout user
  GET /api/stock/<symbol>             → Single stock quote
  GET /api/stocks                     → All tracked stocks
  GET /api/stock/<symbol>/history     → OHLCV history (days param)
  GET /api/stock/<symbol>/news        → Company news (Finnhub)
  GET /api/stock/<symbol>/profile     → Company profile
  GET /api/search/<query>             → Search/validate a ticker
  GET /api/suggest                    → Autocomplete suggestions
  GET /api/cache/stats                → Cache diagnostics
  POST /api/admin/symbols             → Add symbol to tracked list
  DELETE /api/admin/symbols/<symbol>  → Remove symbol from tracked list
  GET /api/portfolio                  → Get user's portfolio
  POST /api/portfolio                 → Add stock to portfolio
  DELETE /api/portfolio/<symbol>      → Remove stock from portfolio
  GET /api/alerts                     → Get user's alerts
  POST /api/alerts                    → Create a price alert
  DELETE /api/alerts/<id>             → Delete a price alert
  GET /api/me                         → Current user info

Logging: Structured JSON logs to stdout — captured by ELK (Logstash).
"""

import os
import json
import logging
import time
from datetime import datetime

from flask import Flask, jsonify, render_template, request, abort, redirect, url_for
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_bcrypt import Bcrypt
from dotenv import load_dotenv

from stock_data import (
    get_stock_price, get_stock_history, get_all_stocks, search_symbol,
    get_stock_news, get_company_profile, cache_stats,
    add_symbol, remove_symbol, get_tracked_symbols,
)
from models import db, User, PortfolioItem, Alert

# ── Load environment variables ────────────────────────────────────────────────
load_dotenv()

# ── Flask App ─────────────────────────────────────────────────────────────────
app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev-secret-change-in-prod")

# ── Database Config ───────────────────────────────────────────────────────────
basedir = os.path.abspath(os.path.dirname(__file__))
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + os.path.join(basedir, "instance", "app.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

os.makedirs(os.path.join(basedir, "instance"), exist_ok=True)

db.init_app(app)
bcrypt = Bcrypt(app)

# ── Flask-Login ───────────────────────────────────────────────────────────────
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login_page"


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


@login_manager.unauthorized_handler
def unauthorized():
    if request.path.startswith("/api/"):
        return jsonify({"error": "Authentication required"}), 401
    return redirect(url_for("login_page"))


# ── Create tables on first run ────────────────────────────────────────────────
with app.app_context():
    db.create_all()


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


# ── Page Routes ───────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/login")
def login_page():
    if current_user.is_authenticated:
        return redirect(url_for("index"))
    return render_template("login.html")


@app.route("/portfolio")
@login_required
def portfolio_page():
    return render_template("portfolio.html")


@app.route("/alerts")
@login_required
def alerts_page():
    return render_template("alerts.html")


# ── Auth Routes ───────────────────────────────────────────────────────────────

@app.route("/register", methods=["POST"])
def register():
    data     = request.get_json(silent=True) or {}
    username = data.get("username", "").strip()
    password = data.get("password", "").strip()

    if not username or not password:
        return jsonify({"error": "Username and password are required"}), 400
    if len(username) < 3:
        return jsonify({"error": "Username must be at least 3 characters"}), 400
    if len(password) < 4:
        return jsonify({"error": "Password must be at least 4 characters"}), 400
    if User.query.filter_by(username=username).first():
        return jsonify({"error": "Username already exists"}), 409

    pw_hash = bcrypt.generate_password_hash(password).decode("utf-8")
    user    = User(username=username, password_hash=pw_hash)
    db.session.add(user)
    db.session.commit()

    login_user(user)
    logger.info(f"User registered: {username}")
    return jsonify({"message": "Registered successfully", "username": username}), 201


@app.route("/do-login", methods=["POST"])
def do_login():
    data     = request.get_json(silent=True) or {}
    username = data.get("username", "").strip()
    password = data.get("password", "").strip()

    if not username or not password:
        return jsonify({"error": "Username and password are required"}), 400

    user = User.query.filter_by(username=username).first()
    if not user or not bcrypt.check_password_hash(user.password_hash, password):
        return jsonify({"error": "Invalid username or password"}), 401

    login_user(user)
    logger.info(f"User logged in: {username}")
    return jsonify({"message": "Login successful", "username": username}), 200


@app.route("/logout")
def logout():
    if current_user.is_authenticated:
        logger.info(f"User logged out: {current_user.username}")
    logout_user()
    return redirect(url_for("login_page"))


@app.route("/api/me")
def get_me():
    if current_user.is_authenticated:
        return jsonify({
            "authenticated": True,
            "username":      current_user.username,
            "id":            current_user.id,
        }), 200
    return jsonify({"authenticated": False}), 200


# ── Health ────────────────────────────────────────────────────────────────────

@app.route("/health")
def health():
    return jsonify({
        "status":    "ok",
        "service":   "stock-app",
        "version":   os.getenv("APP_VERSION", "1.0.0"),
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }), 200


# ── Stock API ─────────────────────────────────────────────────────────────────

@app.route("/api/stock/<symbol>")
def get_stock(symbol):
    """GET /api/stock/AAPL — current quote."""
    result = get_stock_price(symbol.upper())
    if "error" in result:
        abort(404, description=result["error"])
    logger.info(f"Stock served: {symbol.upper()} → ${result['price']}")
    return jsonify(result), 200


@app.route("/api/stocks")
def get_stocks():
    """GET /api/stocks — all tracked symbols in parallel."""
    stocks = get_all_stocks()
    gainers = sum(1 for s in stocks if s.get("change", 0) >= 0)
    return jsonify({
        "stocks":    stocks,
        "count":     len(stocks),
        "gainers":   gainers,
        "losers":    len(stocks) - gainers,
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }), 200


@app.route("/api/stock/<symbol>/history")
def get_history(symbol):
    """GET /api/stock/AAPL/history?days=7 — OHLCV candles."""
    days    = request.args.get("days", 7, type=int)
    days    = min(max(days, 1), 30)
    history = get_stock_history(symbol.upper(), days)

    if not history:
        abort(404, description=f"No history found for {symbol.upper()}")

    return jsonify({
        "symbol":  symbol.upper(),
        "days":    days,
        "history": history,
    }), 200


@app.route("/api/stock/<symbol>/news")
def get_news(symbol):
    """GET /api/stock/AAPL/news?count=5 — latest company news."""
    count = request.args.get("count", 5, type=int)
    count = min(max(count, 1), 20)
    news  = get_stock_news(symbol.upper(), count)
    return jsonify({
        "symbol": symbol.upper(),
        "count":  len(news),
        "news":   news,
    }), 200


@app.route("/api/stock/<symbol>/profile")
def get_profile(symbol):
    """GET /api/stock/AAPL/profile — company info."""
    profile = get_company_profile(symbol.upper())
    if not profile:
        return jsonify({"error": f"Profile not found for {symbol.upper()}"}), 404
    return jsonify(profile), 200


@app.route("/api/search/<query>")
def search_stock(query):
    """GET /api/search/AAPL — validate if a ticker exists."""
    result = search_symbol(query)
    if "error" in result:
        return jsonify(result), 404
    return jsonify(result), 200


@app.route("/api/suggest")
def suggest_stocks():
    """GET /api/suggest?q=net — autocomplete ticker suggestions."""
    query = request.args.get("q", "").strip()
    if not query:
        return jsonify({"suggestions": []}), 200

    try:
        from stock_data import finnhub_client
        if not finnhub_client:
            return jsonify({"suggestions": []}), 200

        res         = finnhub_client.symbol_search(query)
        suggestions = []
        for item in res.get("result", [])[:8]:
            suggestions.append({
                "symbol":      item.get("symbol", ""),
                "description": item.get("description", ""),
                "type":        item.get("type", ""),
            })
        return jsonify({"suggestions": suggestions}), 200
    except Exception as exc:
        logger.warning(f"Suggest failed for '{query}': {exc}")
        return jsonify({"suggestions": []}), 200


# ── Cache Diagnostics ─────────────────────────────────────────────────────────

@app.route("/api/cache/stats")
def get_cache_stats():
    """GET /api/cache/stats — for admin panel / monitoring."""
    return jsonify(cache_stats()), 200


# ── Admin: Symbol Management ──────────────────────────────────────────────────

@app.route("/api/admin/symbols", methods=["GET"])
def list_symbols():
    """GET /api/admin/symbols — list all currently tracked symbols."""
    return jsonify({"symbols": get_tracked_symbols()}), 200


@app.route("/api/admin/symbols", methods=["POST"])
@login_required
def admin_add_symbol():
    """POST /api/admin/symbols — add a symbol to the live tracking list."""
    data   = request.get_json(silent=True) or {}
    symbol = data.get("symbol", "").upper().strip()

    if not symbol:
        return jsonify({"error": "symbol is required"}), 400

    # Validate it exists before adding
    check = search_symbol(symbol)
    if not check.get("valid"):
        return jsonify({"error": f"'{symbol}' is not a valid ticker"}), 400

    added = add_symbol(symbol)
    if not added:
        return jsonify({"message": f"{symbol} is already tracked"}), 200

    logger.info(f"Symbol added to tracking: {symbol} by {current_user.username}")
    return jsonify({"message": f"{symbol} added to tracking", "symbols": get_tracked_symbols()}), 201


@app.route("/api/admin/symbols/<symbol>", methods=["DELETE"])
@login_required
def admin_remove_symbol(symbol):
    """DELETE /api/admin/symbols/AAPL — remove a symbol from tracking."""
    symbol  = symbol.upper()
    removed = remove_symbol(symbol)

    if not removed:
        return jsonify({"error": f"{symbol} is not in the tracked list"}), 404

    logger.info(f"Symbol removed from tracking: {symbol} by {current_user.username}")
    return jsonify({"message": f"{symbol} removed", "symbols": get_tracked_symbols()}), 200


# ── Portfolio API ─────────────────────────────────────────────────────────────

@app.route("/api/portfolio", methods=["GET"])
@login_required
def get_portfolio():
    items     = PortfolioItem.query.filter_by(user_id=current_user.id).all()
    portfolio = []
    for item in items:
        stock = get_stock_price(item.symbol)
        entry = item.to_dict()
        if "error" not in stock:
            entry.update({
                "price":          stock["price"],
                "change":         stock["change"],
                "change_pct":     stock["change_pct"],
                "previous_close": stock.get("previous_close", 0),
                "source":         stock["source"],
            })
        portfolio.append(entry)
    return jsonify({"portfolio": portfolio, "count": len(portfolio)}), 200


@app.route("/api/portfolio", methods=["POST"])
@login_required
def add_to_portfolio():
    data   = request.get_json(silent=True) or {}
    symbol = data.get("symbol", "").upper().strip()

    if not symbol:
        return jsonify({"error": "Symbol is required"}), 400

    exists = PortfolioItem.query.filter_by(user_id=current_user.id, symbol=symbol).first()
    if exists:
        return jsonify({"error": f"{symbol} is already in your portfolio"}), 409

    item = PortfolioItem(user_id=current_user.id, symbol=symbol)
    db.session.add(item)
    db.session.commit()

    logger.info(f"Portfolio add: {current_user.username} → {symbol}")
    return jsonify({"message": f"{symbol} added to portfolio", "item": item.to_dict()}), 201


@app.route("/api/portfolio/<symbol>", methods=["DELETE"])
@login_required
def remove_from_portfolio(symbol):
    symbol = symbol.upper()
    item   = PortfolioItem.query.filter_by(user_id=current_user.id, symbol=symbol).first()
    if not item:
        return jsonify({"error": f"{symbol} not found in your portfolio"}), 404

    db.session.delete(item)
    db.session.commit()

    logger.info(f"Portfolio remove: {current_user.username} → {symbol}")
    return jsonify({"message": f"{symbol} removed from portfolio"}), 200


# ── Alerts API ────────────────────────────────────────────────────────────────

@app.route("/api/alerts", methods=["GET"])
@login_required
def get_alerts():
    alerts = Alert.query.filter_by(user_id=current_user.id).order_by(Alert.created_at.desc()).all()
    return jsonify({"alerts": [a.to_dict() for a in alerts], "count": len(alerts)}), 200


@app.route("/api/alerts", methods=["POST"])
@login_required
def create_alert():
    data         = request.get_json(silent=True) or {}
    symbol       = data.get("symbol", "").upper().strip()
    target_price = data.get("target_price")
    direction    = data.get("direction", "").lower().strip()

    if not symbol or target_price is None or direction not in ("above", "below"):
        return jsonify({"error": "symbol, target_price, and direction (above/below) are required"}), 400

    try:
        target_price = float(target_price)
    except (ValueError, TypeError):
        return jsonify({"error": "target_price must be a number"}), 400

    alert = Alert(
        user_id=current_user.id,
        symbol=symbol,
        target_price=target_price,
        direction=direction,
    )
    db.session.add(alert)
    db.session.commit()

    logger.info(f"Alert created: {current_user.username} → {symbol} {direction} ${target_price}")
    return jsonify({"message": "Alert created", "alert": alert.to_dict()}), 201


@app.route("/api/alerts/<int:alert_id>", methods=["DELETE"])
@login_required
def delete_alert(alert_id):
    alert = Alert.query.filter_by(id=alert_id, user_id=current_user.id).first()
    if not alert:
        return jsonify({"error": "Alert not found"}), 404

    db.session.delete(alert)
    db.session.commit()

    logger.info(f"Alert deleted: {current_user.username} → alert #{alert_id}")
    return jsonify({"message": "Alert deleted"}), 200


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
