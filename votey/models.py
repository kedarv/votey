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

class Option(base):
  id = db.Column(db.Integer, primary_key=True)
  poll_id = db.Column(db.Integer, db.ForeignKey('poll.id'), nullable=False)
  option_text = db.Column(db.Text, nullable=False)
  votes = db.relationship('Vote', backref='option', lazy=True)

class Vote(base):
  id = db.Column(db.Integer, primary_key=True)
  poll_id = db.Column(db.Integer, db.ForeignKey('poll.id'), nullable=False)
  option_id = db.Column(db.Integer, db.ForeignKey('option.id'), nullable=False)
  user = db.Column(db.Text, nullable=False)
