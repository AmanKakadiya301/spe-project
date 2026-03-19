"""
alert_worker.py
CREATE at app/alert_worker.py
Background thread: checks price alerts every 30s, sends email on trigger.

Add to main.py:
    from alert_worker import start_alert_worker
    start_alert_worker(app)

.env vars needed:
    SMTP_USER=kakadiyaaman2004@gmail.com
    SMTP_PASS=your-16-char-gmail-app-password
"""
import os
import time
import logging
import smtplib
import threading
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)

SMTP_HOST      = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT      = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER      = os.getenv("SMTP_USER", "")
SMTP_PASS      = os.getenv("SMTP_PASS", "")
ALERT_FROM     = os.getenv("ALERT_FROM", SMTP_USER)
CHECK_INTERVAL = 30


def _send_email(to: str, subject: str, html: str) -> bool:
    if not SMTP_USER or not SMTP_PASS:
        logger.warning("SMTP not configured — email skipped")
        return False
    try:
        msg             = MIMEMultipart("alternative")
        msg["Subject"]  = subject
        msg["From"]     = f"AutoDevOps FinTech <{ALERT_FROM}>"
        msg["To"]       = to
        msg.attach(MIMEText(html, "html"))
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as s:
            s.ehlo(); s.starttls(); s.login(SMTP_USER, SMTP_PASS)
            s.sendmail(ALERT_FROM, to, msg.as_string())
        logger.info(f"Alert email sent → {to}")
        return True
    except Exception as exc:
        logger.error(f"Email failed to {to}: {exc}")
        return False


def _body(symbol, direction, target, actual):
    color = "#16a34a" if direction == "above" else "#dc2626"
    arrow = "▲" if direction == "above" else "▼"
    return f"""
<div style="font-family:sans-serif;max-width:480px;margin:auto;padding:24px;
            border:1px solid #e5e7eb;border-radius:12px;">
  <h2 style="margin:0 0 16px;color:#111">{arrow} Price Alert: {symbol}</h2>
  <p style="color:#6b7280;">Your alert triggered at {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}</p>
  <table style="width:100%;font-size:14px;margin-top:16px;">
    <tr><td style="color:#6b7280;padding:6px 0">Condition</td>
        <td style="color:{color};font-weight:600">Price {direction} ${target:.2f}</td></tr>
    <tr><td style="color:#6b7280;padding:6px 0">Current price</td>
        <td style="color:{color};font-size:1.4rem;font-weight:700">${actual:.2f}</td></tr>
  </table>
</div>"""


def start_alert_worker(app):
    def _run():
        time.sleep(45)
        logger.info("Alert worker started")
        while True:
            try:
                _check(app)
            except Exception as exc:
                logger.error(f"Alert worker error: {exc}")
            time.sleep(CHECK_INTERVAL)

    threading.Thread(target=_run, daemon=True, name="alert-worker").start()


def _check(app):
    from models import db, Alert, User
    from stock_data import get_stock_price

    with app.app_context():
        alerts = Alert.query.filter_by(is_active=True, triggered=False).all()
        if not alerts:
            return

        prices = {}
        for sym in {a.symbol for a in alerts}:
            r = get_stock_price(sym)
            if "error" not in r:
                prices[sym] = r["price"]

        fired = 0
        for alert in alerts:
            cur = prices.get(alert.symbol)
            if cur is None:
                continue
            triggered = (
                (alert.direction == "above" and cur >= float(alert.target_price)) or
                (alert.direction == "below" and cur <= float(alert.target_price))
            )
            if triggered:
                alert.triggered    = True
                alert.is_active    = False
                alert.triggered_at = datetime.utcnow()
                user = db.session.get(User, alert.user_id)
                if user and user.email:
                    _send_email(
                        user.email,
                        f"[FinTech Alert] {alert.symbol} {alert.direction} ${alert.target_price:.2f}",
                        _body(alert.symbol, alert.direction, float(alert.target_price), cur),
                    )
                fired += 1

        if fired:
            db.session.commit()
            logger.info(f"Alert worker: {fired} alert(s) triggered")
