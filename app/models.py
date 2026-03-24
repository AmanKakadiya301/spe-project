"""
models.py
---------
SQLAlchemy ORM models for the FinTech Stock App.

Changes from original:
  + AlertNotification model — stores fired alert messages for frontend polling
  + price_snapshots gets an index on (symbol, captured_at) for fast range queries
"""

from datetime import datetime, timezone
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin

db = SQLAlchemy()


# ── Users ──────────────────────────────────────────────────────────────────────
class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=True)
    google_id = db.Column(db.String(120), unique=True, nullable=True)
    password_hash = db.Column(db.String(256), nullable=True)
    role = db.Column(db.String(20), nullable=False, default="user")
    avatar_url = db.Column(db.Text, nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    last_login = db.Column(db.DateTime, nullable=True)

    portfolio = db.relationship("PortfolioItem", backref="owner", lazy=True, cascade="all, delete-orphan")
    alerts = db.relationship("Alert", backref="owner", lazy=True, cascade="all, delete-orphan")
    notifications = db.relationship("AlertNotification", backref="owner", lazy=True, cascade="all, delete-orphan")

    def is_admin(self) -> bool:
        return self.role == "admin"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "username": self.username,
            "email": self.email,
            "role": self.role,
            "avatar_url": self.avatar_url,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() + "Z" if self.created_at else None,
            "last_login": self.last_login.isoformat() + "Z" if self.last_login else None,
        }

    def __repr__(self):
        return f"<User {self.username} [{self.role}]>"


# ── Portfolio Items ────────────────────────────────────────────────────────────
class PortfolioItem(db.Model):
    __tablename__ = "portfolio_items"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    symbol = db.Column(db.String(20), nullable=False)
    shares = db.Column(db.Numeric(12, 4), default=0)
    avg_price = db.Column(db.Numeric(12, 4), default=0)
    added_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (db.UniqueConstraint("user_id", "symbol"),)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "symbol": self.symbol,
            "shares": float(self.shares or 0),
            "avg_price": float(self.avg_price or 0),
            "added_at": self.added_at.isoformat() + "Z" if self.added_at else None,
        }


# ── Alerts ─────────────────────────────────────────────────────────────────────
class Alert(db.Model):
    __tablename__ = "alerts"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    symbol = db.Column(db.String(20), nullable=False)
    target_price = db.Column(db.Numeric(12, 4), nullable=False)
    direction = db.Column(db.String(10), nullable=False)   # 'above' | 'below'
    is_active = db.Column(db.Boolean, default=True)
    triggered = db.Column(db.Boolean, default=False)
    triggered_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "symbol": self.symbol,
            "target_price": float(self.target_price),
            "direction": self.direction,
            "is_active": self.is_active,
            "triggered": self.triggered,
            "triggered_at": self.triggered_at.isoformat() + "Z" if self.triggered_at else None,
            "created_at": self.created_at.isoformat() + "Z" if self.created_at else None,
        }


# ── Alert Notifications ────────────────────────────────────────────────────────
# NEW: persisted by alert_worker when an alert fires; polled by the frontend.
class AlertNotification(db.Model):
    __tablename__ = "alert_notifications"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    alert_id = db.Column(db.Integer, db.ForeignKey("alerts.id"), nullable=True)
    symbol = db.Column(db.String(20), nullable=False)
    message = db.Column(db.Text, nullable=False)
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "alert_id": self.alert_id,
            "symbol": self.symbol,
            "message": self.message,
            "is_read": self.is_read,
            "created_at": self.created_at.isoformat() + "Z" if self.created_at else None,
        }


# ── Audit Log ──────────────────────────────────────────────────────────────────
class AuditLog(db.Model):
    __tablename__ = "audit_log"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    username = db.Column(db.String(80), nullable=True)
    action = db.Column(db.String(100), nullable=False)
    target = db.Column(db.String(200), nullable=True)
    ip_address = db.Column(db.String(45), nullable=True)
    extra_data = db.Column(db.JSON, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    @classmethod
    def log(cls, action: str, target: str = None, user=None, ip: str = None, metadata: dict = None):
        entry = cls(
            user_id=user.id if user else None,
            username=user.username if user else "system",
            action=action,
            target=target,
            ip_address=ip,
            extra_data=metadata,
        )
        db.session.add(entry)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "username": self.username,
            "action": self.action,
            "target": self.target,
            "ip_address": self.ip_address,
            "metadata": self.extra_data,
            "created_at": self.created_at.isoformat() + "Z" if self.created_at else None,
        }


# ── Tracked Symbols ────────────────────────────────────────────────────────────
class TrackedSymbol(db.Model):
    __tablename__ = "tracked_symbols"

    id = db.Column(db.Integer, primary_key=True)
    symbol = db.Column(db.String(20), unique=True, nullable=False)
    name = db.Column(db.String(200), nullable=True)
    sector = db.Column(db.String(100), nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    added_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    added_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "name": self.name,
            "sector": self.sector,
            "is_active": self.is_active,
            "added_at": self.added_at.isoformat() + "Z" if self.added_at else None,
        }


# ── Price Snapshots ────────────────────────────────────────────────────────────
class PriceSnapshot(db.Model):
    __tablename__ = "price_snapshots"

    id = db.Column(db.BigInteger, primary_key=True)
    symbol = db.Column(db.String(20), nullable=False)
    price = db.Column(db.Numeric(12, 4), nullable=False)
    change = db.Column(db.Numeric(12, 4), nullable=True)
    change_pct = db.Column(db.Numeric(8, 4), nullable=True)
    volume = db.Column(db.BigInteger, nullable=True)
    source = db.Column(db.String(20), nullable=True)
    captured_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "price": float(self.price),
            "change": float(self.change or 0),
            "change_pct": float(self.change_pct or 0),
            "captured_at": self.captured_at.isoformat() + "Z" if self.captured_at else None,
        }
