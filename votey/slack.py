import json
import shlex
import time
import uuid
from itertools import batched
from typing import Any

from flask import Blueprint
from flask import current_app
from flask import jsonify
from flask import request
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from slack_sdk.signature import SignatureVerifier
from slack_sdk.web import SlackResponse
from sqlalchemy.orm import selectinload

from .exts import db
from .models import Option
from .models import Poll
from .models import Vote
from .models import Workspace
from .utils import JSON
from .utils import AnyJSON
from .utils import Command
from .utils import OptionData
from .utils import get_footer
from .utils import pluralize

bp = Blueprint("slack", __name__)

NUM_TO_SLACKMOJI = {
    1: ":one:",
    2: ":two:",
    3: ":three:",
    4: ":four:",
    5: ":five:",
    6: ":six:",
    7: ":seven:",
    8: ":eight:",
    9: ":nine:",
    10: ":keycap_ten:",
}

ANON_KEYWORDS = {"--anonymous", "-anonymous", "-anon", "--anon"}
SECRET_KEYWORDS = {"--secret", "-secret"}
LIMIT_KEYWORDS = {"--limit", "-limit"}
ALL_FLAG_KEYWORDS = ANON_KEYWORDS | SECRET_KEYWORDS | LIMIT_KEYWORDS

MAX_OPTIONS = 10
ACTIONS_PER_ATTACHMENT = 5


@bp.route("/slack", methods=["POST"])
def slack() -> Any:
    if not valid_request(request):
        return ""
    if request.form.get("payload"):
        return handle_button_interaction(request.form)
    return handle_poll_creation(request.form)


@bp.route("/oauth", methods=["GET"])
def oauth() -> str:
    current_app.logger.debug("beginning oauth handshake")
    try:
        response = WebClient().oauth_access(
            client_id=current_app.config["CLIENT_ID"],
            client_secret=current_app.config["CLIENT_SECRET"],
            code=request.args.get("code", ""),
        )
    except SlackApiError as e:
        current_app.logger.error("oauth handshake failed: %s", e.response.data)
        return "something went wrong :("

    team_id = response.get("team_id")
    name = response.get("team_name")
    token = response.get("access_token")
    workspace = Workspace.query.filter_by(team_id=team_id).first()
    if workspace is not None:
        workspace.token = token
    else:
        workspace = Workspace(team_id=team_id, name=name, token=token)
        db.session.add(workspace)
    db.session.commit()
    current_app.logger.debug("oauth handshake successful")
    return f"thanks! votey has been installed to <b>{name}</b>. you can close this tab."


def generate_poll_markup(poll_id: int) -> list[dict[str, Any]]:
    poll = (
        Poll.query.options(selectinload(Poll.options).selectinload(Option.votes))
        .filter_by(id=poll_id)
        .first()
    )
    if poll is None:
        return []

    actions: list[dict[str, Any]] = []
    fields: list[dict[str, Any]] = []
    for option_index, option in enumerate(poll.options):
        votes = option.votes
        emoji = option.option_emoji or NUM_TO_SLACKMOJI[option_index + 1]
        count_str = f"`{len(votes)}`" if votes else ""
        voter_str = thumbs(votes, poll.vote_emoji) if poll.anonymous else names(votes)

        actions.append(
            {
                "name": str(option_index),
                "text": emoji,
                "value": option.id,
                "type": "button",
            }
        )
        fields.append(
            {
                "title": "",
                "value": f"{emoji} {option.option_text}\t{count_str}\n{voter_str}\n\n",
                "short": False,
                "mrkdwn": "true",
            }
        )

    attachments: list[dict[str, Any]] = [
        {
            "text": poll.question,
            "mrkdwn_in": ["fields"],
            "color": "#6ecadc",
            "fields": fields,
            "footer": get_footer(
                poll.author, poll.anonymous, poll.secret, poll.vote_limit
            ),
            "ts": time.time(),
        },
    ]
    for batch_actions in batched(actions, ACTIONS_PER_ATTACHMENT, strict=False):
        attachments.append(
            {
                "text": " ",
                "callback_id": poll.callback_id,
                "attachment_type": "default",
                "color": "#6ecadc",
                "actions": list(batch_actions),
            }
        )
    return attachments


def handle_poll_creation(req: JSON) -> Any:
    current_app.logger.debug("creating poll with json %s", req)
    workspace = Workspace.query.filter_by(team_id=req.get("team_id")).first()
    if workspace is None:
        return "Something went wrong finding your workspace!"
    cmd = get_command_from_req(req, workspace)
    if cmd is None:
        return ""

    channel = req.get("channel_id", "")

    poll = Poll(
        identifier=uuid.uuid4(),
        question=cmd.question,
        channel=channel,
        anonymous=cmd.anonymous,
        secret=cmd.secret,
        vote_emoji=cmd.vote_emoji,
        author=None if cmd.secret else req.get("user_id"),
        vote_limit=cmd.vote_limit,
    )
    db.session.add(poll)
    db.session.commit()

    db.session.add_all(
        Option(
            poll_id=poll.id,
            option_text=opt.text,
            option_emoji=opt.emoji,
        )
        for opt in cmd.options
    )
    db.session.commit()

    attachments = generate_poll_markup(poll_id=poll.id)

    delete_attachment = {
        "text": " ",
        "callback_id": poll.callback_id,
        "actions": [
            {"name": "delete", "text": "Delete", "type": "button", "style": "danger"}
        ],
    }
    current_app.logger.debug("writing poll to channel %s", channel)
    res = send_message(workspace, channel, attachments=attachments)
    current_app.logger.debug(
        "got poll creation response: %s", res.data if res else None
    )
    if res is None or "ts" not in res:
        body = {
            "response_type": "in_channel",
            "text": " ",
            "attachments": attachments,
        }
        current_app.logger.debug("DIRECTLY returning %s", body)
        return jsonify(body)

    poll.ts = res["ts"]
    db.session.commit()
    send_message(
        workspace,
        req.get("user_id", ""),
        text=f'Delete your last poll, "{cmd.question}"?',
        attachments=[delete_attachment],
    )
    return ""


def handle_button_interaction(req: JSON) -> Any:
    res = json.loads(req.get("payload", ""))
    button = res.get("actions")[0]["name"]
    return handle_poll_deletion(res) if button == "delete" else handle_vote(res)


def handle_vote(response: AnyJSON) -> Any:
    current_app.logger.debug("handling vote with req %s", response)
    identifier = _parse_callback_id(response.get("callback_id"))
    if identifier is None:
        return ""
    poll = Poll.query.filter_by(identifier=identifier).first()
    option = Option.query.filter_by(id=response.get("actions", [])[0]["value"]).first()
    if poll is None or option is None:
        return ""

    user = response.get("user", {}).get("id")
    workspace = Workspace.query.filter_by(
        team_id=response.get("team", {}).get("id")
    ).first()

    vote = Vote.query.filter_by(poll_id=poll.id, option_id=option.id, user=user).first()
    if vote is not None:
        db.session.delete(vote)
    else:
        user_votes_for_poll = Vote.query.filter_by(poll_id=poll.id, user=user).count()
        if poll.vote_limit is not None and user_votes_for_poll >= poll.vote_limit:
            send_ephemeral_message(
                workspace,
                response["channel"]["id"],
                response["user"]["id"],
                f"This poll is limited to {poll.vote_limit} "
                f"{pluralize(poll.vote_limit, 'option')}, please remove an "
                f"existing vote before casting a new vote.",
            )
            return jsonify({"attachments": generate_poll_markup(poll_id=poll.id)})

        db.session.add(Vote(poll_id=poll.id, option_id=option.id, user=user))
    db.session.commit()

    # Slack API kind of sucks
    # Return a dictionary with the attachments key to update a message
    # Is this even documented anywhere anymore?
    return jsonify({"attachments": generate_poll_markup(poll_id=poll.id)})


def handle_poll_deletion(response: AnyJSON) -> str:
    workspace = Workspace.query.filter_by(
        team_id=response.get("team", {}).get("id")
    ).first()
    identifier = _parse_callback_id(response.get("callback_id"))
    if identifier is None:
        return ""
    poll = Poll.query.filter_by(identifier=identifier).first()
    if poll is None or workspace is None:
        return ""

    Vote.query.filter_by(poll_id=poll.id).delete()
    Option.query.filter_by(poll_id=poll.id).delete()
    db.session.delete(poll)
    db.session.commit()

    try:
        _client(workspace).chat_delete(channel=poll.channel, ts=poll.ts)
    except SlackApiError as e:
        current_app.logger.warning("chat.delete failed: %s", e.response.data)
    return f'Your poll "{poll.question}" has been deleted.'


def _parse_callback_id(callback_id: Any) -> uuid.UUID | None:
    if isinstance(callback_id, uuid.UUID):
        return callback_id
    if not isinstance(callback_id, str):
        return None
    try:
        return uuid.UUID(callback_id)
    except ValueError:
        current_app.logger.warning("received non-uuid callback_id: %r", callback_id)
        return None


def thumbs(votes: list[Vote], vote_emoji: str | None) -> str:
    return (vote_emoji or ":thumbsup:") * len(votes)


def names(votes: list[Vote]) -> str:
    return ",".join(f"<@{vote.user}>" for vote in votes)


def is_slackmoji(string: str) -> bool:
    return len(string) >= 2 and string.startswith(":") and string.endswith(":")


def valid_request(req: Any) -> bool:
    verifier = SignatureVerifier(current_app.config["SIGNING_SECRET"])
    return verifier.is_valid_request(req.get_data(), dict(req.headers))


def _has_flag(tokens: list[str], keywords: set[str]) -> bool:
    """Return True iff any token starts with one of the option keywords."""
    return any(tok.startswith(kw) for tok in tokens for kw in keywords)


def _find_flag_value(tokens: list[str], keywords: set[str]) -> str | None:
    """Return the `value` part of the first `--keyword=value` token, if any."""
    for tok in tokens:
        for kw in keywords:
            if tok.startswith(f"{kw}="):
                return tok.split("=", 1)[1]
    return None


def _strip_outer_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] == '"':
        return value[1:-1]
    return value


def get_command_from_req(req: JSON, workspace: Workspace) -> Command | None:
    def reply(text: str) -> None:
        send_ephemeral_message(
            workspace,
            req.get("channel_id", ""),
            req.get("user_id", ""),
            text,
        )

    try:
        fixed_quotes = req.get("text", "").replace("“", '"').replace("”", '"')
        tokens = shlex.split(fixed_quotes, posix=False)
    except ValueError as e:
        reply(f"We had trouble parsing that - {e}")
        return None

    secret = _has_flag(tokens, SECRET_KEYWORDS)
    anonymous = secret or _has_flag(tokens, ANON_KEYWORDS)

    flag_emoji = _find_flag_value(tokens, ANON_KEYWORDS | SECRET_KEYWORDS)
    vote_emoji = flag_emoji if flag_emoji and is_slackmoji(flag_emoji) else None

    vote_limit: int | None = None
    if _has_flag(tokens, LIMIT_KEYWORDS):
        raw_limit = _find_flag_value(tokens, LIMIT_KEYWORDS)
        if raw_limit is None:
            reply(
                "Oops - you must specify a value when using `--limit`. "
                'Try again with `/votey "question" "option 1" --limit=1`'
            )
            return None
        try:
            vote_limit = int(raw_limit)
            if vote_limit < 1:
                raise ValueError("vote_limit must be >= 1")
        except ValueError:
            reply(
                "Oops - you must specify a numeric value when using `--limit`. "
                'Try again with `/votey "question" "option 1" --limit=1`'
            )
            return None

    positional = [
        tok for tok in tokens if not any(tok.startswith(kw) for kw in ALL_FLAG_KEYWORDS)
    ]

    if len(positional) < 2:
        reply(
            "Oops - a poll needs to have at least one option. "
            'Try again with `/votey "question" "option 1"`'
        )
        return None

    poll_question = _strip_outer_quotes(positional[0])
    options = _parse_options(positional[1:])

    if vote_limit is not None and vote_limit > len(options):
        reply(
            "Whoops, your desired vote limit is larger than the number of options "
            "you provided."
        )
        return None

    if len(options) > MAX_OPTIONS:
        reply(f"Sorry - Votey only supports {MAX_OPTIONS} options at the moment.")
        return None

    return Command(
        question=poll_question,
        options=options,
        anonymous=anonymous,
        secret=secret,
        vote_emoji=vote_emoji,
        vote_limit=vote_limit,
    )


def _parse_options(tokens: list[str]) -> list[OptionData]:
    """Pair each option token with an optional trailing :slackmoji: token."""
    options: list[OptionData] = []
    it = iter(tokens)
    pending: str | None = None
    for tok in it:
        text = _strip_outer_quotes(pending if pending is not None else tok)
        if pending is not None:
            # We previously buffered an option, now `tok` may be its emoji.
            if is_slackmoji(tok):
                options.append(OptionData(text=text, emoji=tok))
                pending = None
                continue
            options.append(OptionData(text=text, emoji=None))
            pending = tok
        else:
            pending = tok
    if pending is not None:
        options.append(OptionData(text=_strip_outer_quotes(pending), emoji=None))
    return options


def _client(workspace: Workspace) -> WebClient:
    return WebClient(token=workspace.token)


def send_ephemeral_message(
    workspace: Workspace,
    channel: str,
    user: str,
    text: str,
) -> SlackResponse | None:
    try:
        return _client(workspace).chat_postEphemeral(
            channel=channel, user=user, text=text
        )
    except SlackApiError as e:
        current_app.logger.warning("chat.postEphemeral failed: %s", e.response.data)
        return None


def send_message(
    workspace: Workspace,
    dest: str,
    text: str | None = None,
    attachments: list[Any] | None = None,
) -> SlackResponse | None:
    try:
        return _client(workspace).chat_postMessage(
            channel=dest, text=text, attachments=attachments
        )
    except SlackApiError as e:
        current_app.logger.warning("chat.postMessage failed: %s", e.response.data)
        return None
