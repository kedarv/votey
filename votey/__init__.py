"""Votey!"""

import os
from typing import Any
from typing import Dict
from typing import Optional

from flask import Flask

from . import slack
from .exts import db
from .utils import rewrite_pg_url

DEFAULT_URL: str = "postgresql://localhost:5342"


def create_app(config: Optional[Dict[str, Any]] = None) -> Flask:
    # create and configure the app
    app = Flask(__name__)
    app.config.update(
        # rewriting to explicitly specify psycopg2 driver
        SQLALCHEMY_DATABASE_URI=rewrite_pg_url(
            os.getenv("DATABASE_URL", default=DEFAULT_URL)
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
