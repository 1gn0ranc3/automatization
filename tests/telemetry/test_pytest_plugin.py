import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from automation.telemetry.pytest_plugin import ReportCollector
from automation.telemetry.storage import Outbox

pytestmark = pytest.mark.telemetry


def report(when, outcome="passed", nodeid="test_a.py::test_a", worker="gw0", xfail=False):
    return SimpleNamespace(
        when=when,
        outcome=outcome,
        nodeid=nodeid,
        duration=0.01,
        failed=outcome == "failed",
        skipped=outcome == "skipped",
        wasxfail=xfail,
        user_properties=[("qa_site", "demoqa"), ("qa_worker", worker)],
    )


@pytest.mark.parametrize(
    "phase,outcome,xfail,expected",
    [
        ("call", "passed", False, "passed"),
        ("call", "failed", False, "failed"),
        ("setup", "failed", False, "error"),
        ("teardown", "failed", False, "error"),
        ("setup", "skipped", False, "skipped"),
        ("call", "skipped", True, "xfailed"),
        ("call", "passed", True, "xpassed"),
    ],
)
def test_only_final_result_is_emitted(phase, outcome, xfail, expected):
    collector = ReportCollector("run")
    events = []
    for current in ("setup", "call", "teardown"):
        events += collector.accept(
            report(
                current, outcome if current == phase else "passed", xfail=xfail and current == phase
            )
        )
        if current != "teardown":
            assert events == []
    assert len(events) == 1
    assert events[0]["outcome"] == expected
    assert events[0]["duration_ms"] == 30


def test_interleaved_workers_and_interrupted_attempt():
    collector = ReportCollector("run")
    collector.accept(report("setup"))
    collector.accept(report("setup", nodeid="b", worker="gw1"))
    collector.accept(report("call", nodeid="b", worker="gw1"))
    finished = collector.accept(report("teardown", nodeid="b", worker="gw1"))
    interrupted = collector.finish()
    assert finished[0]["test_id"] == "b" and finished[0]["outcome"] == "passed"
    assert interrupted[0]["test_id"] != "b" and interrupted[0]["outcome"] == "interrupted"


def test_repeated_attempts_have_distinct_ids():
    collector = ReportCollector("run")
    events = []
    for _ in range(2):
        for phase in ("setup", "call", "teardown"):
            events.extend(collector.accept(report(phase)))
    assert [event["attempt"] for event in events] == [1, 2]
    assert events[0]["event_id"] != events[1]["event_id"]


@pytest.mark.parametrize("workers", [0, 2], ids=["serial", "xdist"])
def test_actual_pytest_reports_are_not_duplicated(tmp_path, workers):
    sample = tmp_path / "test_sample.py"
    sample.write_text("""import pytest
@pytest.mark.demoqa
def test_pass(): pass
def test_fail(): assert False
@pytest.mark.skip(reason="example")
def test_skip(): pass
@pytest.mark.xfail(reason="example")
def test_xfail(): assert False
@pytest.mark.xfail(reason="example")
def test_xpass(): pass
@pytest.fixture
def broken_setup(): raise RuntimeError("setup")
def test_setup(broken_setup): pass
@pytest.fixture
def broken_teardown():
    yield
    raise RuntimeError("teardown")
def test_teardown(broken_teardown): pass
""")
    ini = tmp_path / "pytest.ini"
    ini.write_text("[pytest]\nmarkers = demoqa: public site\n")
    outbox = tmp_path / "outbox.sqlite"
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "-c",
        str(ini),
        "--confcutdir",
        str(tmp_path),
        "-p",
        "automation.telemetry.pytest_plugin",
        str(sample),
        "--test-events",
        "--events-db",
        str(outbox),
        "--events-run-id",
        "subprocess-run",
        "-q",
        "--output",
        str(tmp_path / "playwright"),
    ]
    if workers:
        cmd.extend(["-n", str(workers)])
    env = dict(os.environ)
    env.pop("PYTEST_ADDOPTS", None)
    result = subprocess.run(
        cmd,
        cwd=Path(__file__).resolve().parents[2],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 1, result.stdout + result.stderr
    events = Outbox(outbox).pending()
    assert len(events) == 7, result.stdout
    assert sorted(e["outcome"] for e in events) == [
        "error",
        "error",
        "failed",
        "passed",
        "skipped",
        "xfailed",
        "xpassed",
    ]
    assert len({e["event_id"] for e in events}) == 7
    passed = next(e for e in events if e["outcome"] == "passed")
    assert passed["site"] == "demoqa"
    assert all(e["run_id"] == "subprocess-run" for e in events)
    if workers:
        assert all(e["worker_id"].startswith("gw") for e in events)
    else:
        assert all(e["worker_id"] == "controller" for e in events)
    assert all("longrepr" not in e and "password" not in e for e in events)


@pytest.mark.parametrize("mode", ["disabled", "bad-storage", "broker-failure", "unconfirmed"])
def test_telemetry_failure_does_not_change_test_exit_code(tmp_path, mode):
    sample = tmp_path / "test_pass.py"
    sample.write_text("def test_pass(): pass\n")
    ini = tmp_path / "pytest.ini"
    ini.write_text("[pytest]\n")
    (tmp_path / "conftest.py").write_text("""
def pytest_sessionstart(session):
    from automation.telemetry import kafka
    def unavailable(*args, **kwargs):
        raise RuntimeError("simulated unavailable broker")
    kafka.producer_for = unavailable
""")
    if mode == "unconfirmed":
        (tmp_path / "conftest.py").write_text("""
def pytest_sessionstart(session):
    from automation.telemetry import kafka
    from tests.telemetry.fakes import ProducerDouble
    kafka.producer_for = lambda *args: ProducerDouble("timeout")
""")
    outbox = tmp_path / "outbox.sqlite"
    if mode == "bad-storage":
        blocker = tmp_path / "not-a-directory"
        blocker.write_text("blocker")
        outbox = blocker / "outbox.sqlite"
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "-c",
        str(ini),
        "--confcutdir",
        str(tmp_path),
        "-p",
        "automation.telemetry.pytest_plugin",
        str(sample),
        "-q",
        "--events-db",
        str(outbox),
        "--output",
        str(tmp_path / "playwright"),
    ]
    if mode != "disabled":
        cmd.append("--test-events")
    if mode in {"broker-failure", "unconfirmed"}:
        cmd.extend(["--events-broker", "localhost:9092"])
    env = dict(os.environ)
    env.pop("PYTEST_ADDOPTS", None)
    result = subprocess.run(
        cmd,
        cwd=Path(__file__).resolve().parents[2],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    if mode in {"broker-failure", "unconfirmed"}:
        assert Outbox(outbox).counts() == {"pending": 1, "delivered": 0}
        expected = "Kafka недоступна" if mode == "broker-failure" else "доставок не подтверждена"
        assert expected in result.stdout
    elif mode == "disabled":
        assert not outbox.exists()
        assert "Test events" not in result.stdout
    else:
        assert "Outbox недоступен" in result.stdout
