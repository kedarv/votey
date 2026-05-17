import uuid

from sqlalchemy import event

from votey.exts import db
from votey.models import Option
from votey.models import Poll
from votey.models import Vote
from votey.slack import generate_poll_markup


def _make_poll(num_options=3, num_votes_per_option=2, anonymous=False):
    poll = Poll(
        identifier=uuid.uuid4(),
        question="What's for lunch?",
        channel="C123",
        anonymous=anonymous,
        secret=False,
        vote_emoji=None,
        author="U_AUTHOR",
        vote_limit=None,
    )
    db.session.add(poll)
    db.session.commit()

    options = [
        Option(poll_id=poll.id, option_text=f"option-{i}", option_emoji=None)
        for i in range(num_options)
    ]
    db.session.add_all(options)
    db.session.commit()

    for opt_index, option in enumerate(options):
        for vote_index in range(num_votes_per_option):
            db.session.add(
                Vote(
                    poll_id=poll.id,
                    option_id=option.id,
                    user=f"U_{opt_index}_{vote_index}",
                )
            )
    db.session.commit()
    return poll


def test_generate_poll_markup_returns_empty_for_unknown_poll(app):
    assert generate_poll_markup(poll_id=99999) == []


def test_generate_poll_markup_renders_options_and_vote_counts(app):
    poll = _make_poll(num_options=3, num_votes_per_option=2)

    attachments = generate_poll_markup(poll_id=poll.id)

    header = attachments[0]
    assert header["text"] == poll.question
    fields = header["fields"]
    assert len(fields) == 3
    for index, field in enumerate(fields):
        assert f"option-{index}" in field["value"]
        assert "`2`" in field["value"]


def test_generate_poll_markup_batches_action_buttons_in_groups_of_five(app):
    poll = _make_poll(num_options=7, num_votes_per_option=0)

    attachments = generate_poll_markup(poll_id=poll.id)

    action_attachments = attachments[1:]
    assert [len(a["actions"]) for a in action_attachments] == [5, 2]


def test_generate_poll_markup_avoids_n_plus_one_queries(app):
    poll = _make_poll(num_options=10, num_votes_per_option=3)
    poll_id = poll.id
    db.session.expire_all()

    statements = []

    def before_cursor_execute(
        conn, cursor, statement, parameters, context, executemany
    ):
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(statement)

    event.listen(db.engine, "before_cursor_execute", before_cursor_execute)
    try:
        generate_poll_markup(poll_id=poll_id)
    finally:
        event.remove(db.engine, "before_cursor_execute", before_cursor_execute)

    assert len(statements) <= 3, (
        f"generate_poll_markup issued {len(statements)} SELECTs; "
        f"expected <= 3 (poll, selectinload options, selectinload votes). "
        f"Statements: {statements}"
    )
