"""Builders for the /votey creation modal.

The view is composed with `slack_sdk.models` Block Kit classes (`View`,
`InputBlock`, `ActionsBlock`, etc.) and serialized to a plain dict at the
boundary so existing callers and tests continue to work against JSON shapes.

`read_view_values` keeps walking the incoming Slack payload dict directly,
which is the idiomatic shape on the inbound side.
"""

import json
import re
from typing import Any

from slack_sdk.models.blocks import ActionsBlock
from slack_sdk.models.blocks import Block
from slack_sdk.models.blocks import ButtonElement
from slack_sdk.models.blocks import CheckboxesElement
from slack_sdk.models.blocks import ConversationSelectElement
from slack_sdk.models.blocks import InputBlock
from slack_sdk.models.blocks import NumberInputElement
from slack_sdk.models.blocks import Option
from slack_sdk.models.blocks import PlainTextInputElement
from slack_sdk.models.views import View

from .utils import AnyJSON

MAX_OPTIONS = 10
DEFAULT_OPTION_COUNT = 2
CALLBACK_ID = "votey_create_poll"
ADD_OPTION_ACTION_ID = "add_option"

_OPTION_BLOCK_RE = re.compile(r"^option_(\d+)_block$")

_ANON_OPTION = Option(value="anonymous", text="Anonymous (hide voter names)")
_SECRET_OPTION = Option(value="secret", text="Secret (hide creator + voters)")


def build_create_poll_view(
    channel_id: str | None,
    option_count: int = DEFAULT_OPTION_COUNT,
    prefill_values: AnyJSON | None = None,
) -> AnyJSON:
    """Build the JSON payload for the /votey creation modal view.

    `prefill_values` is the normalized dict returned by `read_view_values`.
    It is consumed when re-rendering during `block_actions` (Add option button);
    `open_create_modal` always passes `None`.
    """
    option_count = max(1, min(option_count, MAX_OPTIONS))
    prefill: AnyJSON = prefill_values or {}
    prefill_options: list[tuple[str, str]] = list(prefill.get("options") or [])

    blocks: list[Block] = [
        _channel_block(channel_id, prefill),
        _question_block(prefill),
    ]
    for i in range(1, option_count + 1):
        prefill_text = ""
        if i - 1 < len(prefill_options):
            prefill_text, _ = prefill_options[i - 1]
        blocks.append(_option_block(i, prefill_text))
    if option_count < MAX_OPTIONS:
        blocks.append(_add_option_block())
    blocks.append(_flags_block(prefill))
    blocks.append(_vote_limit_block(prefill))

    view = View(
        type="modal",
        callback_id=CALLBACK_ID,
        title="Create a poll",
        submit="Create",
        close="Cancel",
        private_metadata=json.dumps({"channel_id": channel_id}),
        blocks=blocks,
    )
    return view.to_dict()


def read_view_values(view: AnyJSON) -> AnyJSON:
    """Pull a normalized dict of values out of a Slack `view` payload."""
    values: dict[str, Any] = view.get("state", {}).get("values", {}) or {}

    channel_state = values.get("channel_block", {}).get("channel", {})
    channel_id: str | None = channel_state.get("selected_conversation")
    if not channel_id:
        try:
            meta = json.loads(view.get("private_metadata") or "{}")
        except json.JSONDecodeError, TypeError:
            meta = {}
        channel_id = meta.get("channel_id") if isinstance(meta, dict) else None

    question = values.get("question_block", {}).get("question", {}).get("value") or ""

    indexes: set[int] = set()
    for block_id in values:
        match = _OPTION_BLOCK_RE.match(block_id)
        if match:
            indexes.add(int(match.group(1)))
    option_count = max(indexes, default=0)

    options: list[tuple[str, str]] = []
    for i in range(1, option_count + 1):
        text = (
            values.get(f"option_{i}_block", {}).get(f"option_{i}", {}).get("value")
            or ""
        )
        emoji = (
            values.get(f"option_{i}_emoji_block", {})
            .get(f"option_{i}_emoji", {})
            .get("value")
            or ""
        )
        options.append((text, emoji))

    selected = (
        values.get("flags_block", {}).get("flags", {}).get("selected_options") or []
    )
    flag_values = {opt.get("value") for opt in selected}
    anonymous = "anonymous" in flag_values
    secret = "secret" in flag_values

    vote_emoji = (
        values.get("vote_emoji_block", {}).get("vote_emoji", {}).get("value") or ""
    )
    vote_limit_raw = (
        values.get("vote_limit_block", {}).get("vote_limit", {}).get("value") or ""
    )

    return {
        "question": question,
        "options": options,
        "anonymous": anonymous,
        "secret": secret,
        "vote_emoji": vote_emoji,
        "vote_limit_raw": vote_limit_raw,
        "channel_id": channel_id,
    }


def _channel_block(channel_id: str | None, prefill: AnyJSON) -> InputBlock:
    initial = prefill.get("channel_id") or channel_id
    return InputBlock(
        block_id="channel_block",
        label="Post to channel",
        element=ConversationSelectElement(
            action_id="channel",
            default_to_current_conversation=True,
            initial_conversation=initial or None,
        ),
    )


def _question_block(prefill: AnyJSON) -> InputBlock:
    return InputBlock(
        block_id="question_block",
        label="Question or Topic",
        element=PlainTextInputElement(
            action_id="question",
            placeholder="Which day works best for team lunch?",
            initial_value=prefill.get("question") or None,
        ),
    )


def _option_block(index: int, prefill_text: str) -> InputBlock:
    return InputBlock(
        block_id=f"option_{index}_block",
        label=f"Option {index}",
        element=PlainTextInputElement(
            action_id=f"option_{index}",
            initial_value=prefill_text or None,
        ),
        optional=index > 1,
    )


def _add_option_block() -> ActionsBlock:
    return ActionsBlock(
        block_id="add_option_block",
        elements=[
            ButtonElement(action_id=ADD_OPTION_ACTION_ID, text="Add option"),
        ],
    )


def _flags_block(prefill: AnyJSON) -> InputBlock:
    initial: list[Option] = []
    if prefill.get("anonymous"):
        initial.append(_ANON_OPTION)
    if prefill.get("secret"):
        initial.append(_SECRET_OPTION)
    return InputBlock(
        block_id="flags_block",
        label="Settings",
        element=CheckboxesElement(
            action_id="flags",
            options=[_ANON_OPTION, _SECRET_OPTION],
            initial_options=initial or None,
        ),
        optional=True,
    )


def _vote_limit_block(prefill: AnyJSON) -> InputBlock:
    return InputBlock(
        block_id="vote_limit_block",
        label="Vote limit",
        element=NumberInputElement(
            action_id="vote_limit",
            is_decimal_allowed=False,
            min_value=1,
            initial_value=prefill.get("vote_limit_raw") or None,
        ),
        optional=True,
    )
