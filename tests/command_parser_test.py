# type: ignore
from unittest.mock import MagicMock

import pytest

from votey.slack import ANON_KEYWORDS
from votey.slack import get_command_from_req
from votey.slack import SECRET_KEYWORDS
from votey.utils import OptionData

QUESTION = "Some Question?"
FIRST_OPTION = "Some Option1"
SECOND_OPTION = "Some Option2"


def test_basic_command():
    cmd = get_command_from_req(
        {"text": f'"{QUESTION}" "{FIRST_OPTION}" "{SECOND_OPTION}"'}, MagicMock()
    )
    assert cmd is not None
    assert cmd.question == QUESTION
    assert cmd.options == [
        OptionData(FIRST_OPTION, None),
        OptionData(SECOND_OPTION, None),
    ]
    assert not cmd.anonymous
    assert not cmd.secret


@pytest.mark.parametrize(
    "keyword",
    SECRET_KEYWORDS,
)
def test_secret(keyword):
    cmd = get_command_from_req(
        {"text": f'"{QUESTION}" "{FIRST_OPTION}" "{SECOND_OPTION}" {keyword}'},
        MagicMock(),
    )
    assert cmd is not None
    assert cmd.anonymous
    assert cmd.secret


@pytest.mark.parametrize(
    "keyword",
    ANON_KEYWORDS,
)
def test_anonymous(keyword):
    cmd = get_command_from_req(
        {"text": f'"{QUESTION}" "{FIRST_OPTION}" "{SECOND_OPTION}" {keyword}'},
        MagicMock(),
    )
    assert cmd is not None
    assert cmd.anonymous
    assert not cmd.secret


def test_emoji_option_command():
    cmd = get_command_from_req(
        {
            "text": f'"{QUESTION}" "{FIRST_OPTION}" :someemoji1: "{SECOND_OPTION}" :someemoji2:'
        },
        MagicMock(),
    )
    assert cmd is not None
    assert cmd.question == QUESTION
    assert cmd.options == [
        OptionData(FIRST_OPTION, ":someemoji1:"),
        OptionData(SECOND_OPTION, ":someemoji2:"),
    ]
    assert not cmd.anonymous
    assert not cmd.secret


def test_emoji_option_command_without_last_option():
    cmd = get_command_from_req(
        {"text": f'"{QUESTION}" "{FIRST_OPTION}" :someemoji1: "{SECOND_OPTION}"'},
        MagicMock(),
    )
    assert cmd is not None
    assert cmd.question == QUESTION
    assert cmd.options == [
        OptionData(FIRST_OPTION, ":someemoji1:"),
        OptionData(SECOND_OPTION, None),
    ]
    assert not cmd.anonymous
    assert not cmd.secret


def test_emoji_option_command_without_first_option():
    cmd = get_command_from_req(
        {"text": f'"{QUESTION}" "{FIRST_OPTION}" "{SECOND_OPTION}" :some-emoji:'},
        MagicMock(),
    )
    assert cmd is not None
    assert cmd.question == QUESTION
    assert cmd.options == [
        OptionData(FIRST_OPTION, None),
        OptionData(SECOND_OPTION, ":some-emoji:"),
    ]
    assert not cmd.anonymous
    assert not cmd.secret


def test_emoji_option_command_with_secret():
    cmd = get_command_from_req(
        {
            "text": f'"{QUESTION}" "{FIRST_OPTION}" "{SECOND_OPTION}" :some-emoji: --secret'
        },
        MagicMock(),
    )
    assert cmd is not None
    assert cmd.question == QUESTION
    assert cmd.options == [
        OptionData(FIRST_OPTION, None),
        OptionData(SECOND_OPTION, ":some-emoji:"),
    ]
    assert cmd.anonymous
    assert cmd.secret


def test_emoji_option_command_with_anonymous():
    cmd = get_command_from_req(
        {
            "text": f'"{QUESTION}" "{FIRST_OPTION}" :some-emoji: "{SECOND_OPTION}" --anonymous'
        },
        MagicMock(),
    )
    assert cmd is not None
    assert cmd.question == QUESTION
    assert cmd.options == [
        OptionData(FIRST_OPTION, ":some-emoji:"),
        OptionData(SECOND_OPTION, None),
    ]
    assert cmd.anonymous
    assert not cmd.secret


def test_anonymous_with_voting_emoji():
    cmd = get_command_from_req(
        {
            "text": f'"{QUESTION}" "{FIRST_OPTION}" :some-emoji: "{SECOND_OPTION}" --anonymous=:soccer:'
        },
        MagicMock(),
    )
    assert cmd is not None
    assert cmd.question == QUESTION
    assert cmd.options == [
        OptionData(FIRST_OPTION, ":some-emoji:"),
        OptionData(SECOND_OPTION, None),
    ]
    assert cmd.anonymous
    assert not cmd.secret
    assert cmd.vote_emoji == ":soccer:"


def test_secret_with_voting_emoji():
    cmd = get_command_from_req(
        {
            "text": f'"{QUESTION}" "{FIRST_OPTION}" :some-emoji: "{SECOND_OPTION}" --secret=:soccer:'
        },
        MagicMock(),
    )
    assert cmd is not None
    assert cmd.question == QUESTION
    assert cmd.options == [
        OptionData(FIRST_OPTION, ":some-emoji:"),
        OptionData(SECOND_OPTION, None),
    ]
    assert cmd.anonymous
    assert cmd.secret
    assert cmd.vote_emoji == ":soccer:"


def test_limit():
    cmd = get_command_from_req(
        {
            "text": f'"{QUESTION}" "{FIRST_OPTION}" :some-emoji: "{SECOND_OPTION}" --secret=:soccer: --limit=1'
        },
        MagicMock(),
    )
    assert cmd is not None
    assert cmd.question == QUESTION
    assert cmd.options == [
        OptionData(FIRST_OPTION, ":some-emoji:"),
        OptionData(SECOND_OPTION, None),
    ]
    assert cmd.anonymous
    assert cmd.secret
    assert cmd.vote_emoji == ":soccer:"
    assert cmd.vote_limit == 1


def test_limit_larger_than_option_count():
    cmd = get_command_from_req(
        {
            "text": f'"{QUESTION}" "{FIRST_OPTION}" :some-emoji: "{SECOND_OPTION}" --secret=:soccer: --limit=3'
        },
        MagicMock(),
    )
    assert cmd is None


def test_limit_non_numeric():
    cmd = get_command_from_req(
        {
            "text": f'"{QUESTION}" "{FIRST_OPTION}" :some-emoji: "{SECOND_OPTION}" --secret=:soccer: --limit=a'
        },
        MagicMock(),
    )
    assert cmd is None


def test_limit_negative():
    cmd = get_command_from_req(
        {
            "text": f'"{QUESTION}" "{FIRST_OPTION}" :some-emoji: "{SECOND_OPTION}" --secret=:soccer: --limit=-1'
        },
        MagicMock(),
    )
    assert cmd is None


def test_limit_zero():
    cmd = get_command_from_req(
        {
            "text": f'"{QUESTION}" "{FIRST_OPTION}" :some-emoji: "{SECOND_OPTION}" --secret=:soccer: --limit=0'
        },
        MagicMock(),
    )
    assert cmd is None
