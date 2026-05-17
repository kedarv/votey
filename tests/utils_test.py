from votey.utils import get_footer
from votey.utils import normalize_database_url


def test_normalize_postgres_url():
    assert (
        normalize_database_url("postgres://user:pass@localhost:5432/votey")
        == "postgresql+psycopg2://user:pass@localhost:5432/votey"
    )


def test_normalize_sqlite_url_unchanged():
    assert (
        normalize_database_url("sqlite:///data/votey.db") == "sqlite:///data/votey.db"
    )


def test_default_footer():
    assert (
        get_footer("userid", False, False, None)
        == "Poll created by <@userid> with /votey"
    )


def test_secret_footer():
    assert (
        get_footer("userid", False, True, None) == "Poll creator and votes are hidden"
    )


def test_anonymous_footer():
    assert (
        get_footer("userid", True, False, None)
        == "Anonymous poll created by <@userid> with /votey"
    )


def test_default_footer_limit():
    assert (
        get_footer("userid", False, False, 1)
        == "Poll created by <@userid> with /votey. (Pick up to 1 option)"
    )


def test_secret_footer_limit():
    assert (
        get_footer("userid", False, True, 2)
        == "Poll creator and votes are hidden. (Pick up to 2 options)"
    )


def test_anonymous_footer_limit():
    assert (
        get_footer("userid", True, False, 2)
        == "Anonymous poll created by <@userid> with /votey. (Pick up to 2 options)"
    )
