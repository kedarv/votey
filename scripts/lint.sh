#!/usr/bin/env bash

set -euxo pipefail

uv run ruff check .
uv run ruff format --check .
uv run mypy votey
