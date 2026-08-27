from unittest.mock import MagicMock
from unittest.mock import patch

import pytest
from slack_sdk.socket_mode.request import SocketModeRequest

from votey.models import Workspace
from votey.socket_mode import _register_socket_workspace
from votey.socket_mode import create_socket_mode_client
from votey.socket_mode import process_socket_mode_request


def _request(request_type, payload):
    return SocketModeRequest(
        type=request_type,
        envelope_id="envelope-1",
        payload=payload,
        accepts_response_payload=True,
    )


def _sent_response(client):
    return client.send_socket_mode_response.call_args.args[0]


def test_socket_mode_slash_command_uses_shared_dispatch(app):
    payload = {"team_id": "T1", "text": '"Question" "Yes"'}
    client = MagicMock()
    result = {"response_type": "in_channel", "text": "created"}

    with patch(
        "votey.socket_mode.dispatch_slash_command", return_value=result
    ) as dispatch:
        process_socket_mode_request(app, client, _request("slash_commands", payload))

    dispatch.assert_called_once_with(payload)
    response = _sent_response(client)
    assert response.envelope_id == "envelope-1"
    assert response.payload == result


def test_socket_mode_interaction_uses_shared_dispatch(app):
    payload = {
        "type": "interactive_message",
        "callback_id": "00000000-0000-0000-0000-000000000001",
        "actions": [{"name": "0", "value": "1"}],
    }
    client = MagicMock()
    result = {"attachments": [{"text": "updated"}]}

    with patch(
        "votey.socket_mode.dispatch_interaction", return_value=result
    ) as dispatch:
        process_socket_mode_request(app, client, _request("interactive", payload))

    dispatch.assert_called_once_with(payload)
    assert _sent_response(client).payload == result


def test_socket_mode_acknowledges_unsupported_envelopes(app):
    client = MagicMock()

    process_socket_mode_request(app, client, _request("events_api", {"event": {}}))

    response = _sent_response(client)
    assert response.envelope_id == "envelope-1"
    assert response.payload is None


def test_socket_mode_acknowledges_handler_errors(app):
    client = MagicMock()

    with patch(
        "votey.socket_mode.dispatch_interaction", side_effect=RuntimeError("boom")
    ):
        process_socket_mode_request(app, client, _request("interactive", {}))

    assert _sent_response(client).payload is None


def test_create_socket_mode_client_requires_both_tokens(app):
    app.config.update(SLACK_APP_TOKEN="xapp-test", SLACK_BOT_TOKEN=None)

    with pytest.raises(RuntimeError, match="SLACK_BOT_TOKEN"):
        create_socket_mode_client(app)


def test_create_socket_mode_client_registers_one_listener(app):
    app.config.update(
        SLACK_APP_TOKEN="xapp-test",
        SLACK_BOT_TOKEN="xoxb-test",
    )
    fake_client = MagicMock()
    fake_client.socket_mode_request_listeners = []

    with patch("votey.socket_mode.SocketModeClient", return_value=fake_client) as cls:
        result = create_socket_mode_client(app)

    assert result is fake_client
    assert len(fake_client.socket_mode_request_listeners) == 1
    assert cls.call_args.kwargs["app_token"] == "xapp-test"
    assert cls.call_args.kwargs["web_client"].token == "xoxb-test"


def test_socket_mode_registers_workspace_from_bot_token(app):
    app.config["SLACK_BOT_TOKEN"] = "xoxb-socket-token"
    web_client = MagicMock()
    web_client.auth_test.return_value = {"team_id": "T-socket", "team": "Acme"}

    _register_socket_workspace(app, web_client)

    with app.app_context():
        workspace = Workspace.query.filter_by(team_id="T-socket").one()
        assert workspace.name == "Acme"
        assert workspace.token == "xoxb-socket-token"


def test_socket_mode_refreshes_existing_workspace_token(app):
    app.config["SLACK_BOT_TOKEN"] = "xoxb-new"
    with app.app_context():
        from votey.exts import db

        db.session.add(Workspace(team_id="T1", name="Old", token="xoxb-old"))
        db.session.commit()

    web_client = MagicMock()
    web_client.auth_test.return_value = {"team_id": "T1", "team": "Acme"}

    _register_socket_workspace(app, web_client)

    with app.app_context():
        workspace = Workspace.query.filter_by(team_id="T1").one()
        assert workspace.name == "Acme"
        assert workspace.token == "xoxb-new"
