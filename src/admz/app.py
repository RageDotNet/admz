"""Flask application factory for the Agent DMZ v2."""

from __future__ import annotations

import os
import secrets

from flask import Flask, g, request, send_from_directory
from werkzeug.middleware.proxy_fix import ProxyFix

from admz.core.config import Config, load_config


def create_app(config: Config | None = None) -> Flask:
    """Create the single Flask application (REST API + admin console).

    ``config`` may be injected (tests); otherwise it is loaded from
    ``DMZ_CONFIG`` / ``./config.yaml`` at boot (startup validation crashes
    loudly on bad config per system-prd-v2.md).
    """
    if config is None:
        config = load_config(os.environ.get("DMZ_CONFIG"))

    app = Flask(
        "admz",
        template_folder="templates",
        static_folder="static",
    )
    # One trusted proxy hop so request.url_root matches the host the admin used.
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)  # type: ignore[method-assign]
    app.config["DMZ"] = config
    app.config["SECRET_KEY"] = config.secret_key
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["SESSION_COOKIE_SECURE"] = config.session_cookie_secure
    app.config["PERMANENT_SESSION_LIFETIME"] = 12 * 3600  # 12h rolling (#23)
    # rest-api-v2.md: JSON is UTF-8. Keep non-ASCII (emoji, etc.) unescaped so
    # responses match the request encoding instead of \uXXXX sequences.
    from flask.json.provider import DefaultJSONProvider

    if isinstance(app.json, DefaultJSONProvider):
        app.json.ensure_ascii = False

    # Blueprints are registered in later phases (api v2, admin console).
    from admz.core.db import init_db

    init_db(app, config)

    from admz.api_v2 import ApiError
    from admz.api_v2 import bp as api_v2_bp
    from admz.api_v2 import error as api_error

    app.register_blueprint(api_v2_bp)

    from admz import admin_console  # noqa: F401 — registers routes on bp
    from admz.admin import bp as admin_bp

    app.register_blueprint(admin_bp)

    @app.before_request
    def _csp_nonce() -> None:
        g.csp_nonce = secrets.token_urlsafe(16)

    @app.context_processor
    def _csp_nonce_ctx() -> dict[str, str]:
        return {"csp_nonce": getattr(g, "csp_nonce", "")}

    @app.after_request
    def _security_headers(response):
        nonce = getattr(g, "csp_nonce", "")
        response.headers["Content-Security-Policy"] = (
            "default-src 'none'; "
            f"script-src 'self' 'nonce-{nonce}'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self'; "
            "connect-src 'self'; "
            "form-action 'self'; "
            "base-uri 'self'; "
            "frame-ancestors 'none'"
        )
        return response

    @app.get("/favicon.ico")
    def favicon():
        """Browsers request /favicon.ico even when the HTML points at an SVG."""
        static_folder = app.static_folder
        if static_folder is None:
            raise RuntimeError("static folder is not configured")
        # Serve the SVG here too: browsers still GET /favicon.ico, and an
        # opaque ICO made the tab look like the old grey tile.
        response = send_from_directory(
            static_folder, "favicon.svg", mimetype="image/svg+xml"
        )
        response.headers["Cache-Control"] = "no-cache"
        return response

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
