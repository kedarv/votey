from typing import List

from sqlalchemy.dialects.postgresql import UUID

from . import db

class Workspace(db.Model):  # type: ignore
    id: int = db.Column(db.Integer, primary_key=True)
    team_id: str = db.Column(db.Text, nullable=False)
    name: str = db.Column(db.Text, nullable=False)
    token: str = db.Column(db.Text, nullable=False)

    def __init__(self, team_id: str, name: str, token: str) -> None:
        self.team_id = team_id
        self.name = name
        self.token = token

class Vote(db.Model):  # type: ignore
    id: int = db.Column(db.Integer, primary_key=True)
    poll_id: int = db.Column(db.Integer, db.ForeignKey('poll.id'), nullable=False)
    option_id: int = db.Column(db.Integer, db.ForeignKey('option.id'), nullable=False)
    user: str = db.Column(db.Text, nullable=False)

    def __init__(self, poll_id: int, option_id: int, user: str):
        self.poll_id = poll_id
        self.option_id = option_id
        self.user = user

class Option(db.Model):  # type: ignore
    id: int = db.Column(db.Integer, primary_key=True)
    poll_id: int = db.Column(db.Integer, db.ForeignKey('poll.id'), nullable=False)
    option_text: str = db.Column(db.Text, nullable=False)
    votes: List[Vote] = db.relationship('Vote', backref='option', lazy=True)

    def __init__(self, poll_id: int, option_text: str):
        self.poll_id = poll_id
        self.option_text = option_text

class Poll(db.Model):  # type: ignore
    id: int = db.Column(db.Integer, primary_key=True)
    identifier: UUID = db.Column(UUID(as_uuid=True), unique=True, nullable=False)
    question: str = db.Column(db.Text, nullable=False)
    anonymous: bool = db.Column(db.Boolean, nullable=False, default=False)
    options: List[Option] = db.relationship('Option', backref='poll', lazy=True)
    votes: List[Vote] = db.relationship('Vote', backref='poll', lazy=True)

    def __init__(self, identifier: UUID, question: str, anonymous: bool = False):
        self.identifier = identifier
        self.question = question
        self.anonymous = anonymous

    def poll_identifier(self) -> str:
        return f'{self.identifier}'
