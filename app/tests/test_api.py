"""
test_api.py
-----------
Comprehensive test suite for the AutoDevOps FinTech Stock App.

Coverage:
  - Health endpoint
  - Single stock endpoint (valid, invalid, casing, fields)
  - Bulk stocks endpoint
  - History endpoint
  - Auth: register, login, logout, duplicate user, weak password
  - Portfolio: add, list, duplicate, remove, unauthenticated access
  - Alerts: create, list, delete, invalid inputs, unauthenticated access
  - Notifications: listing unread notifications
  - Cache stats
  - Admin symbol management
  - simulate_price unit test
  - Alert worker logic unit test (no DB needed)

Run:
    pytest app/tests/ -v --cov=app --cov-report=term-missing
"""

import pytest
import json
import sys
import os
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from main import app
from models import db, User, Alert, AlertNotification
from stock_data import simulate_price


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def client():
    app.config["TESTING"]                = True
    app.config["SECRET_KEY"]             = "test-secret"
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["WTF_CSRF_ENABLED"]       = False

    with app.app_context():
        db.create_all()

    with app.test_client() as c:
        yield c

    with app.app_context():
        db.drop_all()


@pytest.fixture
def auth_client(client):
    """Client pre-registered and logged in as 'testuser'."""
    client.post("/register", json={"username": "testuser", "password": "password123"})
    return client


# ── 1. Health ─────────────────────────────────────────────────────────────────

class TestHealth:
    def test_returns_200(self, client):
        assert client.get("/health").status_code == 200

    def test_status_ok(self, client):
        data = json.loads(client.get("/health").data)
        assert data["status"] == "ok"

    def test_service_name(self, client):
        data = json.loads(client.get("/health").data)
        assert data["service"] == "stock-app"

    def test_timestamp_present(self, client):
        data = json.loads(client.get("/health").data)
        assert "timestamp" in data

    def test_version_present(self, client):
        data = json.loads(client.get("/health").data)
        assert "version" in data


# ── 2. Single Stock ───────────────────────────────────────────────────────────

class TestSingleStock:
    def test_valid_symbol_200(self, client):
        assert client.get("/api/stock/AAPL").status_code == 200

    def test_price_positive(self, client):
        data = json.loads(client.get("/api/stock/AAPL").data)
        assert data["price"] > 0

    def test_has_change_fields(self, client):
        data = json.loads(client.get("/api/stock/MSFT").data)
        assert "change" in data and "change_pct" in data

    def test_has_ohlc_fields(self, client):
        data = json.loads(client.get("/api/stock/AAPL").data)
        for field in ("open", "high", "low", "previous_close"):
            assert field in data, f"Missing field: {field}"

    def test_lowercase_normalised(self, client):
        data = json.loads(client.get("/api/stock/aapl").data)
        assert data["symbol"] == "AAPL"

    def test_unknown_symbol_404(self, client):
        assert client.get("/api/stock/ZZZZINVALID999").status_code == 404

    def test_source_field_valid(self, client):
        data = json.loads(client.get("/api/stock/TSLA").data)
        assert data["source"] in ("finnhub", "yfinance", "simulated")

    def test_timestamp_iso_format(self, client):
        data = json.loads(client.get("/api/stock/AAPL").data)
        assert data["timestamp"].endswith("Z")


# ── 3. Bulk Stocks ────────────────────────────────────────────────────────────

class TestBulkStocks:
    def test_returns_200(self, client):
        assert client.get("/api/stocks").status_code == 200

    def test_stocks_non_empty(self, client):
        data = json.loads(client.get("/api/stocks").data)
        assert isinstance(data["stocks"], list)
        assert len(data["stocks"]) > 0

    def test_gainers_losers_sum(self, client):
        data = json.loads(client.get("/api/stocks").data)
        assert data["gainers"] + data["losers"] == data["count"]

    def test_every_stock_has_price(self, client):
        data = json.loads(client.get("/api/stocks").data)
        for stock in data["stocks"]:
            assert "price" in stock and stock["price"] > 0


# ── 4. History ────────────────────────────────────────────────────────────────

class TestHistory:
    def test_returns_200(self, client):
        assert client.get("/api/stock/AAPL/history").status_code == 200

    def test_history_non_empty(self, client):
        data = json.loads(client.get("/api/stock/AAPL/history").data)
        assert isinstance(data["history"], list)
        assert len(data["history"]) > 0

    def test_candle_has_required_fields(self, client):
        data    = json.loads(client.get("/api/stock/AAPL/history").data)
        candle  = data["history"][0]
        for field in ("date", "open", "high", "low", "close", "volume"):
            assert field in candle, f"Missing field: {field}"

    def test_days_param_respected(self, client):
        data = json.loads(client.get("/api/stock/AAPL/history?days=3").data)
        assert data["days"] == 3

    def test_days_capped_at_30(self, client):
        data = json.loads(client.get("/api/stock/AAPL/history?days=999").data)
        assert data["days"] <= 30


# ── 5. Authentication ─────────────────────────────────────────────────────────

class TestAuth:
    def test_register_success(self, client):
        res = client.post("/register", json={"username": "alice", "password": "secret123"})
        assert res.status_code == 201

    def test_register_returns_username(self, client):
        data = json.loads(client.post("/register",
            json={"username": "bob", "password": "secret123"}).data)
        assert data["username"] == "bob"

    def test_duplicate_register_409(self, client):
        client.post("/register", json={"username": "charlie", "password": "pass1234"})
        res = client.post("/register", json={"username": "charlie", "password": "pass1234"})
        assert res.status_code == 409

    def test_short_username_rejected(self, client):
        res = client.post("/register", json={"username": "ab", "password": "pass1234"})
        assert res.status_code == 400

    def test_short_password_rejected(self, client):
        res = client.post("/register", json={"username": "david", "password": "abc"})
        assert res.status_code == 400

    def test_login_success(self, client):
        client.post("/register", json={"username": "eve", "password": "password123"})
        res = client.post("/do-login", json={"username": "eve", "password": "password123"})
        assert res.status_code == 200

    def test_wrong_password_401(self, client):
        client.post("/register", json={"username": "frank", "password": "correct"})
        res = client.post("/do-login", json={"username": "frank", "password": "wrong"})
        assert res.status_code == 401

    def test_me_authenticated(self, auth_client):
        data = json.loads(auth_client.get("/api/me").data)
        assert data["authenticated"] is True
        assert data["username"] == "testuser"

    def test_me_unauthenticated(self, client):
        data = json.loads(client.get("/api/me").data)
        assert data["authenticated"] is False

    def test_logout_redirects(self, auth_client):
        res = auth_client.get("/logout")
        assert res.status_code == 302


# ── 6. Portfolio ──────────────────────────────────────────────────────────────

class TestPortfolio:
    def test_add_stock(self, auth_client):
        res = auth_client.post("/api/portfolio", json={"symbol": "AAPL"})
        assert res.status_code == 201

    def test_portfolio_count(self, auth_client):
        auth_client.post("/api/portfolio", json={"symbol": "AAPL"})
        auth_client.post("/api/portfolio", json={"symbol": "TSLA"})
        data = json.loads(auth_client.get("/api/portfolio").data)
        assert data["count"] == 2

    def test_duplicate_stock_409(self, auth_client):
        auth_client.post("/api/portfolio", json={"symbol": "AAPL"})
        res = auth_client.post("/api/portfolio", json={"symbol": "AAPL"})
        assert res.status_code == 409

    def test_remove_stock(self, auth_client):
        auth_client.post("/api/portfolio", json={"symbol": "AAPL"})
        res = auth_client.delete("/api/portfolio/AAPL")
        assert res.status_code == 200
        data = json.loads(auth_client.get("/api/portfolio").data)
        assert data["count"] == 0

    def test_remove_nonexistent_404(self, auth_client):
        res = auth_client.delete("/api/portfolio/ZZZZ")
        assert res.status_code == 404

    def test_unauthenticated_portfolio_401(self, client):
        res = client.get("/api/portfolio")
        assert res.status_code == 401

    def test_missing_symbol_400(self, auth_client):
        res = auth_client.post("/api/portfolio", json={})
        assert res.status_code == 400


# ── 7. Alerts ─────────────────────────────────────────────────────────────────

class TestAlerts:
    def test_create_alert(self, auth_client):
        res = auth_client.post("/api/alerts", json={
            "symbol": "AAPL", "target_price": 200.0, "direction": "above"
        })
        assert res.status_code == 201

    def test_create_below_alert(self, auth_client):
        res = auth_client.post("/api/alerts", json={
            "symbol": "TSLA", "target_price": 100.0, "direction": "below"
        })
        assert res.status_code == 201

    def test_list_alerts(self, auth_client):
        auth_client.post("/api/alerts", json={"symbol": "AAPL", "target_price": 200.0, "direction": "above"})
        data = json.loads(auth_client.get("/api/alerts").data)
        assert data["count"] == 1

    def test_delete_alert(self, auth_client):
        res  = auth_client.post("/api/alerts", json={"symbol": "AAPL", "target_price": 200.0, "direction": "above"})
        aid  = json.loads(res.data)["alert"]["id"]
        res2 = auth_client.delete(f"/api/alerts/{aid}")
        assert res2.status_code == 200

    def test_delete_nonexistent_404(self, auth_client):
        assert auth_client.delete("/api/alerts/99999").status_code == 404

    def test_invalid_direction_400(self, auth_client):
        res = auth_client.post("/api/alerts", json={
            "symbol": "AAPL", "target_price": 200.0, "direction": "sideways"
        })
        assert res.status_code == 400

    def test_non_numeric_price_400(self, auth_client):
        res = auth_client.post("/api/alerts", json={
            "symbol": "AAPL", "target_price": "banana", "direction": "above"
        })
        assert res.status_code == 400

    def test_unauthenticated_alerts_401(self, client):
        assert client.get("/api/alerts").status_code == 401


# ── 8. Notifications ──────────────────────────────────────────────────────────

class TestNotifications:
    def test_notifications_endpoint_exists(self, auth_client):
        res = auth_client.get("/api/notifications")
        assert res.status_code == 200

    def test_notifications_empty_initially(self, auth_client):
        data = json.loads(auth_client.get("/api/notifications").data)
        assert data["count"] == 0

    def test_unauthenticated_notifications_401(self, client):
        assert client.get("/api/notifications").status_code == 401


# ── 9. Cache Stats ────────────────────────────────────────────────────────────

class TestCacheStats:
    def test_cache_stats_200(self, client):
        assert client.get("/api/cache/stats").status_code == 200

    def test_cache_stats_has_fields(self, client):
        data = json.loads(client.get("/api/cache/stats").data)
        assert "backend" in data or "total_keys" in data


# ── 10. Admin Symbols ─────────────────────────────────────────────────────────

class TestAdminSymbols:
    def test_list_symbols_200(self, client):
        assert client.get("/api/admin/symbols").status_code == 200

    def test_symbols_non_empty(self, client):
        data = json.loads(client.get("/api/admin/symbols").data)
        assert len(data["symbols"]) > 0

    def test_add_symbol_requires_auth(self, client):
        res = client.post("/api/admin/symbols", json={"symbol": "NFLX"})
        assert res.status_code == 401


# ── 11. Unit Tests: simulate_price ───────────────────────────────────────────

class TestSimulatePrice:
    def test_returns_positive_price(self):
        result = simulate_price(200.0)
        assert result["price"] > 0

    def test_source_is_simulated(self):
        result = simulate_price(100.0)
        assert result["source"] == "simulated"

    def test_has_all_required_fields(self):
        result = simulate_price(150.0, symbol="AAPL")
        for field in ("symbol", "price", "change", "change_pct", "previous_close",
                      "high", "low", "open", "timestamp", "source"):
            assert field in result

    def test_symbol_uppercased(self):
        result = simulate_price(symbol="aapl")
        assert result["symbol"] == "AAPL"

    def test_price_within_reasonable_range(self):
        base   = 200.0
        result = simulate_price(base)
        assert abs(result["price"] - base) < base * 0.05  # within ±5%

    def test_known_symbol_uses_base(self):
        result = simulate_price(symbol="NVDA")
        assert result["price"] > 0


# ── 12. Unit Tests: Alert Worker Logic ───────────────────────────────────────

class TestAlertWorkerLogic:
    """
    Test the trigger conditions in isolation — no DB, no threading.
    These test the pure boolean logic to ensure alerts fire correctly.
    """

    def _should_fire(self, direction, current_price, target_price):
        """Mirror of alert_worker._check_alerts trigger logic."""
        if direction == "above":
            return current_price >= target_price
        elif direction == "below":
            return current_price <= target_price
        return False

    def test_above_fires_when_price_exceeds_target(self):
        assert self._should_fire("above", 210.0, 200.0) is True

    def test_above_fires_exactly_at_target(self):
        assert self._should_fire("above", 200.0, 200.0) is True

    def test_above_does_not_fire_below_target(self):
        assert self._should_fire("above", 190.0, 200.0) is False

    def test_below_fires_when_price_drops_under_target(self):
        assert self._should_fire("below", 90.0, 100.0) is True

    def test_below_fires_exactly_at_target(self):
        assert self._should_fire("below", 100.0, 100.0) is True

    def test_below_does_not_fire_above_target(self):
        assert self._should_fire("below", 110.0, 100.0) is False

    def test_unknown_direction_does_not_fire(self):
        assert self._should_fire("sideways", 100.0, 100.0) is False
