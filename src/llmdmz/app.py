"""Flask application factory for the LLM DMZ v2."""

from __future__ import annotations

import os

from flask import Flask, request

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
    from llmdmz.api_v2 import error as api_error

    app.register_blueprint(api_v2_bp)

    from llmdmz import admin_console  # noqa: F401 — registers routes on bp
    from llmdmz.admin import bp as admin_bp

    app.register_blueprint(admin_bp)

    @app.errorhandler(ApiError)
    def _api_error(exc: ApiError):
        return api_error(exc.code, exc.message, exc.status, exc.detail)

    from werkzeug.exceptions import HTTPException

    @app.errorhandler(HTTPException)
    def _http_error(exc: HTTPException):
        """Every /v2 error uses the rest-api-v2.md envelope (T2.9)."""
        if request.path.startswith("/v2/"):
            code_by_status = {
                400: "malformed_json",
                401: "unauthorized",
                403: "forbidden",
                404: "not_found",
                405: "not_found",
                409: "forbidden",
                422: "request_schema_invalid",
                429: "forbidden",
                503: "arbiter_unavailable",
            }
            assert exc.code is not None
            code = code_by_status.get(exc.code)
            if code is None:
                code = "not_found" if exc.code < 500 else "internal_error"
            return api_error(code, exc.description or exc.name, exc.code)
        return exc

    @app.errorhandler(Exception)
    def _unhandled(exc: Exception):
        """Fail closed with the envelope on /v2; logged at ERROR (#6)."""
        if request.path.startswith("/v2/"):
            app.logger.exception("internal_error")
            return api_error("internal_error", "Internal server error.", 500)
        raise exc

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
