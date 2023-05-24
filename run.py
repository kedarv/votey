from threading import Lock

from votey import create_app
from votey.exts import db
from dotenv import load_dotenv

load_dotenv('.env')
app = create_app()
lock = Lock()

with app.app_context(), lock:
    db.create_all()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5050, threaded=True)
