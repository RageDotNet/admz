"""Flask application factory for the LLM DMZ v2."""

from __future__ import annotations

import os

from flask import Flask

from llmdmz.core.config import Config, load_config


def create_app(config: Config | None = None) -> Flask:
    """Create the single Flask application (REST API + admin console).

    ``config`` may be injected (tests); otherwise it is loaded from
    ``DMZ_CONFIG`` / ``./config.yaml`` at boot (startup validation crashes
    loudly on bad config per system-prd-v2.md).
    """
    if config is None:
        config = load_config(os.environ.get("DMZ_CONFIG"))

    app = Flask(
        "llmdmz",
        template_folder="templates",
        static_folder="static",
    )
    app.config["DMZ"] = config
    app.config["SECRET_KEY"] = config.secret_key
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["SESSION_COOKIE_SECURE"] = config.session_cookie_secure
    app.config["PERMANENT_SESSION_LIFETIME"] = 12 * 3600  # 12h rolling (#23)

    # Blueprints are registered in later phases (api v2, admin console).
    from llmdmz.core.db import init_db

    init_db(app, config)

    from llmdmz.api_v2 import ApiError
    from llmdmz.api_v2 import bp as api_v2_bp

    app.register_blueprint(api_v2_bp)

    from llmdmz.api_v2 import error as api_error

    @app.errorhandler(ApiError)
    def _api_error(exc: ApiError):
        return api_error(exc.code, exc.message, exc.status, exc.detail)

    return app


def main() -> None:
    """Console-script entry point (dev server; Docker uses gunicorn)."""
    app = create_app()
    app.run(
        host="0.0.0.0",
        port=app.config["DMZ"].app_port,
        debug=app.config["DMZ"].flask_debug,
    )


def create_app_standalone() -> Flask:
    """Gunicorn entry point (deploy/entrypoint.sh)."""
    return create_app()
