import os
from socket import gethostname
from typing import Any
from typing import Dict
from typing import Optional

from flask import Flask
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

def create_app(config: Optional[Dict[str, Any]] = None) -> Flask:
    # create and configure the app
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(SECRET_KEY='dev')
    app.config.from_object('votey.config.Default')

    if config is None:
        # load the instance config, if it exists, when not testing
        app.config.from_envvar('VOTEY_CONFIG', silent=True)
    else:
        # load the test config if passed in
        app.config.from_mapping(config)

    # ensure the instance folder exists
    try:
        os.makedirs(app.instance_path)
    except OSError:
        pass

    db.init_app(app)

    # paasta healthcheck
    @app.route('/status')  # type: ignore
    def dummy() -> str:
        hostname = app.config.get('SERVER_NAME') or gethostname()
        return f'OK - {hostname}'

    # slack interaction
    from . import slack
    app.register_blueprint(slack.bp)

    return app
