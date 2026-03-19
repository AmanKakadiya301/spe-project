"""
auth/rate_limit.py
CREATE at auth/rate_limit.py
Flask-Limiter setup. Import limiter and use as decorator on routes.

Add to main.py:
    from auth.rate_limit import limiter
    limiter.init_app(app)

Then protect routes:
    @app.route("/do-login", methods=["POST"])
    @limiter.limit("10 per minute")
    def do_login(): ...
"""
import os
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

limiter = Limiter(
    key_func       = get_remote_address,
    default_limits = ["200 per minute", "2000 per hour"],
    storage_uri    = os.getenv("REDIS_URL", "memory://"),
    strategy       = "fixed-window",
    headers_enabled= True,
)
