import os

class Default:
  SLACK_API_TOKEN = os.environ.get('SLACK_API_TOKEN')
  SQLALCHEMY_DATABASE_URI = os.environ.get('SQLALCHEMY_DATABASE_URI')