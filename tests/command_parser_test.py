import pytest
from unittest.mock import MagicMock
from votey.slack import get_command_from_req
from votey.slack import ANON_KEYWORDS
from votey.slack import SECRET_KEYWORDS

QUESTION = "Some Question?"
FIRST_OPTION = "Some Option1"
SECOND_OPTION = "Some Option2"


def test_basic_command():
    poll_question, options, anonymous, secret, anon_secret_emoji = get_command_from_req(
        {"text": f'"{QUESTION}" "{FIRST_OPTION}" "{SECOND_OPTION}"'}, MagicMock()
    )
    assert poll_question == QUESTION
    assert options == [(FIRST_OPTION, None), (SECOND_OPTION, None)]
    assert anonymous == False
    assert secret == False

@pytest.mark.parametrize(
    "keyword",
    SECRET_KEYWORDS,
)
def test_secret(keyword):
    poll_question, options, anonymous, secret, anon_secret_emoji = get_command_from_req(
        {"text": f'"{QUESTION}" "{FIRST_OPTION}" "{SECOND_OPTION}" {keyword}'},
        MagicMock(),
    )
    assert anonymous == True
    assert secret == True

@pytest.mark.parametrize(
    "keyword",
    ANON_KEYWORDS,
)
def test_anonymous(keyword):
    poll_question, options, anonymous, secret, anon_secret_emoji = get_command_from_req(
        {"text": f'"{QUESTION}" "{FIRST_OPTION}" "{SECOND_OPTION}" {keyword}'},
        MagicMock(),
    )

    assert anonymous == True
    assert secret == False

def test_emoji_option_command():
    poll_question, options, anonymous, secret, anon_secret_emoji = get_command_from_req(
        {"text": f'"{QUESTION}" "{FIRST_OPTION}" :someemoji1: "{SECOND_OPTION}" :someemoji2:'}, MagicMock()
    )
    assert poll_question == QUESTION
    assert options == [(FIRST_OPTION, ":someemoji1:"), (SECOND_OPTION, ":someemoji2:")]
    assert anonymous == False
    assert secret == False    

def test_emoji_option_command_without_last_option():
    poll_question, options, anonymous, secret, anon_secret_emoji = get_command_from_req(
        {"text": f'"{QUESTION}" "{FIRST_OPTION}" :someemoji1: "{SECOND_OPTION}"'}, MagicMock()
    )
    assert poll_question == QUESTION
    assert options == [(FIRST_OPTION, ":someemoji1:"), (SECOND_OPTION, None)]
    assert anonymous == False
    assert secret == False        

def test_emoji_option_command_without_first_option():
    poll_question, options, anonymous, secret, anon_secret_emoji = get_command_from_req(
        {"text": f'"{QUESTION}" "{FIRST_OPTION}" "{SECOND_OPTION}" :some-emoji:'}, MagicMock()
    )
    assert poll_question == QUESTION
    assert options == [(FIRST_OPTION, None), (SECOND_OPTION, ":some-emoji:")]
    assert anonymous == False
    assert secret == False

def test_emoji_option_command_with_secret():
    poll_question, options, anonymous, secret, anon_secret_emoji = get_command_from_req(
        {"text": f'"{QUESTION}" "{FIRST_OPTION}" "{SECOND_OPTION}" :some-emoji: --secret'}, MagicMock()
    )
    assert poll_question == QUESTION
    assert options == [(FIRST_OPTION, None), (SECOND_OPTION, ":some-emoji:")]
    assert anonymous == True
    assert secret == True         

def test_emoji_option_command_with_anonymous():
    poll_question, options, anonymous, secret, anon_secret_emoji = get_command_from_req(
        {"text": f'"{QUESTION}" "{FIRST_OPTION}" :some-emoji: "{SECOND_OPTION}" --anonymous'}, MagicMock()
    )
    assert poll_question == QUESTION
    assert options == [(FIRST_OPTION, ":some-emoji:"), (SECOND_OPTION, None)]
    assert anonymous == True
    assert secret == False      

def test_anonymous_with_voting_emoji():
    poll_question, options, anonymous, secret, anon_secret_emoji = get_command_from_req(
        {"text": f'"{QUESTION}" "{FIRST_OPTION}" :some-emoji: "{SECOND_OPTION}" --anonymous=:soccer:'}, MagicMock()
    )
    assert poll_question == QUESTION
    assert options == [(FIRST_OPTION, ":some-emoji:"), (SECOND_OPTION, None)]
    assert anonymous == True
    assert secret == False 
    assert anon_secret_emoji == ":soccer:"         

def test_secret_with_voting_emoji():
    poll_question, options, anonymous, secret, anon_secret_emoji = get_command_from_req(
        {"text": f'"{QUESTION}" "{FIRST_OPTION}" :some-emoji: "{SECOND_OPTION}" --secret=:soccer:'}, MagicMock()
    )
    assert poll_question == QUESTION
    assert options == [(FIRST_OPTION, ":some-emoji:"), (SECOND_OPTION, None)]
    assert anonymous == True
    assert secret == True 
    assert anon_secret_emoji == ":soccer:"             