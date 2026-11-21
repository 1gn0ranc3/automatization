COMMENT_TOKEN := \#
ifneq ($(filter $(COMMENT_TOKEN),$(MAKECMDGOALS)),)
$(error Комментарий попал в аргументы Make. Скопируйте команду без символа решётки и пояснения или выполните setopt interactivecomments в zsh. Тесты не запускались)
endif

PYTHON ?= .venv/bin/python
PYTEST_ARGS ?=
TARGET ?= external
WORKERS ?= 0
TEST_EVENTS ?= false
SELENOID_MARKERS ?= selenoid
SELENOID_COMPOSE = docker compose -f compose.selenoid.yml
RUN_ID ?= $(shell date +%Y%m%d-%H%M%S)-$(shell $(PYTHON) -c 'from uuid import uuid4; print(uuid4().hex[:8])')
RUN_ID := $(RUN_ID)
ARTIFACTS ?= artifacts/$(RUN_ID)
EVENT_FLAGS = $(if $(filter true,$(TEST_EVENTS)),--test-events) --events-db="$(ARTIFACTS)/outbox.sqlite"
SITE_TESTS = $(PYTHON) -m pytest tests/sites -n $(WORKERS) --dist=loadfile \
	$(EVENT_FLAGS) --alluredir="$(ARTIFACTS)/allure-results/$@" \
	--tracing=retain-on-failure --screenshot=only-on-failure

.PHONY: help check verify doctor lint format collect unit-tests telemetry-tests integration-tests smoke test regression-rest api ui kafka-up kafka-init kafka-consume kafka-tests
.DEFAULT_GOAL := help
.PHONY: selenoid-up selenoid-down selenoid-tests selenoid-docker

help:
	@echo 'check              Lint, environment, local tests, collection (no network/browser)'
	@echo 'verify             check + real local HTTP and Chromium tests'
	@echo 'doctor             Environment diagnostics; PYTEST_ARGS is not used'
	@echo 'smoke / test       Public-site smoke / full regression'
	@echo 'api / ui           Public-site API / UI; TARGET=demoqa|reqres|fakestore|external'
	@echo 'integration-tests  Local HTTP and browser integration; fails if unavailable'
	@echo 'kafka-tests        Real Kafka integration; requires running broker'
	@echo 'selenoid-up/down   Start/stop the remote Chrome pool'
	@echo 'selenoid-tests     Selenium tests against a running Selenoid'
	@echo 'selenoid-docker    Build, run and clean up the complete Selenoid stack'
	@echo 'format             Format Python source'

check: lint doctor unit-tests telemetry-tests collect

verify: check integration-tests

doctor:
	$(PYTHON) -m automation.doctor --artifacts="$(ARTIFACTS)"
	$(PYTHON) -m pip check

lint:
	$(PYTHON) -m ruff check .
	$(PYTHON) -m ruff format --check automation tests conftest.py

format:
	$(PYTHON) -m ruff format automation tests conftest.py

collect:
	$(PYTHON) -m pytest tests/sites tests/integration tests/selenoid --collect-only -q

unit-tests:
	$(PYTHON) -m pytest tests/unit -q --junitxml="$(ARTIFACTS)/unit.xml" $(PYTEST_ARGS)

telemetry-tests:
	$(PYTHON) -m pytest tests/telemetry -m telemetry -q --junitxml="$(ARTIFACTS)/telemetry.xml" $(PYTEST_ARGS)

integration-tests:
	$(PYTHON) -m pytest tests/integration -q --junitxml="$(ARTIFACTS)/integration.xml" \
		--alluredir="$(ARTIFACTS)/allure-results/integration" \
		--tracing=retain-on-failure --screenshot=only-on-failure \
		--output="$(ARTIFACTS)/playwright-integration" $(PYTEST_ARGS)

smoke: MARKERS = smoke
test: MARKERS = regression
regression-rest: MARKERS = regression and not smoke
api: MARKERS = api
ui: MARKERS = ui

smoke test regression-rest api ui:
	$(SITE_TESTS) -m '($(MARKERS)) and $(TARGET)' \
		--junitxml="$(ARTIFACTS)/$@.xml" --output="$(ARTIFACTS)/playwright-$@" $(PYTEST_ARGS)

kafka-up:
	docker compose -f compose.kafka.yml up -d --wait

kafka-init:
	$(PYTHON) -m automation.telemetry init

kafka-consume:
	$(PYTHON) -m automation.telemetry consume

kafka-tests:
	$(PYTHON) -m pytest tests/telemetry -m kafka --run-kafka -q \
		--junitxml="$(ARTIFACTS)/kafka.xml" $(PYTEST_ARGS)

selenoid-up:
	$(SELENOID_COMPOSE) --profile images pull chrome-image
	$(SELENOID_COMPOSE) up -d --build --wait selenoid

selenoid-down:
	$(SELENOID_COMPOSE) down --timeout 15

selenoid-tests:
	$(PYTHON) -m pytest tests/selenoid -m '$(SELENOID_MARKERS)' -n $(WORKERS) \
		$(EVENT_FLAGS) --junitxml="$(ARTIFACTS)/selenoid.xml" \
		--alluredir="$(ARTIFACTS)/allure-results/selenoid" $(PYTEST_ARGS)

selenoid-docker:
	ARTIFACTS="$(abspath $(ARTIFACTS))" WORKERS="$(WORKERS)" TEST_EVENTS="$(TEST_EVENTS)" \
		SELENOID_MARKERS='$(SELENOID_MARKERS)' sh infra/selenoid/run.sh
