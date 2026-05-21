from unittest.mock import MagicMock
from unittest.mock import patch

from slack_sdk.errors import SlackApiError

from votey.exts import db
from votey.models import Workspace


def _mock_web_client(payload):
    """Build a `WebClient` whose `oauth_access` returns a dict-like response."""
    web_client = MagicMock()
    web_client.oauth_access.return_value = payload
    return web_client


def _slack_api_error(payload):
    response = MagicMock()
    response.data = payload
    return SlackApiError(payload.get("error", "error"), response=response)


def test_oauth_creates_new_workspace(client):
    payload = {
        "ok": True,
        "access_token": "xoxb-new-token",
        "team_id": "T123",
        "team_name": "Acme",
    }
    web_client = _mock_web_client(payload)
    with patch("votey.slack.WebClient", return_value=web_client) as web_client_cls:
        res = client.get("/oauth?code=the-code")

    assert res.status_code == 200
    assert b"Acme" in res.data

    workspace = Workspace.query.filter_by(team_id="T123").one()
    assert workspace.token == "xoxb-new-token"
    assert workspace.name == "Acme"

    web_client_cls.assert_called_once_with()
    web_client.oauth_access.assert_called_once_with(
        client_id="test-client-id",
        client_secret="test-client-secret",
        code="the-code",
    )


def test_oauth_updates_existing_workspace_token(client):
    db.session.add(Workspace(team_id="T123", name="Old name", token="xoxb-old"))
    db.session.commit()

    payload = {
        "ok": True,
        "access_token": "xoxb-rotated",
        "team_id": "T123",
        "team_name": "Acme",
    }
    with patch("votey.slack.WebClient", return_value=_mock_web_client(payload)):
        res = client.get("/oauth?code=the-code")

    assert res.status_code == 200
    workspaces = Workspace.query.filter_by(team_id="T123").all()
    assert len(workspaces) == 1
    assert workspaces[0].token == "xoxb-rotated"


def test_oauth_failure_does_not_create_workspace(client):
    web_client = MagicMock()
    web_client.oauth_access.side_effect = _slack_api_error(
        {"ok": False, "error": "invalid_code"}
    )
    with patch("votey.slack.WebClient", return_value=web_client):
        res = client.get("/oauth?code=bad-code")

    assert res.status_code == 200
    assert b"something went wrong" in res.data
    assert Workspace.query.count() == 0
