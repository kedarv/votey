from typing import Any

from sqlalchemy.dialects.postgresql import UUID

from . import db

base: Any = db.Model

class Poll(base):
  id = db.Column(db.Integer, primary_key=True)
  identifier = db.Column(UUID(as_uuid=True), unique=True, nullable=False)
  question = db.Column(db.Text, nullable=False)
  options = db.relationship('Option', backref='poll', lazy=True)
  votes = db.relationship('Vote', backref='poll', lazy=True)

  def __init__(self, identifier, question):
    self.identifier = identifier
    self.question = question

  def poll_identifier(self):
    return self.identifier.__str__()

class Option(base):
  id = db.Column(db.Integer, primary_key=True)
  poll_id = db.Column(db.Integer, db.ForeignKey('poll.id'), nullable=False)
  option_text = db.Column(db.Text, nullable=False)
  votes = db.relationship('Vote', backref='option', lazy=True)

  def __init__(self, poll_id, option_text):
    self.poll_id = poll_id
    self.option_text = option_text

class Vote(base):
  id = db.Column(db.Integer, primary_key=True)
  poll_id = db.Column(db.Integer, db.ForeignKey('poll.id'), nullable=False)
  option_id = db.Column(db.Integer, db.ForeignKey('option.id'), nullable=False)
  user = db.Column(db.Text, nullable=False)

  def __init__(self, poll_id, option_id, user):
    self.poll_id = poll_id
    self.option_id = option_id
    self.user = user
