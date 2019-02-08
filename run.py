import os

from votey import create_app
from votey import db

os.environ['FLASK_ENV'] = 'development'
app = create_app()

with app.app_context():
  db.create_all()

if __name__ == "__main__":
  app.run(host='0.0.0.0', port=5050, debug=True, threaded=True)
