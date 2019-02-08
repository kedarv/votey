clean-cache:
	find . -name '*.pyc' -delete
	find . -name '__pycache__' -delete
	rm -rf .mypy_cache/
	rm -rf .pytest_cache/
	rm -rf votey.egg-info

clean: clean-cache
	rm -rf venv/

venv:
	virtualenv -p python3 venv
	venv/bin/pip install -rrequirements-bootstrap.txt

pipenv: | venv
	venv/bin/pipenv install -d

run: | venv
	venv/bin/pipenv run python run.py

lint: | venv
	venv/bin/pipenv run mypy --ignore-missing-imports votey --strict
	venv/bin/pipenv run prospector -A
