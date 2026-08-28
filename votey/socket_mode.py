"""Socket Mode transport for the shared Slack request handlers."""

from threading import Event
from typing import Any

from flask import Flask
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from slack_sdk.socket_mode import SocketModeClient
from slack_sdk.socket_mode.request import SocketModeRequest
from slack_sdk.socket_mode.response import SocketModeResponse

from .exts import db
from .models import Workspace
from .slack import SlackResult
from .slack import dispatch_interaction
from .slack import dispatch_slash_command


def create_socket_mode_client(app: Flask) -> SocketModeClient:
    """Create a configured Socket Mode client without connecting it."""
    app_token = _required_config(app, "SLACK_APP_TOKEN")
    bot_token = _required_config(app, "SLACK_BOT_TOKEN")
    web_client = WebClient(token=bot_token)
    client = SocketModeClient(
        app_token=app_token,
        web_client=web_client,
        logger=app.logger,
    )

    def listener(socket_client: Any, socket_request: SocketModeRequest) -> None:
        process_socket_mode_request(app, socket_client, socket_request)

    client.socket_mode_request_listeners.append(listener)
    return client


def process_socket_mode_request(
    app: Flask,
    client: Any,
    socket_request: SocketModeRequest,
) -> None:
    """Dispatch one Socket Mode envelope and acknowledge it exactly once."""
    result: SlackResult = ""
    try:
        with app.app_context():
            if socket_request.type == "slash_commands":
                result = dispatch_slash_command(socket_request.payload)
            elif socket_request.type == "interactive":
                result = dispatch_interaction(socket_request.payload)
            else:
                app.logger.debug(
                    "ignoring unsupported Socket Mode request type %s",
                    socket_request.type,
                )
    except Exception:
        app.logger.exception(
            "failed to process Socket Mode request %s", socket_request.type
        )
    finally:
        client.send_socket_mode_response(
            SocketModeResponse(
                envelope_id=socket_request.envelope_id,
                payload=result or None,
            )
        )


def start_socket_mode(app: Flask) -> None:
    """Connect to Slack and block while the Socket Mode client is running."""
    client = create_socket_mode_client(app)
    try:
        _register_socket_workspace(app, client.web_client)
        app.logger.info("starting Slack Socket Mode transport")
        client.connect()
        Event().wait()
    finally:
        client.close()  # type: ignore[no-untyped-call]


def _register_socket_workspace(app: Flask, web_client: WebClient) -> None:
    """Make the configured bot token available to the shared workspace lookup."""
    try:
        auth = web_client.auth_test()
    except SlackApiError as error:
        raise RuntimeError(
            f"SLACK_BOT_TOKEN authentication failed: {error.response.data}"
        ) from error

    team_id = auth.get("team_id")
    if not isinstance(team_id, str) or not team_id:
        raise RuntimeError("Slack auth.test did not return a team_id")

    team_name = auth.get("team")
    bot_token = _required_config(app, "SLACK_BOT_TOKEN")
    with app.app_context():
        workspace = Workspace.query.filter_by(team_id=team_id).first()
        if workspace is None:
            workspace = Workspace(
                team_id=team_id,
                name=team_name or team_id,
                token=bot_token,
            )
            db.session.add(workspace)
        else:
            workspace.name = team_name or workspace.name
            workspace.token = bot_token
        db.session.commit()


def _required_config(app: Flask, key: str) -> str:
    value = app.config.get(key)
    if not isinstance(value, str) or not value.strip():
        raise RuntimeError(f"{key} is required when SLACK_MODE=socket")
    return value
