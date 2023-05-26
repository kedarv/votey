from datetime import datetime
from typing import TYPE_CHECKING

from .exts import db

if TYPE_CHECKING:
    import uuid

    from flask_sqlalchemy.model import Model
    from sqlalchemy.types import TypeEngine

    BaseModel = db.make_declarative_base(Model)
    UUID = TypeEngine[uuid.UUID]  # pylint: disable=unsubscriptable-object

else:
    import sqlalchemy.dialects.postgresql

    BaseModel = db.Model
    UUID = sqlalchemy.dialects.postgresql.UUID(as_uuid=True)


class Workspace(BaseModel):
    id = db.Column(db.Integer, primary_key=True)
    team_id = db.Column(db.Text, nullable=False)
    name = db.Column(db.Text, nullable=False)
    token = db.Column(db.Text, nullable=False)


class Vote(BaseModel):
    id = db.Column(db.Integer, primary_key=True)
    poll_id = db.Column(db.Integer, db.ForeignKey("poll.id"), nullable=False)
    option_id = db.Column(db.Integer, db.ForeignKey("option.id"), nullable=False)
    user = db.Column(db.Text, nullable=False)


class Option(BaseModel):
    id = db.Column(db.Integer, primary_key=True)
    poll_id = db.Column(db.Integer, db.ForeignKey("poll.id"), nullable=False)
    option_text = db.Column(db.Text, nullable=False)
    option_emoji = db.Column(db.Text, nullable=True)
    votes = db.relationship("Vote", backref="option", lazy="select")


class Poll(BaseModel):
    id = db.Column(db.Integer, primary_key=True)
    identifier = db.Column(UUID, unique=True, nullable=False)
    question = db.Column(db.Text, nullable=False)
    anonymous = db.Column(db.Boolean, nullable=False, default=False)
    secret = db.Column(db.Boolean, nullable=False, default=False)
    vote_emoji = db.Column(db.Text, nullable=True)
    author = db.Column(db.Text, nullable=True)
    options = db.relationship("Option", backref="poll", lazy="select")
    votes = db.relationship("Vote", backref="poll", lazy="select")
    ts = db.Column(db.Text, nullable=True)
    channel = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)
    vote_limit = db.Column(db.Integer, nullable=False)

    def poll_identifier(self) -> str:
        return f"{self.identifier}"
