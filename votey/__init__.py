import os
from typing import Any
from typing import Dict
from typing import Optional

from flask import Flask
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


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
    db.init_app(app)

    # slack interaction
    from . import slack

    app.register_blueprint(slack.bp)

    return app
