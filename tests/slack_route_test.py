import json
from unittest.mock import patch


def test_slack_route_with_inline_text_dispatches_to_poll_creation(client):
    with (
        patch("votey.slack.valid_request", return_value=True) as valid,
        patch("votey.slack.handle_poll_creation", return_value="ok") as create,
        patch("votey.slack.open_create_modal") as open_modal,
    ):
        res = client.post(
            "/slack",
            data={"team_id": "T1", "text": '"q" "a" "b"'},
        )

    assert res.status_code == 200
    assert valid.call_count == 1
    create.assert_called_once()
    open_modal.assert_not_called()


def test_slack_route_with_empty_text_opens_modal(client):
    with (
        patch("votey.slack.valid_request", return_value=True) as valid,
        patch("votey.slack.open_create_modal", return_value="") as open_modal,
        patch("votey.slack.handle_poll_creation") as create,
    ):
        res = client.post(
            "/slack",
            data={"team_id": "T1", "text": "", "trigger_id": "trig.1"},
        )

    assert res.status_code == 200
    assert valid.call_count == 1
    open_modal.assert_called_once()
    create.assert_not_called()


def test_slack_route_with_whitespace_only_text_opens_modal(client):
    with (
        patch("votey.slack.valid_request", return_value=True),
        patch("votey.slack.open_create_modal", return_value="") as open_modal,
        patch("votey.slack.handle_poll_creation") as create,
    ):
        res = client.post("/slack", data={"team_id": "T1", "text": "   "})

    assert res.status_code == 200
    open_modal.assert_called_once()
    create.assert_not_called()


def test_slack_route_dispatches_view_submission(client):
    payload = {"type": "view_submission", "view": {}}
    with (
        patch("votey.slack.valid_request", return_value=True) as valid,
        patch("votey.slack.handle_view_submission", return_value="") as view_sub,
        patch("votey.slack.handle_button_interaction") as button,
    ):
        res = client.post("/slack", data={"payload": json.dumps(payload)})

    assert res.status_code == 200
    assert valid.call_count == 1
    view_sub.assert_called_once()
    button.assert_not_called()


def test_slack_route_dispatches_block_actions_with_view(client):
    payload = {"type": "block_actions", "view": {"id": "V1"}, "actions": []}
    with (
        patch("votey.slack.valid_request", return_value=True),
        patch("votey.slack.handle_modal_block_action", return_value="") as modal,
        patch("votey.slack.handle_button_interaction") as button,
    ):
        res = client.post("/slack", data={"payload": json.dumps(payload)})

    assert res.status_code == 200
    modal.assert_called_once()
    button.assert_not_called()


def test_slack_route_legacy_interactive_message_payload_still_routes_to_buttons(client):
    payload = {
        "type": "interactive_message",
        "actions": [{"name": "0"}],
    }
    with (
        patch("votey.slack.valid_request", return_value=True),
        patch("votey.slack.handle_button_interaction", return_value="ok") as button,
        patch("votey.slack.handle_view_submission") as view_sub,
        patch("votey.slack.handle_modal_block_action") as modal,
    ):
        res = client.post("/slack", data={"payload": json.dumps(payload)})

    assert res.status_code == 200
    button.assert_called_once()
    view_sub.assert_not_called()
    modal.assert_not_called()


def test_slack_route_short_circuits_on_invalid_request(client):
    with (
        patch("votey.slack.valid_request", return_value=False) as valid,
        patch("votey.slack.handle_button_interaction") as button,
        patch("votey.slack.handle_poll_creation") as create,
        patch("votey.slack.open_create_modal") as open_modal,
        patch("votey.slack.handle_view_submission") as view_sub,
        patch("votey.slack.handle_modal_block_action") as modal,
    ):
        res = client.post("/slack", data={"payload": "{}", "text": "anything"})

    assert res.status_code == 200
    assert res.data == b""
    assert valid.call_count == 1
    button.assert_not_called()
    create.assert_not_called()
    open_modal.assert_not_called()
    view_sub.assert_not_called()
    modal.assert_not_called()
