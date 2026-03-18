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
from stock_data import simulate_price


# ── Fixture ───────────────────────────────────────────────────────────────────
@pytest.fixture
def client():
    """Flask test client — spins up a test instance of the app."""
    app.config["TESTING"]   = True
    app.config["SECRET_KEY"] = "test-secret"
    with app.test_client() as c:
        yield c


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
        assert client.get("/api/stock/ZZZZINVALID").status_code == 404

    def test_source_field_present(self, client):
        data = json.loads(client.get("/api/stock/TSLA").data)
        assert data["source"] in ("live", "simulated")

    def test_response_has_timestamp(self, client):
        data = json.loads(client.get("/api/stock/NVDA").data)
        assert "timestamp" in data


# ── 3. Bulk Stocks Endpoint ───────────────────────────────────────────────────
class TestBulkStocksEndpoint:
    def test_returns_200(self, client):
        assert client.get("/api/stocks").status_code == 200

    def test_stocks_is_nonempty_list(self, client):
        data = json.loads(client.get("/api/stocks").data)
        assert isinstance(data["stocks"], list)
        assert len(data["stocks"]) > 0

    def test_count_matches_list_length(self, client):
        data = json.loads(client.get("/api/stocks").data)
        assert data["count"] == len(data["stocks"])

    def test_includes_timestamp(self, client):
        data = json.loads(client.get("/api/stocks").data)
        assert "timestamp" in data


# ── 4. History Endpoint ───────────────────────────────────────────────────────
class TestHistoryEndpoint:
    def test_returns_200(self, client):
        assert client.get("/api/stock/AAPL/history").status_code == 200

    def test_history_is_nonempty_list(self, client):
        data = json.loads(client.get("/api/stock/AAPL/history").data)
        assert isinstance(data["history"], list)
        assert len(data["history"]) > 0

    def test_history_item_has_required_fields(self, client):
        data = json.loads(client.get("/api/stock/AAPL/history").data)
        item = data["history"][0]
        for field in ("date", "open", "close", "high", "low", "volume"):
            assert field in item, f"Missing field: {field}"

    def test_custom_days_respected(self, client):
        data = json.loads(client.get("/api/stock/AAPL/history?days=3").data)
        assert data["days"] == 3


# ── 5. Unit Tests: Business Logic ─────────────────────────────────────────────
class TestSimulatePrice:
    def test_returns_new_price(self):
        result = simulate_price(200.0)
        assert "price" in result
        assert result["price"] > 0

    def test_has_change_fields(self):
        result = simulate_price(150.0)
        assert "change" in result
        assert "change_pct" in result

    def test_change_pct_is_within_bounds(self):
        for _ in range(50):            # run 50 times to cover randomness
            result = simulate_price(100.0)
            assert -10 < result["change_pct"] < 10

    def test_source_is_simulated(self):
        assert simulate_price(100.0)["source"] == "simulated"
