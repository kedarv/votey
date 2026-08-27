"""Socket Mode handler for Votey using slack-bolt."""

import logging
import os
import shlex
import uuid
from typing import Any

from slack_bolt import App
from slack_bolt.context.ack import Ack
from slack_bolt.context.respond import Respond
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from .exts import db
from .modal import ADD_OPTION_ACTION_ID
from .modal import CALLBACK_ID
from .modal import build_create_poll_view
from .modal import read_view_values
from .models import Option
from .models import Poll
from .models import Vote
from .models import Workspace
from .slack import ALL_FLAG_KEYWORDS
from .slack import ANON_KEYWORDS
from .slack import LIMIT_KEYWORDS
from .slack import SECRET_KEYWORDS
from .slack import _CLI_ERROR_MESSAGES
from .slack import _MODAL_ERROR_MESSAGES
from .slack import _find_flag_value
from .slack import _has_flag
from .slack import _parse_options
from .slack import _strip_outer_quotes
from .slack import generate_poll_markup
from .utils import MAX_OPTIONS
from .utils import Command
from .utils import CommandError
from .utils import OptionData
from .utils import build_command
from .utils import is_slackmoji
from .utils import pluralize

logger = logging.getLogger(__name__)


def create_bolt_app(signing_secret: str) -> App:
    bot_token = os.environ.get("SLACK_BOT_TOKEN", "")
    bolt_app = App(
        signing_secret=signing_secret,
        token=bot_token,
        token_verification_enabled=False,
        request_verification_enabled=False,
    )
    _register_handlers(bolt_app)
    return bolt_app


def _register_handlers(bolt_app: App) -> None:
    @bolt_app.command("/votey")
    def handle_votey_command(
        ack: Ack,
        body: dict[str, Any],
        client: WebClient,
        respond: Respond,
    ) -> None:
        text = body.get("text", "").strip()
        team_id = body.get("team_id", "")
        channel_id = body.get("channel_id", "")
        user_id = body.get("user_id", "")
        trigger_id = body.get("trigger_id", "")

        workspace = Workspace.query.filter_by(team_id=team_id).first()
        if workspace is None:
            ack("Something went wrong finding your workspace!")
            return

        if not text:
            view = build_create_poll_view(channel_id=channel_id)
            ack()
            try:
                client.views_open(trigger_id=trigger_id, view=view)
            except SlackApiError as e:
                logger.warning("views.open failed: %s", e.response.data)
            return

        cmd = _parse_command_text(text, workspace, channel_id, user_id, client)
        if cmd is None:
            ack()
            return

        ack()
        _create_and_post_poll_socket(workspace, channel_id, user_id, cmd, client)

    @bolt_app.action({"type": "interactive_message"})
    def handle_legacy_action(
        ack: Ack,
        body: dict[str, Any],
        client: WebClient,
    ) -> None:
        actions = body.get("actions", [])
        if not actions:
            ack()
            return

        ack()
        button_name = actions[0].get("name", "")
        if button_name == "delete":
            _handle_poll_deletion_socket(body, client)
        else:
            _handle_vote_socket(body, client)

    @bolt_app.view(CALLBACK_ID)
    def handle_create_poll_view(
        ack: Ack,
        body: dict[str, Any],
        client: WebClient,
    ) -> None:
        team_id = body.get("team", {}).get("id", "")
        workspace = Workspace.query.filter_by(team_id=team_id).first()
        if workspace is None:
            ack(
                response_action="errors",
                errors={"channel_block": "Workspace not found."},
            )
            return

        view = body.get("view") or {}
        user_id = body.get("user", {}).get("id", "")
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
            ack(response_action="errors", errors=errors)
            return

        ack()
        _create_and_post_poll_socket(workspace, channel, user_id, cmd, client)

    @bolt_app.action(ADD_OPTION_ACTION_ID)
    def handle_add_option(
        ack: Ack,
        body: dict[str, Any],
        client: WebClient,
    ) -> None:
        ack()
        team_id = body.get("team", {}).get("id", "")
        workspace = Workspace.query.filter_by(team_id=team_id).first()
        if workspace is None:
            return

        view = body.get("view") or {}
        values = read_view_values(view)
        current_count = len(values.get("options") or [])
        new_count = min(current_count + 1, MAX_OPTIONS)

        new_view = build_create_poll_view(
            channel_id=values.get("channel_id"),
            option_count=new_count,
            prefill_values=values,
        )
        try:
            client.views_update(
                view_id=view.get("id"),
                hash=view.get("hash"),
                view=new_view,
            )
        except SlackApiError as e:
            logger.warning("views.update failed: %s", e.response.data)


def _parse_command_text(
    text: str,
    workspace: Workspace,
    channel_id: str,
    user_id: str,
    client: WebClient,
) -> Command | None:
    def reply(msg: str) -> None:
        try:
            client.chat_postEphemeral(channel=channel_id, user=user_id, text=msg)
        except SlackApiError as e:
            logger.warning("chat.postEphemeral failed: %s", e.response.data)

    try:
        fixed_quotes = text.replace("“", '"').replace("”", '"')
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


def _create_and_post_poll_socket(
    workspace: Workspace,
    channel: str,
    user_id: str,
    cmd: Command,
    client: WebClient,
) -> None:
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

    try:
        res = client.chat_postMessage(channel=channel, attachments=attachments)
    except SlackApiError as e:
        logger.warning("chat.postMessage failed: %s", e.response.data)
        return

    poll.ts = res["ts"]
    db.session.commit()

    delete_attachment = {
        "text": " ",
        "callback_id": poll.callback_id,
        "actions": [
            {"name": "delete", "text": "Delete", "type": "button", "style": "danger"}
        ],
    }
    try:
        client.chat_postMessage(
            channel=user_id,
            text=f'Delete your last poll, "{cmd.question}"?',
            attachments=[delete_attachment],
        )
    except SlackApiError as e:
        logger.warning("DM delete-button failed: %s", e.response.data)


def _handle_vote_socket(body: dict[str, Any], client: WebClient) -> None:
    callback_id = body.get("callback_id")
    identifier = _parse_callback_id(callback_id)
    if identifier is None:
        return

    poll = Poll.query.filter_by(identifier=identifier).first()
    actions = body.get("actions", [])
    if not actions:
        return
    option = Option.query.filter_by(id=actions[0]["value"]).first()
    if poll is None or option is None:
        return

    user = body.get("user", {}).get("id")
    team_id = body.get("team", {}).get("id", "")
    workspace = Workspace.query.filter_by(team_id=team_id).first()

    vote = Vote.query.filter_by(poll_id=poll.id, option_id=option.id, user=user).first()
    if vote is not None:
        db.session.delete(vote)
    else:
        user_votes_for_poll = Vote.query.filter_by(poll_id=poll.id, user=user).count()
        if poll.vote_limit is not None and user_votes_for_poll >= poll.vote_limit:
            try:
                client.chat_postEphemeral(
                    channel=body["channel"]["id"],
                    user=body["user"]["id"],
                    text=(
                        f"This poll is limited to {poll.vote_limit} "
                        f"{pluralize(poll.vote_limit, 'option')}, please remove an "
                        f"existing vote before casting a new vote."
                    ),
                )
            except SlackApiError as e:
                logger.warning("chat.postEphemeral failed: %s", e.response.data)
            return

        db.session.add(Vote(poll_id=poll.id, option_id=option.id, user=user))
    db.session.commit()

    attachments = generate_poll_markup(poll_id=poll.id)
    channel_id = body.get("channel", {}).get("id", "")
    message_ts = body.get("message_ts") or body.get("original_message", {}).get("ts")
    if channel_id and message_ts:
        try:
            client.chat_update(
                channel=channel_id,
                ts=message_ts,
                attachments=attachments,
            )
        except SlackApiError as e:
            logger.warning("chat.update failed: %s", e.response.data)


def _handle_poll_deletion_socket(body: dict[str, Any], client: WebClient) -> None:
    team_id = body.get("team", {}).get("id", "")
    workspace = Workspace.query.filter_by(team_id=team_id).first()
    callback_id = body.get("callback_id")
    identifier = _parse_callback_id(callback_id)
    if identifier is None or workspace is None:
        return

    poll = Poll.query.filter_by(identifier=identifier).first()
    if poll is None:
        return

    Vote.query.filter_by(poll_id=poll.id).delete()
    Option.query.filter_by(poll_id=poll.id).delete()
    db.session.delete(poll)
    db.session.commit()

    try:
        client.chat_delete(channel=poll.channel, ts=poll.ts)
    except SlackApiError as e:
        logger.warning("chat.delete failed: %s", e.response.data)

    channel_id = body.get("channel", {}).get("id", "")
    message_ts = body.get("message_ts") or body.get("original_message", {}).get("ts")
    if channel_id and message_ts:
        try:
            client.chat_update(
                channel=channel_id,
                ts=message_ts,
                text=f'Your poll "{poll.question}" has been deleted.',
                attachments=[],
            )
        except SlackApiError as e:
            logger.warning("chat.update (delete confirm) failed: %s", e.response.data)


def _parse_callback_id(callback_id: Any) -> uuid.UUID | None:
    if isinstance(callback_id, uuid.UUID):
        return callback_id
    if not isinstance(callback_id, str):
        return None
    try:
        return uuid.UUID(callback_id)
    except ValueError:
        logger.warning("received non-uuid callback_id: %r", callback_id)
        return None
