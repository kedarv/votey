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
from .modal import ADD_OPTION_ACTION_ID
from .modal import build_create_poll_view
from .modal import read_view_values
from .models import Option
from .models import Poll
from .models import Vote
from .models import Workspace
from .utils import JSON
from .utils import MAX_OPTIONS
from .utils import AnyJSON
from .utils import Command
from .utils import CommandError
from .utils import OptionData
from .utils import build_command
from .utils import get_footer
from .utils import is_slackmoji
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

ACTIONS_PER_ATTACHMENT = 5

_CLI_ERROR_MESSAGES: dict[CommandError, str] = {
    CommandError.NO_OPTIONS: (
        "Oops - a poll needs to have at least one option. "
        'Try again with `/votey "question" "option 1"`'
    ),
    CommandError.TOO_MANY_OPTIONS: (
        f"Sorry - Votey only supports {MAX_OPTIONS} options at the moment."
    ),
    CommandError.LIMIT_NOT_INT: (
        "Oops - you must specify a numeric value when using `--limit`. "
        'Try again with `/votey "question" "option 1" --limit=1`'
    ),
    CommandError.LIMIT_TOO_LOW: (
        "Oops - you must specify a numeric value when using `--limit`. "
        'Try again with `/votey "question" "option 1" --limit=1`'
    ),
    CommandError.LIMIT_EXCEEDS_OPTIONS: (
        "Whoops, your desired vote limit is larger than the number of options "
        "you provided."
    ),
}

_MODAL_ERROR_MESSAGES: dict[CommandError, tuple[str, str]] = {
    CommandError.NO_OPTIONS: (
        "option_1_block",
        "Please provide at least one option.",
    ),
    CommandError.TOO_MANY_OPTIONS: (
        "option_1_block",
        f"Sorry - Votey only supports {MAX_OPTIONS} options at the moment.",
    ),
    CommandError.LIMIT_NOT_INT: (
        "vote_limit_block",
        "Vote limit must be a whole number.",
    ),
    CommandError.LIMIT_TOO_LOW: (
        "vote_limit_block",
        "Vote limit must be at least 1.",
    ),
    CommandError.LIMIT_EXCEEDS_OPTIONS: (
        "vote_limit_block",
        "Vote limit can't exceed the number of options.",
    ),
}


@bp.route("/slack", methods=["POST"])
def slack() -> Any:
    if not valid_request(request):
        return ""
    payload_raw = request.form.get("payload")
    if payload_raw:
        try:
            payload = json.loads(payload_raw)
        except (json.JSONDecodeError, TypeError):
            current_app.logger.warning("invalid interactive payload: %r", payload_raw)
            return ""
        ptype = payload.get("type")
        if ptype == "view_submission":
            return handle_view_submission(payload)
        if ptype == "block_actions" and payload.get("view"):
            return handle_modal_block_action(payload)
        return handle_button_interaction(request.form)
    if request.form.get("text", "").strip():
        return handle_poll_creation(request.form)
    return open_create_modal(request.form)


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
    user_id = req.get("user_id", "")
    res, attachments = create_and_post_poll(workspace, channel, user_id, cmd)
    if res is None or "ts" not in res:
        body = {
            "response_type": "in_channel",
            "text": " ",
            "attachments": attachments,
        }
        current_app.logger.debug("DIRECTLY returning %s", body)
        return jsonify(body)
    return ""


def create_and_post_poll(
    workspace: Workspace,
    channel: str,
    user_id: str,
    cmd: Command,
) -> tuple[SlackResponse | None, list[dict[str, Any]]]:
    """Persist a poll, post it to `channel`, and DM the author a delete button.

    Returns the `chat.postMessage` response (or `None` if the API call failed)
    plus the rendered attachments so the caller can fall back to an inline
    response or surface an error to the user.
    """
    poll = Poll(
        identifier=uuid.uuid4(),
        question=cmd.question,
        channel=channel,
        anonymous=cmd.anonymous,
        secret=cmd.secret,
        vote_emoji=cmd.vote_emoji,
        author=None if cmd.secret else user_id,
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

    current_app.logger.debug("writing poll to channel %s", channel)
    res = send_message(workspace, channel, attachments=attachments)
    current_app.logger.debug(
        "got poll creation response: %s", res.data if res else None
    )
    if res is None or "ts" not in res:
        return res, attachments

    poll.ts = res["ts"]
    db.session.commit()

    delete_attachment = {
        "text": " ",
        "callback_id": poll.callback_id,
        "actions": [
            {"name": "delete", "text": "Delete", "type": "button", "style": "danger"}
        ],
    }
    send_message(
        workspace,
        user_id,
        text=f'Delete your last poll, "{cmd.question}"?',
        attachments=[delete_attachment],
    )
    return res, attachments


def open_create_modal(req: JSON) -> Any:
    workspace = Workspace.query.filter_by(team_id=req.get("team_id")).first()
    if workspace is None:
        return "Something went wrong finding your workspace!"
    trigger_id = req.get("trigger_id", "")
    channel_id = req.get("channel_id", "")
    view = build_create_poll_view(channel_id=channel_id)
    try:
        _client(workspace).views_open(trigger_id=trigger_id, view=view)
    except SlackApiError as e:
        current_app.logger.warning("views.open failed: %s", e.response.data)
        return "Couldn't open the poll modal - please try again."
    return ""


def handle_view_submission(payload: AnyJSON) -> Any:
    current_app.logger.debug("handling view_submission %s", payload)
    workspace = Workspace.query.filter_by(
        team_id=payload.get("team", {}).get("id")
    ).first()
    if workspace is None:
        return jsonify(
            {
                "response_action": "errors",
                "errors": {"channel_block": "Workspace not found."},
            }
        )

    view = payload.get("view") or {}
    user_id = payload.get("user", {}).get("id", "")
    values = read_view_values(view)

    raw_options: list[tuple[str, str]] = list(values.get("options") or [])
    options = [
        OptionData(
            text=text.strip(),
            emoji=(emoji.strip() if is_slackmoji(emoji.strip()) else None),
        )
        for text, emoji in raw_options
        if text.strip()
    ]

    cmd, err = build_command(
        question=(values.get("question") or "").strip(),
        options=options,
        anonymous=bool(values.get("anonymous")),
        secret=bool(values.get("secret")),
        vote_emoji_raw=(values.get("vote_emoji") or "").strip(),
        vote_limit_raw=(values.get("vote_limit_raw") or "").strip() or None,
    )

    errors: dict[str, str] = {}
    if err is not None:
        block_id, message = _MODAL_ERROR_MESSAGES[err]
        errors[block_id] = message

    channel = values.get("channel_id") or ""
    if not channel:
        errors.setdefault("channel_block", "Please select a channel to post to.")

    if errors or cmd is None:
        return jsonify({"response_action": "errors", "errors": errors})

    res, _ = create_and_post_poll(workspace, channel, user_id, cmd)
    if res is None or "ts" not in res:
        return jsonify(
            {
                "response_action": "errors",
                "errors": {
                    "channel_block": (
                        "Couldn't post the poll to that channel - make sure "
                        "Votey has been added to it."
                    )
                },
            }
        )

    return ""


def handle_modal_block_action(payload: AnyJSON) -> Any:
    workspace = Workspace.query.filter_by(
        team_id=payload.get("team", {}).get("id")
    ).first()
    if workspace is None:
        return ""
    actions = payload.get("actions") or []
    if not actions or actions[0].get("action_id") != ADD_OPTION_ACTION_ID:
        return ""

    view = payload.get("view") or {}
    values = read_view_values(view)
    current_count = len(values.get("options") or [])
    new_count = min(current_count + 1, MAX_OPTIONS)

    new_view = build_create_poll_view(
        channel_id=values.get("channel_id"),
        option_count=new_count,
        prefill_values=values,
    )
    try:
        _client(workspace).views_update(
            view_id=view.get("id"),
            hash=view.get("hash"),
            view=new_view,
        )
    except SlackApiError as e:
        current_app.logger.warning("views.update failed: %s", e.response.data)
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
    anonymous = _has_flag(tokens, ANON_KEYWORDS)
    flag_emoji = _find_flag_value(tokens, ANON_KEYWORDS | SECRET_KEYWORDS)

    vote_limit_raw: str | None = None
    if _has_flag(tokens, LIMIT_KEYWORDS):
        vote_limit_raw = _find_flag_value(tokens, LIMIT_KEYWORDS)
        if vote_limit_raw is None:
            reply(
                "Oops - you must specify a value when using `--limit`. "
                'Try again with `/votey "question" "option 1" --limit=1`'
            )
            return None

    positional = [
        tok for tok in tokens if not any(tok.startswith(kw) for kw in ALL_FLAG_KEYWORDS)
    ]
    poll_question = _strip_outer_quotes(positional[0]) if positional else ""
    options = _parse_options(positional[1:]) if len(positional) >= 2 else []

    cmd, err = build_command(
        question=poll_question,
        options=options,
        anonymous=anonymous,
        secret=secret,
        vote_emoji_raw=flag_emoji,
        vote_limit_raw=vote_limit_raw,
    )
    if err is not None:
        reply(_CLI_ERROR_MESSAGES[err])
        return None
    return cmd


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
