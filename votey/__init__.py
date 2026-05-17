"""Votey!"""

import os
from pathlib import Path
from typing import Any

from flask import Flask
from werkzeug.middleware.proxy_fix import ProxyFix

from . import slack
from .exts import db
from .utils import normalize_database_url

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DATA_DIR = _PROJECT_ROOT / "data"
DEFAULT_DATABASE_URL: str = f"sqlite:///{_DATA_DIR / 'votey.db'}"


def create_app(config: dict[str, Any] | None = None) -> Flask:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    app = Flask(__name__)
    # Trust X-Forwarded-* headers from the proxy in front of us (Fly.io in
    # prod, ngrok in dev) so request.scheme / request.host reflect the public
    # URL the client actually hit.
    app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)  # type: ignore[method-assign]
    app.config.update(
        SQLALCHEMY_DATABASE_URI=normalize_database_url(
            os.getenv("DATABASE_URL") or DEFAULT_DATABASE_URL
        ),
        CLIENT_ID=os.getenv("CLIENT_ID"),
        CLIENT_SECRET=os.getenv("CLIENT_SECRET"),
        SIGNING_SECRET=os.getenv("SIGNING_SECRET"),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )
    if config:
        app.config.update(config)

    register_extensions(app)

    return app


def register_extensions(app: Flask) -> None:
    db.init_app(app)
    app.register_blueprint(slack.bp)
