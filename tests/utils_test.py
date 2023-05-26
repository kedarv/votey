from votey.utils import get_footer


def test_default_footer():
    assert "Poll created by <@userid> with /votey" == get_footer(
        "userid", False, False, None
    )


def test_secret_footer():
    assert "Poll creator and votes are hidden" == get_footer(
        "userid", False, True, None
    )


def test_anonymous_footer():
    assert "Anonymous poll created by <@userid> with /votey" == get_footer(
        "userid", True, False, None
    )


def test_default_footer_limit():
    assert "Poll created by <@userid> with /votey. (Pick up to 1 option)" == get_footer(
        "userid", False, False, 1
    )


def test_secret_footer_limit():
    assert "Poll creator and votes are hidden. (Pick up to 2 options)" == get_footer(
        "userid", False, True, 2
    )


def test_anonymous_footer_limit():
    assert (
        "Anonymous poll created by <@userid> with /votey. (Pick up to 2 options)"
        == get_footer("userid", True, False, 2)
    )
