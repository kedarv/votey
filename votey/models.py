from datetime import datetime
from typing import TYPE_CHECKING

from .exts import db

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.types import TypeEngine

    UuidType = TypeEngine[uuid.UUID]  # type: ignore[type-arg]
else:
    from sqlalchemy import Uuid  # type: ignore[attr-defined]

    UuidType = Uuid(as_uuid=True)

BaseModel = db.Model


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
    identifier = db.Column(UuidType, unique=True, nullable=False)
    question = db.Column(db.Text, nullable=False)
    anonymous = db.Column(db.Boolean, nullable=False, default=False)
    secret = db.Column(db.Boolean, nullable=False, default=False)
    vote_emoji = db.Column(db.Text, nullable=True)
    author = db.Column(db.Text, nullable=True)
    options = db.relationship(
        "Option", backref="poll", lazy="select", order_by="Option.id"
    )
    votes = db.relationship("Vote", backref="poll", lazy="select")
    ts = db.Column(db.Text, nullable=True)
    channel = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)
    vote_limit = db.Column(db.Integer, nullable=True)

    @property
    def callback_id(self) -> str:
        return str(self.identifier)
