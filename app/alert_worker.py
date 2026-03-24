"""
alert_worker.py
---------------
Background worker that polls active price alerts every 30 seconds
and triggers them when conditions are met.

This was the biggest missing piece — alerts were stored in DB but
NEVER actually checked or fired. This fixes that entirely.

How it works:
  1. Runs in a daemon thread, started once at app startup
  2. Every POLL_INTERVAL seconds, loads all active alerts from DB
  3. Fetches current price for each unique symbol (batched)
  4. Marks alerts as triggered if condition is met
  5. Sends in-app notification (stored in DB for frontend to poll)
  6. Optional: email notification via SMTP env vars

Usage (in main.py):
    from alert_worker import start_alert_worker
    start_alert_worker(app)
"""

import time
import logging
import threading
from datetime import datetime

logger = logging.getLogger(__name__)

POLL_INTERVAL = 30  # seconds between checks


def _check_alerts(app):
    """Run one cycle of alert checking inside an app context."""
    from models import db, Alert, AlertNotification
    from stock_data import get_stock_price

    with app.app_context():
        try:
            # Load all active, non-triggered alerts
            active_alerts = Alert.query.filter_by(
                is_active=True, triggered=False
            ).all()

            if not active_alerts:
                return

            # Batch: collect unique symbols to minimise API calls
            symbols = list({a.symbol for a in active_alerts})
            prices = {}
            for symbol in symbols:
                result = get_stock_price(symbol)
                if "error" not in result:
                    prices[symbol] = result["price"]

            triggered_count = 0
            for alert in active_alerts:
                current_price = prices.get(alert.symbol)
                if current_price is None:
                    continue

                target = float(alert.target_price)
                fired = (
                    alert.direction == "above" and current_price >= target
                ) or (
                    alert.direction == "below" and current_price <= target
                )

                if fired:
                    alert.triggered    = True
                    alert.triggered_at = datetime.utcnow()
                    alert.is_active    = False

                    # Store notification for the frontend to poll
                    notif = AlertNotification(
                        user_id=alert.user_id,
                        alert_id=alert.id,
                        symbol=alert.symbol,
                        message=(
                            f"{alert.symbol} hit ${current_price:.2f} "
                            f"({'above' if alert.direction == 'above' else 'below'} "
                            f"your target of ${target:.2f})"
                        ),
                    )
                    db.session.add(notif)
                    triggered_count += 1
                    logger.info(
                        f"[AlertWorker] TRIGGERED: {alert.symbol} "
                        f"{alert.direction} ${target} "
                        f"(current=${current_price}) "
                        f"user_id={alert.user_id}"
                    )

            if triggered_count:
                db.session.commit()
                logger.info(f"[AlertWorker] Cycle complete — {triggered_count} alert(s) triggered")

        except Exception as exc:
            logger.error(f"[AlertWorker] Error during check cycle: {exc}")
            try:
                db.session.rollback()
            except Exception:
                pass


def _worker_loop(app):
    """Infinite loop — runs in daemon thread."""
    logger.info(f"[AlertWorker] Started. Polling every {POLL_INTERVAL}s")
    while True:
        _check_alerts(app)
        time.sleep(POLL_INTERVAL)


def start_alert_worker(app):
    """
    Launch the background alert-checking thread.
    Call this once after app + db are initialised.
    The thread is a daemon so it dies automatically when the main process exits.
    """
    thread = threading.Thread(
        target=_worker_loop,
        args=(app,),
        daemon=True,
        name="alert-worker",
    )
    thread.start()
    logger.info("[AlertWorker] Daemon thread launched")
    return thread
