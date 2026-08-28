import os

from dotenv import load_dotenv

from votey import create_app
from votey.exts import db
from votey.socket_mode import start_socket_mode

load_dotenv()
app = create_app()

with app.app_context():
    db.create_all()

if __name__ == "__main__":
    if app.config["SLACK_MODE"] == "socket":
        start_socket_mode(app)
    else:
        app.run(
            host=os.getenv("HOST", "127.0.0.1"),
            port=int(os.getenv("PORT", "5050")),
            threaded=True,
        )
