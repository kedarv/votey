import json

from votey.modal import ADD_OPTION_ACTION_ID
from votey.modal import CALLBACK_ID
from votey.modal import MAX_OPTIONS
from votey.modal import build_create_poll_view
from votey.modal import read_view_values


def _block_ids(view):
    return [b.get("block_id") for b in view["blocks"]]


def _block_by_id(view, block_id):
    for b in view["blocks"]:
        if b.get("block_id") == block_id:
            return b
    raise AssertionError(f"missing block {block_id}; have {_block_ids(view)}")


def test_default_view_has_two_option_rows_channel_question_flags_and_add_button():
    view = build_create_poll_view(channel_id="C123")

    assert view["type"] == "modal"
    assert view["callback_id"] == CALLBACK_ID
    meta = json.loads(view["private_metadata"])
    assert meta == {"channel_id": "C123"}

    block_ids = _block_ids(view)
    assert "channel_block" in block_ids
    assert "question_block" in block_ids
    for i in (1, 2):
        assert f"option_{i}_block" in block_ids
        assert f"option_{i}_emoji_block" not in block_ids
    assert "option_3_block" not in block_ids
    assert "add_option_block" in block_ids
    assert "flags_block" in block_ids
    assert "vote_emoji_block" not in block_ids
    assert "vote_limit_block" in block_ids


def test_channel_block_default_to_current_conversation_and_initial_conversation():
    view = build_create_poll_view(channel_id="C123")

    channel_block = _block_by_id(view, "channel_block")
    element = channel_block["element"]
    assert element["type"] == "conversations_select"
    assert element["default_to_current_conversation"] is True
    assert element["initial_conversation"] == "C123"


def test_channel_block_omits_initial_conversation_when_no_channel():
    view = build_create_poll_view(channel_id=None)

    channel_block = _block_by_id(view, "channel_block")
    assert "initial_conversation" not in channel_block["element"]


def test_add_option_button_hidden_at_max_options():
    view = build_create_poll_view(channel_id="C1", option_count=MAX_OPTIONS)

    block_ids = _block_ids(view)
    assert "add_option_block" not in block_ids
    for i in range(1, MAX_OPTIONS + 1):
        assert f"option_{i}_block" in block_ids
        assert f"option_{i}_emoji_block" not in block_ids


def test_option_count_is_capped_at_max_options():
    view = build_create_poll_view(channel_id="C1", option_count=99)

    block_ids = _block_ids(view)
    assert f"option_{MAX_OPTIONS}_block" in block_ids
    assert f"option_{MAX_OPTIONS + 1}_block" not in block_ids
    assert "add_option_block" not in block_ids


def test_add_option_block_uses_expected_action_id():
    view = build_create_poll_view(channel_id="C1", option_count=2)

    button = _block_by_id(view, "add_option_block")["elements"][0]
    assert button["action_id"] == ADD_OPTION_ACTION_ID
    assert button["type"] == "button"


def test_prefill_values_populate_initial_values():
    prefill = {
        "question": "What's for lunch?",
        "options": [("Pizza", ":pizza:"), ("Salad", "")],
        "anonymous": True,
        "secret": False,
        "vote_emoji": ":heart:",
        "vote_limit_raw": "1",
        "channel_id": "C-pref",
    }
    view = build_create_poll_view(
        channel_id="C-orig", option_count=2, prefill_values=prefill
    )

    assert (
        _block_by_id(view, "channel_block")["element"]["initial_conversation"]
        == "C-pref"
    )
    assert (
        _block_by_id(view, "question_block")["element"]["initial_value"]
        == "What's for lunch?"
    )
    assert _block_by_id(view, "option_1_block")["element"]["initial_value"] == "Pizza"
    assert _block_by_id(view, "option_2_block")["element"]["initial_value"] == "Salad"

    flags_element = _block_by_id(view, "flags_block")["element"]
    initial_options = flags_element.get("initial_options", [])
    assert [opt["value"] for opt in initial_options] == ["anonymous"]

    assert _block_by_id(view, "vote_limit_block")["element"]["initial_value"] == "1"


def test_read_view_values_round_trips_prefill():
    prefill = {
        "question": "Best stack?",
        "options": [("Flask", ""), ("Django", ""), ("Rails", "")],
        "anonymous": False,
        "secret": True,
        "vote_emoji": "",
        "vote_limit_raw": "2",
        "channel_id": "C-target",
    }
    view = build_create_poll_view(
        channel_id="C-target", option_count=3, prefill_values=prefill
    )

    state_values = {}
    for block in view["blocks"]:
        if block.get("type") != "input":
            continue
        block_id = block["block_id"]
        element = block["element"]
        action_id = element["action_id"]
        if element["type"] == "plain_text_input" or element["type"] == "number_input":
            state_values[block_id] = {
                action_id: {"value": element.get("initial_value")}
            }
        elif element["type"] == "conversations_select":
            state_values[block_id] = {
                action_id: {
                    "selected_conversation": element.get("initial_conversation")
                }
            }
        elif element["type"] == "checkboxes":
            state_values[block_id] = {
                action_id: {
                    "selected_options": element.get("initial_options", []),
                }
            }

    submitted_view = {
        "state": {"values": state_values},
        "private_metadata": view["private_metadata"],
        "blocks": view["blocks"],
    }
    result = read_view_values(submitted_view)

    assert result["question"] == prefill["question"]
    assert result["options"] == prefill["options"]
    assert result["anonymous"] is False
    assert result["secret"] is True
    assert result["vote_emoji"] == ""
    assert result["vote_limit_raw"] == "2"
    assert result["channel_id"] == "C-target"


def test_read_view_values_falls_back_to_private_metadata_channel():
    view = {
        "state": {"values": {}},
        "private_metadata": json.dumps({"channel_id": "C-from-meta"}),
        "blocks": [],
    }

    result = read_view_values(view)

    assert result["channel_id"] == "C-from-meta"
    assert result["options"] == []
    assert result["question"] == ""
    assert result["anonymous"] is False
    assert result["secret"] is False
