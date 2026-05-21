from dotenv import load_dotenv

from votey import create_app
from votey.exts import db

load_dotenv()
app = create_app()

with app.app_context():
    db.create_all()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5050, threaded=True)
