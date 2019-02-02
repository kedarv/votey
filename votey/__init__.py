import os
from socket import gethostname

from flask import Flask


def create_app(config=None):
  # create and configure the app
  app = Flask(__name__, instance_relative_config=True)
  app.config.from_mapping(
    SECRET_KEY='dev',
    DATABASE=os.path.join(app.instance_path, 'votey.sqlite'),
  )
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

  # paasta healthcheck
  @app.route('/status')
  def dummy() -> str:
    hostname = app.config.get('SERVER_NAME') or gethostname()
    return f'OK - {hostname}'

  # slack interaction
  from . import slack
  app.register_blueprint(slack.bp)

  return app
