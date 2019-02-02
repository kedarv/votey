import os

from votey import create_app

os.environ['FLASK_ENV'] = 'development'
create_app().run(host='0.0.0.0', port=5050, debug=True, threaded=True)
