import os
from collections.abc import Callable

from dotenv import load_dotenv

from votey import create_app
from votey.exts import db

load_dotenv()
app = create_app()

with app.app_context():
    db.create_all()

SLACK_MODE = os.getenv("SLACK_MODE", "http").lower()


def run_socket_mode() -> None:
    from slack_bolt.adapter.socket_mode import SocketModeHandler

    from votey.socket_mode import create_bolt_app

    app_token = os.environ["SLACK_APP_TOKEN"]
    signing_secret = os.getenv("SIGNING_SECRET", "")

    bolt_app = create_bolt_app(signing_secret)

    from slack_bolt.middleware import CustomMiddleware
    from slack_bolt.request import BoltRequest
    from slack_bolt.response import BoltResponse

    class FlaskAppContextMiddleware(CustomMiddleware):
        def name(self) -> str:
            return "FlaskAppContextMiddleware"

        def process(
            self,
            *,
            req: BoltRequest,
            resp: BoltResponse,
            next: Callable[[], BoltResponse],
        ) -> BoltResponse:
            with app.app_context():
                return next()

    bolt_app.middleware.insert(0, FlaskAppContextMiddleware())

    handler = SocketModeHandler(bolt_app, app_token)
    print("⚡ Votey socket mode connected")
    handler.start()


if __name__ == "__main__":
    if SLACK_MODE == "socket":
        run_socket_mode()
    elif SLACK_MODE == "http":
        app.run(host="127.0.0.1", port=5050, threaded=True)
    else:
        raise ValueError(
            f"Unknown SLACK_MODE={SLACK_MODE!r}. Use 'http' or 'socket'."
        )
