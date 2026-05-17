.PHONY: install-hooks
install-hooks:
	uv run pre-commit install --install-hooks

.PHONY: lint
lint:
	./scripts/lint.sh

.PHONY: pre-commit
pre-commit:
	uv run pre-commit run --all-files

.PHONY: start
start:
	uv run python run.py

.PHONY: format
format:
	uv run ruff format .
	uv run ruff check --fix .

.PHONY: test
test:
	uv run pytest
