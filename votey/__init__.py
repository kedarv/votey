import os
from typing import Any
from typing import Dict
from typing import Optional

from flask import Flask

from . import slack
from .exts import db


def create_app(config: Optional[Dict[str, Any]] = None) -> Flask:
    # create and configure the app
    app = Flask(__name__)
    app.config.update(
        SQLALCHEMY_DATABASE_URI=os.getenv("DATABASE_URL"),
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
