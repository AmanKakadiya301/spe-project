"""
test_api.py
-----------
Unit and Integration Tests for the Stock Analysis REST API.
Run with: pytest app/tests/ -v --cov=app
"""

import pytest
import json
import sys
import os

# Make sure app/ is on the import path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from main import app
from models import db, User
from stock_data import simulate_price


# ── Fixture ───────────────────────────────────────────────────────────────────
@pytest.fixture
def client():
    """Flask test client — spins up a test instance of the app."""
    app.config["TESTING"] = True
    app.config["SECRET_KEY"] = "test-secret"
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["WTF_CSRF_ENABLED"] = False

    with app.app_context():
        db.create_all()

    with app.test_client() as c:
        yield c

    with app.app_context():
        db.drop_all()


# ── 1. Health Endpoint ────────────────────────────────────────────────────────
class TestHealthEndpoint:
    def test_returns_200(self, client):
        assert client.get("/health").status_code == 200

    def test_status_is_ok(self, client):
        data = json.loads(client.get("/health").data)
        assert data["status"] == "ok"

    def test_includes_service_name(self, client):
        data = json.loads(client.get("/health").data)
        assert data["service"] == "stock-app"

    def test_includes_timestamp(self, client):
        data = json.loads(client.get("/health").data)
        assert "timestamp" in data


# ── 2. Single Stock Endpoint ──────────────────────────────────────────────────
class TestStockEndpoint:
    def test_valid_symbol_returns_200(self, client):
        assert client.get("/api/stock/AAPL").status_code == 200

    def test_response_has_positive_price(self, client):
        data = json.loads(client.get("/api/stock/AAPL").data)
        assert data["price"] > 0

    def test_response_has_change_fields(self, client):
        data = json.loads(client.get("/api/stock/MSFT").data)
        assert "change" in data
        assert "change_pct" in data

    def test_lowercase_symbol_normalised(self, client):
        data = json.loads(client.get("/api/stock/aapl").data)
        assert data["symbol"] == "AAPL"

    def test_unknown_symbol_returns_404(self, client):
        assert client.get("/api/stock/ZZZZINVALID123").status_code == 404

    def test_source_field_present(self, client):
        data = json.loads(client.get("/api/stock/TSLA").data)
        assert data["source"] in ("live", "simulated")


# ── 3. Bulk Stocks Endpoint ───────────────────────────────────────────────────
class TestBulkStocksEndpoint:
    def test_returns_200(self, client):
        assert client.get("/api/stocks").status_code == 200

    def test_stocks_is_nonempty_list(self, client):
        data = json.loads(client.get("/api/stocks").data)
        assert isinstance(data["stocks"], list)
        assert len(data["stocks"]) > 0


# ── 4. History Endpoint ───────────────────────────────────────────────────────
class TestHistoryEndpoint:
    def test_returns_200(self, client):
        assert client.get("/api/stock/AAPL/history").status_code == 200

    def test_history_is_nonempty_list(self, client):
        data = json.loads(client.get("/api/stock/AAPL/history").data)
        assert isinstance(data["history"], list)
        assert len(data["history"]) > 0


# ── 5. Auth & Portfolio Endpoints ──────────────────────────────────────────────
class TestAuthEndpoints:
    def test_register_and_login(self, client):
        res = client.post("/register", json={"username": "testuser", "password": "password123"})
        assert res.status_code == 201

        res2 = client.post("/do-login", json={"username": "testuser", "password": "password123"})
        assert res2.status_code == 200
        
        # Test me endpoint
        res3 = client.get("/api/me")
        assert res3.status_code == 200
        assert json.loads(res3.data)["authenticated"] is True

        res4 = client.get("/logout")
        assert res4.status_code == 302
        
        res5 = client.get("/api/me")
        assert json.loads(res5.data)["authenticated"] is False


class TestPortfolioEndpoints:
    def test_add_to_portfolio(self, client):
        client.post("/register", json={"username": "tester", "password": "password123"})
        res = client.post("/api/portfolio", json={"symbol": "AAPL"})
        assert res.status_code == 201
        
        res2 = client.get("/api/portfolio")
        data = json.loads(res2.data)
        assert data["count"] == 1
        assert data["portfolio"][0]["symbol"] == "AAPL"


# ── 6. Unit Tests: Business Logic ─────────────────────────────────────────────
class TestSimulatePrice:
    def test_returns_new_price(self):
        result = simulate_price(200.0)
        assert result["price"] > 0
        assert result["source"] == "simulated"
