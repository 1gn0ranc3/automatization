import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

from automation.selenoid import browser_session


def test_remote_session_is_closed_after_success():
    driver = Mock()
    with browser_session(lambda: driver) as session:
        assert session is driver
        driver.quit.assert_not_called()
    driver.quit.assert_called_once()


def test_remote_session_is_closed_when_setup_fails():
    driver = Mock()
    driver.set_window_size.side_effect = RuntimeError("window failed")
    with pytest.raises(RuntimeError, match="window failed"):
        with browser_session(lambda: driver):
            pytest.fail("Setup failure must prevent the scenario")
    driver.quit.assert_called_once()


def test_quit_failure_preserves_original_exception():
    driver = Mock()
    driver.quit.side_effect = RuntimeError("quit failed")
    with pytest.warns(UserWarning, match="Selenoid"):
        with pytest.raises(AssertionError, match="scenario failed"):
            with browser_session(lambda: driver):
                raise AssertionError("scenario failed")
    driver.quit.assert_called_once()


def test_quit_failure_is_not_hidden_after_success():
    driver = Mock()
    driver.quit.side_effect = RuntimeError("quit failed")
    with pytest.raises(RuntimeError, match="quit failed"):
        with browser_session(lambda: driver):
            pass


@pytest.mark.parametrize(
    "failure,expected", [("pull", 7), ("run", 7), ("down", 1), ("run,down", 7), ("none", 0)]
)
def test_docker_runner_preserves_exit_status_and_cleans_own_sessions(tmp_path, failure, expected):
    docker = tmp_path / "docker"
    docker.write_text(
        f"#!{sys.executable}\n"
        + """import json
import os
import sys
from pathlib import Path
args = sys.argv[1:]
with Path(os.environ["CALLS"]).open("a") as output:
    output.write(json.dumps(args) + "\\n")
if any(stage in args for stage in os.environ["FAIL_STAGE"].split(",")):
    sys.exit(7)
if args[:2] == ["ps", "-aq"]:
    print("abc123")
"""
    )
    docker.chmod(0o755)
    calls_path = tmp_path / "calls.jsonl"
    project = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        ["sh", str(project / "infra/selenoid/run.sh")],
        cwd=project,
        env={
            **os.environ,
            "PATH": str(tmp_path) + os.pathsep + os.environ["PATH"],
            "CALLS": str(calls_path),
            "FAIL_STAGE": failure,
            "ARTIFACTS": str(tmp_path / "reports"),
            "SELENOID_PROJECT": "isolated-test",
        },
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == expected, result.stdout + result.stderr
    calls = [json.loads(line) for line in calls_path.read_text().splitlines()]
    assert ["ps", "-aq", "--filter", "label=qa.selenoid.project=isolated-test"] in calls
    assert ["rm", "-f", "abc123"] in calls
    assert calls[-1] == ["compose", "-f", "compose.selenoid.yml", "down", "--timeout", "15"]
    if failure == "pull":
        assert not any("run" in call for call in calls)
    assert (tmp_path / "reports/selenoid.log").exists()
