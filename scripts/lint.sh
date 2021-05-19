#!/usr/bin/env bash

# make bash handle errors more sensibly
set -euxo pipefail

mypy votey
prospector -A
pipenv check