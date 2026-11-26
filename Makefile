# GNU make >= 4.0. Префикс рецептов '>' вместо табуляции.
.RECIPEPREFIX := >
.DEFAULT_GOAL := help
SHELL := /bin/bash

COMPOSE := docker compose -f compose.yml -f compose.dev-lite.yml
AS_USER := --user $(shell id -u):$(shell id -g)
PY      := $(COMPOSE) exec -T web python
PYU     := $(COMPOSE) exec -T $(AS_USER) web python
PYTHON  ?= .venv/bin/python

.PHONY: help env certs staging-up staging-down staging-reset staging-status staging-logs backup restore-check assets lock build up down restart ps logs migrate makemigrations \
        superuser shell psql test test-fresh e2e js-check js-test probe-seed undercover-seed coverage lint fmt types check dump clean clean-caches precommit-install

help:
> @grep -E '^[a-z-]+:' Makefile | sed 's/:.*//' | sort

env:
> @bash infra/scripts/gen_dev_env.sh

certs:
> @bash infra/scripts/mkcert.sh

assets:
> npm install --no-audit --no-fund
> npm run build

lock:
> uv lock

build:
> $(COMPOSE) build

up:
> $(COMPOSE) --profile beat up -d
> @echo "https://portal.test:8443/healthz"

down:
> $(COMPOSE) down

restart:
> $(COMPOSE) restart web worker

ps:
> $(COMPOSE) ps

logs:
> $(COMPOSE) logs -f --tail=100 web worker nginx

makemigrations:
> $(PYU) manage.py makemigrations

migrate:
> $(PY) manage.py migrate --noinput

superuser:
> $(COMPOSE) exec web python manage.py createsuperuser

shell:
> $(COMPOSE) exec web python manage.py shell

psql:
> $(COMPOSE) exec db psql -U ba -d ba

test:
> $(PYU) -m pytest

test-fresh:
> $(PYU) -m pytest --create-db

e2e:
> BA_E2E=1 BA_E2E_BASE_URL=$${BA_E2E_BASE_URL:-https://portal.test:8443} \
>   $(PYTHON) -m pytest tests/e2e -m e2e

js-check:
> npm run check:js

js-test:
> npm run test:js

probe-seed:
> $(PY) manage.py probe_seed
> $(PY) manage.py collectstatic --noinput
> $(COMPOSE) exec -T web chmod -R u+rwX,g+rX,o+rX /app/staticfiles
> $(COMPOSE) exec -T -u 10001:10001 -e BA_RUNTIME_ROOT=/app/runtime web python scripts/publish_probe.py

undercover-seed:
> $(COMPOSE) exec -T web sh -c 'python games-src/whos_undercover/pack.py --output /tmp/whos_undercover-1.0.1.zip'
> $(PY) manage.py seed_dev_game /tmp/whos_undercover-1.0.1.zip --genre casual --genre-name-en Casual --genre-name-ru Казуальные

coverage:
> $(PYU) -m pytest --cov=apps --cov-report=term-missing

lint:
> $(PYU) -m ruff check apps config tests devcontrol
> $(PYU) -m ruff format --check apps config tests devcontrol

fmt:
> $(PYU) -m ruff check --fix apps config tests devcontrol
> $(PYU) -m ruff format apps config tests devcontrol

types:
> $(PYU) -m mypy

check: lint types test

backup:
> $(COMPOSE) --profile backup run --rm backup

restore-check:
> $(COMPOSE) --profile restore-check run --rm restore-check

staging-up:
> @./infra/scripts/staging.sh up

staging-down:
> @./infra/scripts/staging.sh down

staging-reset:
> @./infra/scripts/staging.sh reset

staging-status:
> @./infra/scripts/staging.sh status

staging-logs:
> @./infra/scripts/staging.sh logs

dump:
> @bash scripts/collect_project.sh

clean-caches:
> rm -rf .pytest_cache .ruff_cache .mypy_cache .coverage htmlcov \
>   test-results playwright-report static/dist

precommit-install:
> $(PYTHON) -m pre_commit install

clean:
> $(COMPOSE) down --remove-orphans
> rm -rf static/dist .pytest_cache .ruff_cache .mypy_cache
