from unittest.mock import patch


def test_slack_route_validates_request_once_for_poll_creation(client):
    with (
        patch("votey.slack.valid_request", return_value=True) as valid,
        patch("votey.slack.handle_poll_creation", return_value="ok") as create,
    ):
        res = client.post("/slack", data={"team_id": "T1", "text": ""})

    assert res.status_code == 200
    assert valid.call_count == 1
    create.assert_called_once()


def test_slack_route_validates_request_once_for_button_interaction(client):
    with (
        patch("votey.slack.valid_request", return_value=True) as valid,
        patch("votey.slack.handle_button_interaction", return_value="ok") as button,
    ):
        res = client.post("/slack", data={"payload": "{}"})

    assert res.status_code == 200
    assert valid.call_count == 1
    button.assert_called_once()


def test_slack_route_short_circuits_on_invalid_request(client):
    with (
        patch("votey.slack.valid_request", return_value=False) as valid,
        patch("votey.slack.handle_button_interaction") as button,
        patch("votey.slack.handle_poll_creation") as create,
    ):
        res = client.post("/slack", data={"payload": "{}", "text": "anything"})

    assert res.status_code == 200
    assert res.data == b""
    assert valid.call_count == 1
    button.assert_not_called()
    create.assert_not_called()
