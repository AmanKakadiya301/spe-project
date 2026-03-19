"""
main.py — AutoDevOps FinTech Stock App v2
REPLACE existing app/main.py
All features wired: OAuth, rate limiting, metrics, tracing, audit log,
                    alert worker, snapshot thread, admin routes.
"""

import os
import sys
import json
import logging
import time
import threading
from datetime import datetime, timedelta
from functools import wraps

from flask import Flask, jsonify, render_template, request, abort, redirect, url_for
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_bcrypt import Bcrypt
from dotenv import load_dotenv

# ── Env ───────────────────────────────────────────────────────────────────────
load_dotenv()

# ── App ───────────────────────────────────────────────────────────────────────
app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev-secret-change-in-prod")

# ── Database ──────────────────────────────────────────────────────────────────
basedir   = os.path.abspath(os.path.dirname(__file__))
_sqlite   = "sqlite:///" + os.path.join(basedir, "instance", "app.db")
app.config["SQLALCHEMY_DATABASE_URI"]  = os.getenv("DATABASE_URL", _sqlite)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"pool_pre_ping": True, "pool_recycle": 300}
os.makedirs(os.path.join(basedir, "instance"), exist_ok=True)

# ── Extensions ────────────────────────────────────────────────────────────────
from models import db, User, PortfolioItem, Alert, AuditLog, TrackedSymbol, PriceSnapshot, seed_defaults
db.init_app(app)
bcrypt = Bcrypt(app)

# ── Observability ─────────────────────────────────────────────────────────────
try:
    from metrics import init_metrics
    init_metrics(app)
except Exception as e:
    logging.warning(f"Metrics init failed: {e}")

try:
    from tracing.otel import init_tracing
    init_tracing(app)
except Exception as e:
    logging.warning(f"Tracing init failed: {e}")

# ── Rate Limiting ─────────────────────────────────────────────────────────────
try:
    from auth.rate_limit import limiter
    limiter.init_app(app)
except Exception as e:
    logging.warning(f"Rate limiter init failed: {e}")
    limiter = None

# ── Google OAuth ──────────────────────────────────────────────────────────────
try:
    from auth.google_oauth import google_auth
    app.register_blueprint(google_auth)
except Exception as e:
    logging.warning(f"Google OAuth blueprint failed: {e}")

# ── Cache ─────────────────────────────────────────────────────────────────────
try:
    from cache_service import cache
except Exception:
    cache = None

# ── Stock data ────────────────────────────────────────────────────────────────
from stock_data import (
    get_stock_price, get_stock_history, get_all_stocks, search_symbol,
    get_stock_news, get_company_profile, cache_stats,
    add_symbol, remove_symbol, get_tracked_symbols,
)

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

# ── DB init + seed ────────────────────────────────────────────────────────────
with app.app_context():
    db.create_all()
    seed_defaults()

# ── Structured JSON Logging ───────────────────────────────────────────────────
class JSONFormatter(logging.Formatter):
    def format(self, record):
        entry = {"timestamp": datetime.utcnow().isoformat()+"Z", "level": record.levelname,
                 "service": "stock-app", "message": record.getMessage(), "module": record.module}
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry)

_handler = logging.StreamHandler()
_handler.setFormatter(JSONFormatter())
logging.basicConfig(level=logging.INFO, handlers=[_handler])
logger = logging.getLogger(__name__)

# ── Request timing ────────────────────────────────────────────────────────────
@app.before_request
def _start_timer():
    request.start_time = time.time()

@app.after_request
def _log_request(response):
    ms = round((time.time() - request.start_time) * 1000, 2)
    logger.info(json.dumps({"event": "http_request", "method": request.method,
                             "path": request.path, "status": response.status_code,
                             "duration_ms": ms, "remote_addr": request.remote_addr}))
    return response

# ── Background: Price Snapshots ───────────────────────────────────────────────
def _snapshot_worker():
    time.sleep(30)
    while True:
        try:
            with app.app_context():
                stocks = get_all_stocks()
                now    = datetime.utcnow()
                cutoff = now - timedelta(days=7)
                for s in stocks:
                    db.session.add(PriceSnapshot(
                        symbol=s["symbol"], price=s["price"],
                        change=s.get("change"), change_pct=s.get("change_pct"),
                        source=s.get("source"), captured_at=now))
                PriceSnapshot.query.filter(PriceSnapshot.captured_at < cutoff).delete()
                db.session.commit()
        except Exception as exc:
            logger.warning(f"Snapshot worker: {exc}")
        time.sleep(60)

threading.Thread(target=_snapshot_worker, daemon=True).start()

# ── Alert worker ──────────────────────────────────────────────────────────────
try:
    from alert_worker import start_alert_worker
    start_alert_worker(app)
except Exception as e:
    logger.warning(f"Alert worker failed to start: {e}")

# ── Admin guard ───────────────────────────────────────────────────────────────
def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            return jsonify({"error": "Authentication required"}), 401
        if not current_user.is_admin():
            return jsonify({"error": "Admin access required"}), 403
        return f(*args, **kwargs)
    return decorated

# ═══════════════════════════════════════════════════════════════════════════════
# PAGE ROUTES
# ═══════════════════════════════════════════════════════════════════════════════

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

# ═══════════════════════════════════════════════════════════════════════════════
# AUTH
# ═══════════════════════════════════════════════════════════════════════════════

@app.route("/register", methods=["POST"])
def register():
    data     = request.get_json(silent=True) or {}
    username = data.get("username","").strip()
    password = data.get("password","").strip()
    if not username or not password:
        return jsonify({"error": "Username and password required"}), 400
    if len(username) < 3:
        return jsonify({"error": "Username min 3 chars"}), 400
    if len(password) < 4:
        return jsonify({"error": "Password min 4 chars"}), 400
    if User.query.filter_by(username=username).first():
        return jsonify({"error": "Username already exists"}), 409

    user = User(username=username, password_hash=bcrypt.generate_password_hash(password).decode())
    db.session.add(user)
    AuditLog.log("register", user=user, ip=request.remote_addr)
    db.session.commit()
    login_user(user)
    return jsonify({"message": "Registered", "username": username}), 201


@app.route("/do-login", methods=["POST"])
def do_login():
    data     = request.get_json(silent=True) or {}
    username = data.get("username","").strip()
    password = data.get("password","").strip()
    if not username or not password:
        return jsonify({"error": "Username and password required"}), 400

    user = User.query.filter_by(username=username).first()
    if not user or not bcrypt.check_password_hash(user.password_hash or "", password):
        return jsonify({"error": "Invalid credentials"}), 401

    user.last_login = datetime.utcnow()
    login_user(user)
    AuditLog.log("login", user=user, ip=request.remote_addr)
    db.session.commit()
    return jsonify({"message": "Login successful", "username": username, "role": user.role}), 200


@app.route("/logout")
def logout():
    if current_user.is_authenticated:
        AuditLog.log("logout", user=current_user, ip=request.remote_addr)
        db.session.commit()
    logout_user()
    return redirect(url_for("login_page"))


@app.route("/api/me")
def get_me():
    if current_user.is_authenticated:
        return jsonify({"authenticated": True, "username": current_user.username,
                        "id": current_user.id, "role": current_user.role,
                        "email": current_user.email, "avatar_url": current_user.avatar_url}), 200
    return jsonify({"authenticated": False}), 200

# ═══════════════════════════════════════════════════════════════════════════════
# HEALTH
# ═══════════════════════════════════════════════════════════════════════════════

@app.route("/health")
def health():
    db_ok = True
    try:
        db.session.execute(db.text("SELECT 1"))
    except Exception:
        db_ok = False
    stats = cache.stats() if cache else {"backend": "none"}
    return jsonify({
        "status": "ok" if db_ok else "degraded",
        "service": "stock-app", "version": os.getenv("APP_VERSION","2.0.0"),
        "database": "ok" if db_ok else "error", "cache": stats["backend"],
        "timestamp": datetime.utcnow().isoformat()+"Z",
    }), 200 if db_ok else 503

# ═══════════════════════════════════════════════════════════════════════════════
# STOCK API
# ═══════════════════════════════════════════════════════════════════════════════

@app.route("/api/stock/<symbol>")
def get_stock(symbol):
    result = get_stock_price(symbol.upper())
    if "error" in result:
        abort(404, description=result["error"])
    return jsonify(result), 200


@app.route("/api/stocks")
def get_stocks():
    stocks  = get_all_stocks()
    gainers = sum(1 for s in stocks if s.get("change", 0) >= 0)
    return jsonify({"stocks": stocks, "count": len(stocks), "gainers": gainers,
                    "losers": len(stocks)-gainers, "timestamp": datetime.utcnow().isoformat()+"Z"}), 200


@app.route("/api/stock/<symbol>/history")
def get_history(symbol):
    days    = min(max(request.args.get("days", 7, type=int), 1), 30)
    history = get_stock_history(symbol.upper(), days)
    if not history:
        abort(404, description=f"No history for {symbol.upper()}")
    return jsonify({"symbol": symbol.upper(), "days": days, "history": history}), 200


@app.route("/api/stock/<symbol>/news")
def get_news(symbol):
    count = min(max(request.args.get("count", 5, type=int), 1), 20)
    news  = get_stock_news(symbol.upper(), count)
    return jsonify({"symbol": symbol.upper(), "count": len(news), "news": news}), 200


@app.route("/api/stock/<symbol>/profile")
def get_profile(symbol):
    profile = get_company_profile(symbol.upper())
    if not profile:
        return jsonify({"error": f"Profile not found for {symbol.upper()}"}), 404
    return jsonify(profile), 200


@app.route("/api/stock/<symbol>/snapshots")
def get_snapshots(symbol):
    hours  = min(max(request.args.get("hours", 24, type=int), 1), 168)
    cutoff = datetime.utcnow() - timedelta(hours=hours)
    snaps  = (PriceSnapshot.query.filter_by(symbol=symbol.upper())
              .filter(PriceSnapshot.captured_at >= cutoff)
              .order_by(PriceSnapshot.captured_at.asc()).all())
    return jsonify({"symbol": symbol.upper(), "hours": hours,
                    "snapshots": [s.to_dict() for s in snaps]}), 200


@app.route("/api/search/<query>")
def search_stock(query):
    result = search_symbol(query)
    if "error" in result:
        return jsonify(result), 404
    return jsonify(result), 200


@app.route("/api/suggest")
def suggest_stocks():
    query = request.args.get("q","").strip()
    if not query:
        return jsonify({"suggestions": []}), 200
    try:
        from stock_data import finnhub_client
        if not finnhub_client:
            return jsonify({"suggestions": []}), 200
        res = finnhub_client.symbol_search(query)
        suggestions = [{"symbol": i.get("symbol",""), "description": i.get("description",""),
                        "type": i.get("type","")} for i in res.get("result",[])[:8]]
        return jsonify({"suggestions": suggestions}), 200
    except Exception as exc:
        logger.warning(f"Suggest failed '{query}': {exc}")
        return jsonify({"suggestions": []}), 200

# ═══════════════════════════════════════════════════════════════════════════════
# CACHE
# ═══════════════════════════════════════════════════════════════════════════════

@app.route("/api/cache/stats")
def get_cache_stats():
    return jsonify(cache_stats()), 200


@app.route("/api/cache/flush", methods=["POST"])
@admin_required
def flush_cache():
    if cache:
        cache.flush()
    AuditLog.log("cache_flush", user=current_user, ip=request.remote_addr)
    db.session.commit()
    return jsonify({"message": "Cache flushed"}), 200

# ═══════════════════════════════════════════════════════════════════════════════
# ADMIN: SYMBOLS
# ═══════════════════════════════════════════════════════════════════════════════

@app.route("/api/admin/symbols", methods=["GET"])
def list_symbols():
    symbols = TrackedSymbol.query.filter_by(is_active=True).all()
    return jsonify({"symbols": [s.to_dict() for s in symbols]}), 200


@app.route("/api/admin/symbols", methods=["POST"])
@admin_required
def admin_add_symbol():
    data   = request.get_json(silent=True) or {}
    symbol = data.get("symbol","").upper().strip()
    if not symbol:
        return jsonify({"error": "symbol required"}), 400
    check = search_symbol(symbol)
    if not check.get("valid"):
        return jsonify({"error": f"'{symbol}' is not a valid ticker"}), 400
    existing = TrackedSymbol.query.filter_by(symbol=symbol).first()
    if existing:
        existing.is_active = True
        db.session.commit()
        return jsonify({"message": f"{symbol} re-activated"}), 200
    ts = TrackedSymbol(symbol=symbol, name=check.get("description", symbol), added_by=current_user.id)
    db.session.add(ts)
    add_symbol(symbol)
    AuditLog.log("add_symbol", target=symbol, user=current_user, ip=request.remote_addr)
    db.session.commit()
    return jsonify({"message": f"{symbol} added", "symbol": ts.to_dict()}), 201


@app.route("/api/admin/symbols/<symbol>", methods=["DELETE"])
@admin_required
def admin_remove_symbol(symbol):
    symbol = symbol.upper()
    ts     = TrackedSymbol.query.filter_by(symbol=symbol).first()
    if not ts:
        return jsonify({"error": f"{symbol} not found"}), 404
    ts.is_active = False
    remove_symbol(symbol)
    AuditLog.log("remove_symbol", target=symbol, user=current_user, ip=request.remote_addr)
    db.session.commit()
    return jsonify({"message": f"{symbol} removed"}), 200

# ═══════════════════════════════════════════════════════════════════════════════
# ADMIN: USERS
# ═══════════════════════════════════════════════════════════════════════════════

@app.route("/api/admin/users", methods=["GET"])
@admin_required
def admin_list_users():
    users = User.query.order_by(User.created_at.desc()).all()
    return jsonify({"users": [u.to_dict() for u in users], "count": len(users)}), 200


@app.route("/api/admin/users/<int:uid>/role", methods=["PATCH"])
@admin_required
def admin_set_role(uid):
    data = request.get_json(silent=True) or {}
    role = data.get("role","").lower().strip()
    if role not in ("user","admin"):
        return jsonify({"error": "role must be user or admin"}), 400
    user = db.session.get(User, uid)
    if not user:
        return jsonify({"error": "User not found"}), 404
    old = user.role
    user.role = role
    AuditLog.log("change_role", target=f"user#{uid} {old}→{role}", user=current_user, ip=request.remote_addr)
    db.session.commit()
    return jsonify({"message": f"Role updated to {role}", "user": user.to_dict()}), 200


@app.route("/api/admin/users/<int:uid>/toggle", methods=["PATCH"])
@admin_required
def admin_toggle_user(uid):
    user = db.session.get(User, uid)
    if not user:
        return jsonify({"error": "User not found"}), 404
    if user.id == current_user.id:
        return jsonify({"error": "Cannot deactivate yourself"}), 400
    user.is_active = not user.is_active
    AuditLog.log("toggle_user", target=f"user#{uid}", user=current_user, ip=request.remote_addr)
    db.session.commit()
    return jsonify({"message": "User updated", "user": user.to_dict()}), 200


@app.route("/api/admin/audit", methods=["GET"])
@admin_required
def admin_audit_log():
    limit  = min(request.args.get("limit", 50, type=int), 200)
    offset = request.args.get("offset", 0, type=int)
    logs   = (AuditLog.query.order_by(AuditLog.created_at.desc()).limit(limit).offset(offset).all())
    return jsonify({"logs": [l.to_dict() for l in logs], "count": len(logs)}), 200

# ═══════════════════════════════════════════════════════════════════════════════
# PORTFOLIO
# ═══════════════════════════════════════════════════════════════════════════════

@app.route("/api/portfolio", methods=["GET"])
@login_required
def get_portfolio():
    items = PortfolioItem.query.filter_by(user_id=current_user.id).all()
    result = []
    for item in items:
        stock = get_stock_price(item.symbol)
        entry = item.to_dict()
        if "error" not in stock:
            entry.update({"price": stock["price"], "change": stock["change"],
                          "change_pct": stock["change_pct"],
                          "previous_close": stock.get("previous_close",0),
                          "source": stock["source"]})
        result.append(entry)
    return jsonify({"portfolio": result, "count": len(result)}), 200


@app.route("/api/portfolio", methods=["POST"])
@login_required
def add_to_portfolio():
    data   = request.get_json(silent=True) or {}
    symbol = data.get("symbol","").upper().strip()
    if not symbol:
        return jsonify({"error": "Symbol required"}), 400
    if PortfolioItem.query.filter_by(user_id=current_user.id, symbol=symbol).first():
        return jsonify({"error": f"{symbol} already in portfolio"}), 409
    item = PortfolioItem(user_id=current_user.id, symbol=symbol,
                         shares=data.get("shares",0), avg_price=data.get("avg_price",0))
    db.session.add(item)
    AuditLog.log("portfolio_add", target=symbol, user=current_user, ip=request.remote_addr)
    db.session.commit()
    return jsonify({"message": f"{symbol} added", "item": item.to_dict()}), 201


@app.route("/api/portfolio/<symbol>", methods=["DELETE"])
@login_required
def remove_from_portfolio(symbol):
    symbol = symbol.upper()
    item   = PortfolioItem.query.filter_by(user_id=current_user.id, symbol=symbol).first()
    if not item:
        return jsonify({"error": f"{symbol} not in portfolio"}), 404
    db.session.delete(item)
    AuditLog.log("portfolio_remove", target=symbol, user=current_user, ip=request.remote_addr)
    db.session.commit()
    return jsonify({"message": f"{symbol} removed"}), 200

# ═══════════════════════════════════════════════════════════════════════════════
# ALERTS
# ═══════════════════════════════════════════════════════════════════════════════

@app.route("/api/alerts", methods=["GET"])
@login_required
def get_alerts():
    alerts = Alert.query.filter_by(user_id=current_user.id).order_by(Alert.created_at.desc()).all()
    return jsonify({"alerts": [a.to_dict() for a in alerts], "count": len(alerts)}), 200


@app.route("/api/alerts", methods=["POST"])
@login_required
def create_alert():
    data         = request.get_json(silent=True) or {}
    symbol       = data.get("symbol","").upper().strip()
    target_price = data.get("target_price")
    direction    = data.get("direction","").lower().strip()
    if not symbol or target_price is None or direction not in ("above","below"):
        return jsonify({"error": "symbol, target_price, direction (above/below) required"}), 400
    try:
        target_price = float(target_price)
    except (ValueError, TypeError):
        return jsonify({"error": "target_price must be a number"}), 400

    alert = Alert(user_id=current_user.id, symbol=symbol,
                  target_price=target_price, direction=direction)
    db.session.add(alert)
    AuditLog.log("create_alert", target=f"{symbol} {direction} ${target_price}",
                 user=current_user, ip=request.remote_addr)
    db.session.commit()
    return jsonify({"message": "Alert created", "alert": alert.to_dict()}), 201


@app.route("/api/alerts/<int:alert_id>", methods=["DELETE"])
@login_required
def delete_alert(alert_id):
    alert = Alert.query.filter_by(id=alert_id, user_id=current_user.id).first()
    if not alert:
        return jsonify({"error": "Alert not found"}), 404
    db.session.delete(alert)
    AuditLog.log("delete_alert", target=f"alert#{alert_id}", user=current_user, ip=request.remote_addr)
    db.session.commit()
    return jsonify({"message": "Alert deleted"}), 200

# ═══════════════════════════════════════════════════════════════════════════════
# ERROR HANDLERS
# ═══════════════════════════════════════════════════════════════════════════════

@app.errorhandler(404)
def not_found(exc):
    return jsonify({"error": "Not Found", "message": str(exc)}), 404

@app.errorhandler(429)
def rate_limited(exc):
    return jsonify({"error": "Too many requests", "retry_after": "60s"}), 429

@app.errorhandler(500)
def server_error(exc):
    logger.error(f"Internal error: {exc}")
    return jsonify({"error": "Internal Server Error"}), 500

# ═══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    port  = int(os.getenv("PORT", 5000))
    debug = os.getenv("FLASK_ENV","production") == "development"
    logger.info(f"Starting Stock App v2 on port {port} | debug={debug}")
    app.run(host="0.0.0.0", port=port, debug=debug)
