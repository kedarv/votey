import pytest

from votey import create_app
from votey.exts import db


@pytest.fixture
def app(tmp_path):
    flask_app = create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'votey-test.db'}",
            "CLIENT_ID": "test-client-id",
            "CLIENT_SECRET": "test-client-secret",
            "SIGNING_SECRET": "test-signing-secret",
        }
    )
    with flask_app.app_context():
        db.create_all()
        try:
            yield flask_app
        finally:
            db.session.remove()
            db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()
