"""
models.py
REPLACE existing app/models.py
PostgreSQL + SQLite compatible. All new tables added safely.
"""
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin

db = SQLAlchemy()


class User(UserMixin, db.Model):
    __tablename__ = "users"
    id            = db.Column(db.Integer,     primary_key=True)
    username      = db.Column(db.String(80),  unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=True)
    email         = db.Column(db.String(120), unique=True, nullable=True)
    google_id     = db.Column(db.String(120), unique=True, nullable=True)
    role          = db.Column(db.String(20),  nullable=False, default="user")
    avatar_url    = db.Column(db.Text,        nullable=True)
    is_active     = db.Column(db.Boolean,     nullable=False, default=True)
    last_login    = db.Column(db.DateTime,    nullable=True)
    created_at    = db.Column(db.DateTime,    default=datetime.utcnow)
    portfolio     = db.relationship("PortfolioItem", backref="owner", lazy=True, cascade="all, delete-orphan")
    alerts        = db.relationship("Alert",         backref="owner", lazy=True, cascade="all, delete-orphan")

    def is_admin(self):
        return self.role == "admin"

    def to_dict(self):
        return {
            "id": self.id, "username": self.username, "email": self.email,
            "role": self.role, "avatar_url": self.avatar_url, "is_active": self.is_active,
            "created_at": self.created_at.isoformat() + "Z" if self.created_at else None,
            "last_login":  self.last_login.isoformat()  + "Z" if self.last_login  else None,
        }

    def __repr__(self):
        return f"<User {self.username} [{self.role}]>"


class PortfolioItem(db.Model):
    __tablename__ = "portfolio_items"
    id        = db.Column(db.Integer,       primary_key=True)
    user_id   = db.Column(db.Integer,       db.ForeignKey("users.id"), nullable=False)
    symbol    = db.Column(db.String(20),    nullable=False)
    shares    = db.Column(db.Numeric(12, 4), default=0)
    avg_price = db.Column(db.Numeric(12, 4), default=0)
    added_at  = db.Column(db.DateTime,      default=datetime.utcnow)
    __table_args__ = (db.UniqueConstraint("user_id", "symbol", name="uq_user_symbol"),)

    def to_dict(self):
        return {
            "id": self.id, "symbol": self.symbol,
            "shares": float(self.shares or 0), "avg_price": float(self.avg_price or 0),
            "added_at": self.added_at.isoformat() + "Z" if self.added_at else None,
        }


class Alert(db.Model):
    __tablename__ = "alerts"
    id           = db.Column(db.Integer,        primary_key=True)
    user_id      = db.Column(db.Integer,        db.ForeignKey("users.id"), nullable=False)
    symbol       = db.Column(db.String(20),     nullable=False)
    target_price = db.Column(db.Numeric(12, 4), nullable=False)
    direction    = db.Column(db.String(10),     nullable=False)
    is_active    = db.Column(db.Boolean,        default=True)
    triggered    = db.Column(db.Boolean,        default=False)
    triggered_at = db.Column(db.DateTime,       nullable=True)
    created_at   = db.Column(db.DateTime,       default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id, "symbol": self.symbol,
            "target_price": float(self.target_price), "direction": self.direction,
            "is_active": self.is_active, "triggered": self.triggered,
            "triggered_at": self.triggered_at.isoformat() + "Z" if self.triggered_at else None,
            "created_at":   self.created_at.isoformat()   + "Z" if self.created_at   else None,
        }


class AuditLog(db.Model):
    __tablename__ = "audit_log"
    id         = db.Column(db.Integer,     primary_key=True)
    user_id    = db.Column(db.Integer,     db.ForeignKey("users.id"), nullable=True)
    username   = db.Column(db.String(80),  nullable=True)
    action     = db.Column(db.String(100), nullable=False)
    target     = db.Column(db.String(200), nullable=True)
    ip_address = db.Column(db.String(45),  nullable=True)
    meta       = db.Column(db.JSON,        nullable=True)
    created_at = db.Column(db.DateTime,    default=datetime.utcnow)

    @classmethod
    def log(cls, action, target=None, user=None, ip=None, meta=None):
        db.session.add(cls(
            user_id=user.id if user else None,
            username=user.username if user else "system",
            action=action, target=target, ip_address=ip, meta=meta,
        ))

    def to_dict(self):
        return {
            "id": self.id, "username": self.username, "action": self.action,
            "target": self.target, "ip_address": self.ip_address, "meta": self.meta,
            "created_at": self.created_at.isoformat() + "Z" if self.created_at else None,
        }


class TrackedSymbol(db.Model):
    __tablename__ = "tracked_symbols"
    id        = db.Column(db.Integer,     primary_key=True)
    symbol    = db.Column(db.String(20),  unique=True, nullable=False)
    name      = db.Column(db.String(200), nullable=True)
    sector    = db.Column(db.String(100), nullable=True)
    is_active = db.Column(db.Boolean,    default=True)
    added_by  = db.Column(db.Integer,    db.ForeignKey("users.id"), nullable=True)
    added_at  = db.Column(db.DateTime,   default=datetime.utcnow)

    def to_dict(self):
        return {
            "symbol": self.symbol, "name": self.name, "sector": self.sector,
            "is_active": self.is_active,
            "added_at": self.added_at.isoformat() + "Z" if self.added_at else None,
        }


class PriceSnapshot(db.Model):
    __tablename__ = "price_snapshots"
    id          = db.Column(db.BigInteger,    primary_key=True)
    symbol      = db.Column(db.String(20),    nullable=False)
    price       = db.Column(db.Numeric(12, 4), nullable=False)
    change      = db.Column(db.Numeric(12, 4), nullable=True)
    change_pct  = db.Column(db.Numeric(8, 4),  nullable=True)
    source      = db.Column(db.String(20),    nullable=True)
    captured_at = db.Column(db.DateTime,      default=datetime.utcnow)

    def to_dict(self):
        return {
            "symbol": self.symbol, "price": float(self.price),
            "change": float(self.change or 0), "change_pct": float(self.change_pct or 0),
            "captured_at": self.captured_at.isoformat() + "Z" if self.captured_at else None,
        }


DEFAULT_SYMBOLS = [
    ("AAPL", "Apple Inc.",             "Technology"),
    ("GOOGL", "Alphabet Inc.",         "Technology"),
    ("MSFT",  "Microsoft Corp.",       "Technology"),
    ("AMZN",  "Amazon.com Inc.",       "Consumer Cyclical"),
    ("TSLA",  "Tesla Inc.",            "Consumer Cyclical"),
    ("META",  "Meta Platforms Inc.",   "Technology"),
    ("NVDA",  "NVIDIA Corp.",          "Technology"),
    ("AMD",   "Advanced Micro Devices","Technology"),
    ("INTC",  "Intel Corp.",           "Technology"),
    ("NFLX",  "Netflix Inc.",          "Communication"),
    ("IBM",   "IBM Corp.",             "Technology"),
    ("ORCL",  "Oracle Corp.",          "Technology"),
]


def seed_defaults():
    """Call from main.py after db.create_all(). Seeds default symbols."""
    if TrackedSymbol.query.count() == 0:
        for symbol, name, sector in DEFAULT_SYMBOLS:
            db.session.add(TrackedSymbol(symbol=symbol, name=name, sector=sector))
        db.session.commit()
