"""Socket Mode handler for Votey using slack-bolt."""

import logging
import os
from typing import Any

from slack_bolt import App
from slack_bolt.context.ack import Ack
from slack_bolt.context.respond import Respond
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from .modal import ADD_OPTION_ACTION_ID
from .modal import CALLBACK_ID
from .modal import build_create_poll_view
from .modal import read_view_values
from .models import Workspace
from .slack import _parse_callback_id
from .slack import create_and_post_poll
from .slack import delete_poll
from .slack import parse_command_text
from .slack import toggle_vote
from .slack import validate_view_submission
from .utils import MAX_OPTIONS

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

        def reply(msg: str) -> None:
            try:
                client.chat_postEphemeral(
                    channel=channel_id, user=user_id, text=msg
                )
            except SlackApiError as e:
                logger.warning("chat.postEphemeral failed: %s", e.response.data)

        cmd = parse_command_text(text, reply)
        if cmd is None:
            ack()
            return

        ack()
        create_and_post_poll(workspace, channel_id, user_id, cmd, client=client)

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
            identifier = _parse_callback_id(body.get("callback_id"))
            if identifier is None:
                return
            workspace = Workspace.query.filter_by(
                team_id=body.get("team", {}).get("id")
            ).first()
            if workspace is None:
                return
            msg = delete_poll(identifier, client)
            channel_id = body.get("channel", {}).get("id", "")
            message_ts = (
                body.get("message_ts")
                or body.get("original_message", {}).get("ts")
            )
            if channel_id and message_ts and msg:
                try:
                    client.chat_update(
                        channel=channel_id, ts=message_ts,
                        text=msg, attachments=[],
                    )
                except SlackApiError as e:
                    logger.warning("chat.update failed: %s", e.response.data)
        else:
            identifier = _parse_callback_id(body.get("callback_id"))
            if identifier is None:
                return
            option_id = actions[0]["value"]
            user = body.get("user", {}).get("id", "")
            channel_id = body.get("channel", {}).get("id", "")

            attachments, _ = toggle_vote(
                identifier, option_id, user, client, channel_id, user,
            )
            if attachments is None:
                return
            message_ts = (
                body.get("message_ts")
                or body.get("original_message", {}).get("ts")
            )
            if channel_id and message_ts:
                try:
                    client.chat_update(
                        channel=channel_id, ts=message_ts,
                        attachments=attachments,
                    )
                except SlackApiError as e:
                    logger.warning("chat.update failed: %s", e.response.data)

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
        cmd, channel, errors = validate_view_submission(view)

        if errors or cmd is None:
            ack(response_action="errors", errors=errors)
            return

        ack()
        create_and_post_poll(workspace, channel, user_id, cmd, client=client)

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
