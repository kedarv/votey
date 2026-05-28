import json
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

from votey.exts import db
from votey.models import Option
from votey.models import Poll
from votey.models import Workspace
from votey.slack import handle_view_submission


class _FakeSlackResponse(dict):
    """Dict + `.data` attribute, mirroring `slack_sdk.web.SlackResponse`."""

    @property
    def data(self):
        return self


@pytest.fixture
def workspace(app):
    ws = Workspace(team_id="T1", name="Acme", token="xoxb-test")
    db.session.add(ws)
    db.session.commit()
    return ws


def _state_values(
    *,
    channel="C-target",
    question="What's up?",
    options=(("Yes", ""), ("No", "")),
    anonymous=False,
    secret=False,
    vote_emoji="",
    vote_limit="",
):
    values = {
        "channel_block": {"channel": {"selected_conversation": channel}},
        "question_block": {"question": {"value": question}},
        "flags_block": {"flags": {"selected_options": []}},
        "vote_emoji_block": {"vote_emoji": {"value": vote_emoji}},
        "vote_limit_block": {"vote_limit": {"value": vote_limit}},
    }
    if anonymous:
        values["flags_block"]["flags"]["selected_options"].append(
            {"value": "anonymous"}
        )
    if secret:
        values["flags_block"]["flags"]["selected_options"].append({"value": "secret"})

    for i, (text, emoji) in enumerate(options, start=1):
        values[f"option_{i}_block"] = {f"option_{i}": {"value": text}}
        values[f"option_{i}_emoji_block"] = {f"option_{i}_emoji": {"value": emoji}}
    return values


def _payload(state_values, *, channel="C-target", user="U1", team="T1"):
    return {
        "type": "view_submission",
        "team": {"id": team},
        "user": {"id": user},
        "view": {
            "id": "V1",
            "hash": "h1",
            "state": {"values": state_values},
            "private_metadata": json.dumps({"channel_id": channel}),
        },
    }


def _body(response):
    return json.loads(response.get_data(as_text=True))


def test_view_submission_rejects_when_no_options_provided(workspace):
    state = _state_values(options=(("", ""), ("", "")))
    payload = _payload(state)

    with patch("votey.slack.create_and_post_poll") as creator:
        body = _body(handle_view_submission(payload))

    assert body == {
        "response_action": "errors",
        "errors": {"option_1_block": "Please provide at least one option."},
    }
    creator.assert_not_called()


def test_view_submission_rejects_non_numeric_vote_limit(workspace):
    state = _state_values(vote_limit="abc")
    payload = _payload(state)

    with patch("votey.slack.create_and_post_poll") as creator:
        body = _body(handle_view_submission(payload))

    assert body["response_action"] == "errors"
    assert "vote_limit_block" in body["errors"]
    creator.assert_not_called()


def test_view_submission_rejects_vote_limit_larger_than_option_count(workspace):
    state = _state_values(options=(("yes", ""), ("no", "")), vote_limit="5")
    payload = _payload(state)

    with patch("votey.slack.create_and_post_poll") as creator:
        body = _body(handle_view_submission(payload))

    assert body["response_action"] == "errors"
    assert "vote_limit_block" in body["errors"]
    creator.assert_not_called()


def test_view_submission_rejects_missing_channel(workspace):
    state = _state_values(channel=None)
    payload = _payload(state, channel=None)
    payload["view"]["private_metadata"] = json.dumps({"channel_id": None})

    with patch("votey.slack.create_and_post_poll") as creator:
        body = _body(handle_view_submission(payload))

    assert body["response_action"] == "errors"
    assert "channel_block" in body["errors"]
    creator.assert_not_called()


def test_view_submission_returns_channel_error_when_post_fails(workspace):
    state = _state_values()
    payload = _payload(state)

    with patch("votey.slack.create_and_post_poll", return_value=(None, [])) as creator:
        body = _body(handle_view_submission(payload))

    creator.assert_called_once()
    assert body["response_action"] == "errors"
    assert "channel_block" in body["errors"]


def test_view_submission_happy_path_creates_and_posts_poll(workspace):
    state = _state_values(
        question="Pizza?",
        options=(("Yes", ":pizza:"), ("No", "")),
        anonymous=True,
        vote_emoji=":fire:",
        vote_limit="1",
    )
    payload = _payload(state, user="U-author")
    fake_response = _FakeSlackResponse({"ts": "1234.5"})

    with patch(
        "votey.slack.create_and_post_poll",
        return_value=(fake_response, []),
    ) as creator:
        res = handle_view_submission(payload)

    assert res == ""
    creator.assert_called_once()
    ws_arg, channel_arg, user_arg, cmd_arg = creator.call_args.args
    assert ws_arg.team_id == "T1"
    assert channel_arg == "C-target"
    assert user_arg == "U-author"
    assert cmd_arg.question == "Pizza?"
    assert [(o.text, o.emoji) for o in cmd_arg.options] == [
        ("Yes", ":pizza:"),
        ("No", None),
    ]
    assert cmd_arg.anonymous is True
    assert cmd_arg.secret is False
    assert cmd_arg.vote_emoji == ":fire:"
    assert cmd_arg.vote_limit == 1


def test_view_submission_secret_implies_anonymous(workspace):
    state = _state_values(secret=True, anonymous=False)
    payload = _payload(state)
    fake_response = _FakeSlackResponse({"ts": "1.0"})

    with patch(
        "votey.slack.create_and_post_poll",
        return_value=(fake_response, []),
    ) as creator:
        handle_view_submission(payload)

    cmd = creator.call_args.args[3]
    assert cmd.secret is True
    assert cmd.anonymous is True


def test_view_submission_drops_non_slackmoji_vote_emoji(workspace):
    state = _state_values(vote_emoji="not-an-emoji")
    payload = _payload(state)
    fake_response = _FakeSlackResponse({"ts": "1.0"})

    with patch(
        "votey.slack.create_and_post_poll",
        return_value=(fake_response, []),
    ) as creator:
        handle_view_submission(payload)

    cmd = creator.call_args.args[3]
    assert cmd.vote_emoji is None


def test_view_submission_persists_poll_through_create_and_post_poll(workspace):
    """End-to-end-ish: don't mock create_and_post_poll; only mock the Slack
    client so the DB rows are actually written by the real helper."""
    state = _state_values(
        question="Lunch?", options=(("Pizza", ":pizza:"), ("Salad", ""))
    )
    payload = _payload(state, user="U-author")

    fake_client = MagicMock()
    fake_client.chat_postMessage.return_value = _FakeSlackResponse({"ts": "12345.6789"})

    with patch("votey.slack._client", return_value=fake_client):
        res = handle_view_submission(payload)

    assert res == ""
    poll = Poll.query.filter_by(question="Lunch?").one()
    assert poll.channel == "C-target"
    assert poll.author == "U-author"
    assert poll.ts == "12345.6789"
    options = Option.query.filter_by(poll_id=poll.id).order_by(Option.id.asc()).all()
    assert [(o.option_text, o.option_emoji) for o in options] == [
        ("Pizza", ":pizza:"),
        ("Salad", None),
    ]
    assert fake_client.chat_postMessage.called
