import math
from collections import defaultdict
from uuid import uuid4

import pytest

from automation.telemetry.events import make_event
from automation.telemetry.storage import Outbox


def send_timeout(value):
    seconds = float(value)
    if not math.isfinite(seconds) or not 0 < seconds <= 30:
        raise ValueError("timeout must be between 0 and 30 seconds")
    return seconds


def pytest_addoption(parser):
    group = parser.getgroup("test event telemetry")
    group.addoption(
        "--test-events", action="store_true", help="Записывать результаты в локальный outbox"
    )
    group.addoption("--events-db", default="artifacts/telemetry/outbox.sqlite")
    group.addoption(
        "--events-run-id", default=None, help="По умолчанию новый UUID на каждый запуск"
    )
    group.addoption("--events-broker", default=None, help="Опционально: Kafka bootstrap servers")
    group.addoption("--events-topic", default="qa.test-results.v1")
    group.addoption("--events-timeout", type=send_timeout, default=5.0)


def pytest_configure(config):
    if config.getoption("--test-events") or config.getoption("--events-broker"):
        run_id = config.getoption("--events-run-id")
        if run_id is not None and (not run_id.strip() or len(run_id) > 128):
            raise pytest.UsageError("--events-run-id: от 1 до 128 символов")
        config.pluginmanager.register(Reporter(config), "qa-event-reporter")


class ReportCollector:
    """Один итог после teardown, а не три отдельных события setup/call/teardown."""

    def __init__(self, run_id):
        self.run_id = run_id
        self.pending = {}
        self.attempts = defaultdict(int)

    def accept(self, report):
        props = dict(getattr(report, "user_properties", []))
        gateway = getattr(getattr(report, "node", None), "gateway", None)
        worker = props.get("qa_worker", getattr(gateway, "id", "controller"))
        key = (report.nodeid, worker)
        emitted = []
        if report.when == "setup" and key in self.pending:
            # Например, новый запуск после незавершённой попытки плагина retries.
            emitted.append(self.complete(key, incomplete=True))
        if key not in self.pending:
            self.attempts[report.nodeid] += 1
            self.pending[key] = {
                "attempt": self.attempts[report.nodeid],
                "reports": [],
                "site": props.get("qa_site", "unknown"),
            }
        self.pending[key]["reports"].append(report)
        if report.when == "teardown":
            emitted.append(self.complete(key))
        return emitted

    def complete(self, key, incomplete=False):
        state = self.pending.pop(key)
        reports = state["reports"]
        if any(r.failed and r.when != "call" for r in reports):
            outcome = "error"
        elif any(r.failed or r.outcome == "rerun" for r in reports):
            outcome = "failed"
        elif incomplete:
            outcome = "interrupted"
        elif any(r.skipped for r in reports):
            outcome = (
                "xfailed" if any(getattr(r, "wasxfail", False) for r in reports) else "skipped"
            )
        elif any(getattr(r, "wasxfail", False) for r in reports):
            outcome = "xpassed"
        else:
            outcome = "passed"
        return make_event(
            self.run_id,
            key[0],
            state["attempt"],
            state["site"],
            key[1],
            outcome,
            sum(r.duration for r in reports) * 1000,
        )

    def finish(self):
        return [self.complete(key, incomplete=True) for key in list(self.pending)]


class Reporter:
    def __init__(self, config):
        self.config = config
        self.is_worker = hasattr(config, "workerinput")
        self.run_id = config.getoption("--events-run-id") or uuid4().hex
        self.collector = ReportCollector(self.run_id)
        self.errors = []
        self.outbox = None
        if not self.is_worker:
            try:
                self.outbox = Outbox(config.getoption("--events-db"))
            except Exception as exc:
                self.errors.append(
                    f"Outbox недоступен: {type(exc).__name__}; события не сохраняются"
                )

    @pytest.hookimpl(hookwrapper=True, tryfirst=True)
    def pytest_runtest_makereport(self, item, call):
        result = yield
        report = result.get_result()
        site = next(
            (s for s in ("demoqa", "reqres", "fakestore") if item.get_closest_marker(s)), "internal"
        )
        worker = getattr(self.config, "workerinput", {}).get("workerid", "controller")
        report.user_properties.extend([("qa_site", site), ("qa_worker", worker)])

    def save(self, events):
        for event in events:
            try:
                self.outbox.append(event)
            except Exception as exc:
                self.errors.append(f"Событие не сохранено: {type(exc).__name__}")

    def pytest_runtest_logreport(self, report):
        if not self.is_worker and self.outbox is not None:
            try:
                self.save(self.collector.accept(report))
            except Exception as exc:
                self.errors.append(f"Не удалось сформировать событие: {type(exc).__name__}")

    def pytest_sessionfinish(self, session, exitstatus):
        if self.is_worker or self.outbox is None:
            return
        try:
            self.save(self.collector.finish())
        except Exception as exc:
            self.errors.append(f"Не удалось завершить события: {type(exc).__name__}")
        bootstrap = self.config.getoption("--events-broker")
        if bootstrap:
            try:
                if not self.outbox.counts(self.run_id)["pending"]:
                    return
                from automation.telemetry.kafka import producer_for, publish_outbox

                timeout = self.config.getoption("--events-timeout")
                producer = producer_for(bootstrap, timeout)
                result = publish_outbox(
                    self.outbox,
                    producer,
                    self.config.getoption("--events-topic"),
                    timeout,
                    self.run_id,
                )
                if result["pending"] or result["delivery_errors"]:
                    self.errors.append("Часть доставок не подтверждена; события остаются в outbox")
            except Exception as exc:
                self.errors.append(
                    f"Kafka недоступна ({type(exc).__name__}); повтор: telemetry publish"
                )

    def pytest_terminal_summary(self, terminalreporter):
        if self.is_worker:
            return
        terminalreporter.write_sep("-", f"Test events · run_id={self.run_id}")
        if self.outbox is not None:
            try:
                terminalreporter.write_line(
                    f"{self.config.getoption('--events-db')}: {self.outbox.counts(self.run_id)}"
                )
            except Exception as exc:
                self.errors.append(f"Не удалось прочитать outbox: {type(exc).__name__}")
        for message in self.errors:
            terminalreporter.write_line(message, yellow=True)
