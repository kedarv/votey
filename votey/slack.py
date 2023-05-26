import hashlib
import hmac
import json
import shlex
import time
import uuid
from typing import Any
from typing import Dict
from typing import List
from typing import Optional

import requests
from flask import Blueprint
from flask import current_app
from flask import jsonify
from flask import request

from .exts import db
from .models import Option
from .models import Poll
from .models import Vote
from .models import Workspace
from .utils import AnyJSON
from .utils import batch
from .utils import Command
from .utils import get_footer
from .utils import JSON
from .utils import OptionData

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

ANON_KEYWORDS = {
    "--anonymous",
    "-anonymous",
    "-anon",
    "--anon",
}

SECRET_KEYWORDS = {
    "--secret",
    "-secret",
}

LIMIT_KEYWORDS = {
    "--limit",
    "-limit",
}


@bp.route("/slack", methods=["POST"])
def slack() -> Any:
    return (
        handle_button_interaction(request.form)
        if valid_request(request) and request.form.get("payload")
        else handle_poll_creation(request.form)
        if valid_request(request)
        else ""
    )


@bp.route("/oauth", methods=["GET"])
def oauth() -> str:
    current_app.logger.debug("beginning oauth handshake")
    code = request.args.get("code")
    client_id = current_app.config["CLIENT_ID"]
    client_secret = current_app.config["CLIENT_SECRET"]
    oauth = requests.get(
        "https://slack.com/api/oauth.access",
        params={"code": code, "client_id": client_id, "client_secret": client_secret},
    )
    if oauth.json().get("ok"):
        team_id = oauth.json().get("team_id")
        token = oauth.json().get("access_token")
        name = oauth.json().get("team_name")
        workspace = Workspace.query.filter_by(team_id=team_id).first()
        if workspace is not None:
            workspace.token = token
        else:
            workspace = Workspace(
                team_id=team_id,
                name=name,
                token=token,
            )
            db.session.add(workspace)
        db.session.commit()
        current_app.logger.debug("oauth handshake successful")
        return f"thanks! votey has been installed to <b>{name}</b>. you can close this tab."
    current_app.logger.error("oauth handshake failed")
    return "something went wrong :("


def generate_poll_markup(poll_id: int) -> List[Dict[str, Any]]:
    poll = Poll.query.filter_by(id=poll_id).first()
    options = Option.query.filter_by(poll_id=poll_id)
    actions = []
    fields = []
    for option_index, option in enumerate(options):
        votes = Vote.query.filter_by(
            option_id=option.id,
        ).all()
        actions.append(
            {
                "name": str(option_index),
                "text": option.option_emoji or NUM_TO_SLACKMOJI[option_index + 1],
                "value": option.id,
                "type": "button",
            }
        )
        field_text = (
            f"{option.option_emoji or NUM_TO_SLACKMOJI[option_index+1]} {option.option_text}\t"
            f'{f"`{len(votes)}`" if votes else ""}\n'
            f"{thumbs(votes, poll.vote_emoji) if poll.anonymous else names(votes)}\n\n"
        )

        fields.append(
            {
                "title": "",
                "value": field_text,
                "short": False,
                "mrkdwn": "true",
            }
        )

    attachments = [
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
    for batched in batch(actions, 5):
        attachments.append(
            {
                "text": " ",
                "callback_id": poll.poll_identifier(),
                "attachment_type": "default",
                "color": "#6ecadc",
                "actions": batched,
            }
        )
    return attachments


def handle_poll_creation(req: JSON) -> Any:
    current_app.logger.debug(f"creating poll with json {req}")
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
        author=req.get("user_id") if not cmd.secret else None,
        vote_limit=cmd.vote_limit,
    )
    db.session.add(poll)
    db.session.commit()

    for option_data in cmd.options:
        option = Option(
            poll_id=poll.id,
            option_text=option_data.text,
            option_emoji=option_data.emoji,
        )
        db.session.add(option)
        db.session.commit()

    attachments = generate_poll_markup(poll_id=poll.id)

    delete_attachment = {
        "text": " ",
        "callback_id": poll.poll_identifier(),
        "actions": [
            {"name": "delete", "text": "Delete", "type": "button", "style": "danger"}
        ],
    }
    current_app.logger.debug(f"writing poll to channel {channel}")
    res = send_message(workspace, channel, attachments=attachments).json()
    current_app.logger.debug(f"got poll creation response: {res}")
    if "ts" in res:
        poll.ts = res["ts"]
        db.session.commit()

        send_message(
            workspace,
            req.get("user_id", ""),
            text=f'Delete your last poll, "{cmd.question}"?',
            attachments=[delete_attachment],
        )
    else:
        body = {
            "response_type": "in_channel",
            "text": " ",
            "attachments": attachments,
        }
        current_app.logger.debug(f"DIRECTLY returning {body}")
        return jsonify(body)
    return ""


def handle_button_interaction(req: JSON) -> Any:
    res = json.loads(req.get("payload", ""))
    button = res.get("actions")[0]["name"]
    return handle_poll_deletion(res) if button == "delete" else handle_vote(res)


def handle_vote(response: AnyJSON) -> Any:
    current_app.logger.debug(f"handling vote with req {response}")
    poll = Poll.query.filter_by(identifier=response.get("callback_id")).first()
    option = Option.query.filter_by(id=response.get("actions", [])[0]["value"]).first()
    user = response.get("user", {}).get("id")
    workspace = Workspace.query.filter_by(
        team_id=response.get("team", {}).get("id")
    ).first()

    if poll is not None and option is not None:
        vote = Vote.query.filter_by(
            poll_id=poll.id, option_id=option.id, user=user
        ).first()

        if vote:
            db.session.delete(vote)
        else:
            user_votes_for_poll = Vote.query.filter_by(
                poll_id=poll.id, user=user
            ).count()
            if (
                poll.vote_limit is not None
                and user_votes_for_poll + 1 > poll.vote_limit
            ):
                send_ephemeral_message(
                    workspace,
                    response["channel"]["id"],
                    response["user"]["id"],
                    f"This poll is limited to {poll.vote_limit} option{'s' if poll.vote_limit > 1 else ''}, please remove an existing vote before casting a new vote.",
                )
                return jsonify({"attachments": generate_poll_markup(poll_id=poll.id)})

            vote = Vote(
                poll_id=poll.id,
                option_id=option.id,
                user=user,
            )
            db.session.add(vote)
        db.session.commit()

        # Slack API kind of sucks
        # Return a dictionary with the attachments key to update a message
        # Is this even documented anywhere anymore?
        return jsonify({"attachments": generate_poll_markup(poll_id=poll.id)})
    return ""


def handle_poll_deletion(response: AnyJSON) -> str:
    workspace = Workspace.query.filter_by(
        team_id=response.get("team", {}).get("id")
    ).first()
    poll = Poll.query.filter_by(identifier=response.get("callback_id")).first()
    if poll is None or workspace is None:
        return ""
    Vote.query.filter_by(poll_id=poll.id).delete()
    Option.query.filter_by(poll_id=poll.id).delete()

    db.session.delete(poll)
    db.session.commit()

    requests.post(
        "https://slack.com/api/chat.delete",
        json={"channel": poll.channel, "ts": poll.ts},
        headers={"Authorization": f"Bearer {workspace.token}"},
    )
    return f'Your poll "{poll.question}" has been deleted.'


def thumbs(votes: List[Vote], vote_emoji: Optional[str]) -> str:
    if vote_emoji:
        return vote_emoji * len(votes)
    return ":thumbsup:" * len(votes)


def names(votes: List[Vote]) -> str:
    return ",".join([f"<@{vote.user}>" for vote in votes])


def is_slackmoji(string: str) -> bool:
    return string.startswith(":") and string.endswith(":")


def valid_request(request: Any) -> bool:
    timestamp = request.headers["X-Slack-Request-Timestamp"]
    slack_signature = request.headers["X-Slack-Signature"]

    # Avoid replay attacks
    if abs(time.time() - int(timestamp)) > (60 * 5):
        return False
    sig_basestring = str.encode(f"v0:{timestamp}:") + request.get_data()
    request_hash = (
        "v0="
        + hmac.new(
            bytes(current_app.config["SIGNING_SECRET"], encoding="utf-8"),
            sig_basestring,
            hashlib.sha256,
        ).hexdigest()
    )
    return hmac.compare_digest(request_hash, slack_signature)


def get_command_from_req(request: JSON, workspace: Workspace) -> Optional[Command]:
    try:
        fixed_quote_string = request.get("text", "").replace("“", '"').replace("”", '"')
        split = shlex.split(fixed_quote_string, posix=False)
    except ValueError as e:
        send_ephemeral_message(
            workspace,
            request.get("channel_id", ""),
            request.get("user_id", ""),
            f"We had trouble parsing that - {e}",
        )
        return None

    if not [
        word for word in split if any(keyword in word for keyword in ANON_KEYWORDS)
    ]:
        anonymous = False
    else:
        anonymous = True

    if not [
        word for word in split if any(keyword in word for keyword in SECRET_KEYWORDS)
    ]:
        secret = False
    else:
        secret = True
        anonymous = True

    anon_secret_opt = [
        word
        for word in split
        if any(keyword in word for keyword in ANON_KEYWORDS.union(SECRET_KEYWORDS))
    ]

    limit_opt = [
        word for word in split if any(keyword in word for keyword in LIMIT_KEYWORDS)
    ]

    vote_emoji = None
    if (
        anon_secret_opt
        and "=" in anon_secret_opt[0]
        and is_slackmoji(anon_secret_opt[0].split("=")[1])
    ):
        vote_emoji = anon_secret_opt[0].split("=")[1]

    vote_limit = None
    if limit_opt:
        if "=" in limit_opt[0]:
            try:
                vote_limit = int(limit_opt[0].split("=")[1])
                if vote_limit < 1:
                    raise
            except Exception:
                send_ephemeral_message(
                    workspace,
                    request.get("channel_id", ""),
                    request.get("user_id", ""),
                    "Oops - you must specify a numeric value when using `--limit`"
                    'Try again with `/votey "question" "option 1" --limit=1`',
                )
                return None
        else:
            send_ephemeral_message(
                workspace,
                request.get("channel_id", ""),
                request.get("user_id", ""),
                "Oops - you must specify a value when using `--limit`"
                'Try again with `/votey "question" "option 1" --limit=1`',
            )
            return None

    # Filter out the anonymous or secret options
    split = [
        word
        for word in split
        if not any(
            keyword in word
            for keyword in ANON_KEYWORDS.union(SECRET_KEYWORDS).union(LIMIT_KEYWORDS)
        )
    ]

    if len(split) < 2:
        send_ephemeral_message(
            workspace,
            request.get("channel_id", ""),
            request.get("user_id", ""),
            "Oops - a poll needs to have at least one option. "
            'Try again with `/votey "question" "option 1"`',
        )
        return None

    poll_question = split.pop(0)
    if poll_question.startswith('"') and poll_question.endswith('"'):
        poll_question = poll_question[1:-1]

    options = []
    while split:
        option = split.pop(0)
        if option.startswith('"') and option.endswith('"'):
            option = option[1:-1]

        maybe_emoji = None
        if split:
            maybe_emoji = split.pop(0)
            # If the next item in the list is not an emoji, put it back and set emoji to None
            if not is_slackmoji(maybe_emoji):
                split.insert(0, maybe_emoji)
                maybe_emoji = None

        options.append(
            OptionData(
                text=option,
                emoji=maybe_emoji,
            )
        )

    if vote_limit and vote_limit > len(options):
        send_ephemeral_message(
            workspace,
            request.get("channel_id", ""),
            request.get("user_id", ""),
            "Whoops, your desired vote limit is larger than the number of options you provided.",
        )
        return None
    
    if len(options) > 10:
        send_ephemeral_message(
            workspace,
            request.get("channel_id", ""),
            request.get("user_id", ""),
            "Sorry - Votey only supports 10 options at the moment.",
        )
        return None

    return Command(
        question=poll_question,
        options=options,
        anonymous=anonymous,
        secret=secret,
        vote_emoji=vote_emoji,
        vote_limit=vote_limit,
    )


def send_ephemeral_message(
    workspace: Workspace,
    channel: str,
    user: str,
    text: str,
) -> requests.Response:
    return requests.post(
        "https://slack.com/api/chat.postEphemeral",
        json={"channel": channel, "user": user, "text": text},
        headers={"Authorization": f"Bearer {workspace.token}"},
    )


def send_message(
    workspace: Workspace,
    dest: str,
    text: Optional[str] = None,
    attachments: Optional[List[Any]] = None,
) -> requests.Response:
    body: Any = {"channel": dest}
    if text is not None:
        body["text"] = text
    if attachments is not None:
        body["attachments"] = attachments

    return requests.post(
        "https://slack.com/api/chat.postMessage",
        json=body,
        headers={"Authorization": f"Bearer {workspace.token}"},
    )
