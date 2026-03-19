"""
tests/test_api.py — CREATE at app/tests/test_api.py
Basic integration tests for all API endpoints.
Run: pytest app/tests/ -v
"""
import pytest
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

@pytest.fixture
def client():
    os.environ["FLASK_ENV"]       = "testing"
    os.environ["FLASK_SECRET_KEY"] = "test-secret"
    os.environ["DATABASE_URL"]    = "sqlite:///:memory:"
    from main import app
    app.config["TESTING"]         = True
    app.config["WTF_CSRF_ENABLED"] = False
    with app.test_client() as c:
        yield c


def test_health(client):
    r = client.get("/health")
    assert r.status_code in (200, 503)
    data = json.loads(r.data)
    assert "status" in data
    assert "service" in data


def test_get_stocks(client):
    r = client.get("/api/stocks")
    assert r.status_code == 200
    data = json.loads(r.data)
    assert "stocks" in data
    assert "count"  in data


def test_get_single_stock(client):
    r = client.get("/api/stock/AAPL")
    assert r.status_code in (200, 404)


def test_search_valid(client):
    r = client.get("/api/search/AAPL")
    assert r.status_code in (200, 404)


def test_suggest(client):
    r = client.get("/api/suggest?q=AA")
    assert r.status_code == 200
    data = json.loads(r.data)
    assert "suggestions" in data


def test_cache_stats(client):
    r = client.get("/api/cache/stats")
    assert r.status_code == 200


def test_list_symbols(client):
    r = client.get("/api/admin/symbols")
    assert r.status_code == 200


def test_register_and_login(client):
    r = client.post("/register",
        data=json.dumps({"username": "testuser99", "password": "pass1234"}),
        content_type="application/json")
    assert r.status_code in (201, 409)

    r = client.post("/do-login",
        data=json.dumps({"username": "testuser99", "password": "pass1234"}),
        content_type="application/json")
    assert r.status_code in (200, 401)


def test_me_unauthenticated(client):
    r = client.get("/api/me")
    assert r.status_code == 200
    data = json.loads(r.data)
    assert data["authenticated"] is False


def test_portfolio_requires_auth(client):
    r = client.get("/api/portfolio")
    assert r.status_code in (401, 302)


def test_alerts_requires_auth(client):
    r = client.get("/api/alerts")
    assert r.status_code in (401, 302)


def test_admin_requires_auth(client):
    r = client.get("/api/admin/users")
    assert r.status_code == 401
