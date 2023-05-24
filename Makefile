.PHONY: format
format:
	black votey

.PHONY: install-hooks
install-hooks:
	pre-commit install --install-hooks

.PHONY: lint
lint:
	./scripts/lint.sh

.PHONY: pre-commit
pre-commit:
	pre-commit run --all-files

.PHONY: start
start:
	python run.py

.PHONY: test
test:
	pytest tests --cov=./