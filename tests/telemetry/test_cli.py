import json

import pytest

from automation.telemetry.__main__ import main
from automation.telemetry.storage import Outbox, Results

pytestmark = pytest.mark.telemetry


@pytest.mark.parametrize(
    "command,option", [("status", "--outbox"), ("summary", "--db"), ("publish", "--outbox")]
)
def test_missing_database_is_an_error_without_creating_files(tmp_path, capsys, command, option):
    path = tmp_path / "missing" / "data.sqlite"
    assert main([command, option, str(path)]) == 1
    assert not path.parent.exists()
    assert "OperationalError" in capsys.readouterr().err


def test_status_and_summary_read_existing_data(tmp_path, event, capsys):
    path = tmp_path / "queue ?#%.sqlite"
    Outbox(path).append(event)
    Results(path).record(event)
    assert main(["status", "--outbox", str(path), "--run-id", event["run_id"]]) == 0
    assert json.loads(capsys.readouterr().out) == {"pending": 1, "delivered": 0}
    assert main(["summary", "--db", str(path)]) == 0
    assert json.loads(capsys.readouterr().out)[0]["attempts"] == 1


def test_empty_existing_outbox_does_not_require_kafka(tmp_path, capsys):
    path = tmp_path / "outbox.sqlite"
    Outbox(path)
    assert main(["publish", "--outbox", str(path)]) == 0
    assert json.loads(capsys.readouterr().out)["pending"] == 0


@pytest.mark.parametrize("value", ["0", "-1", "nan", "inf", "31", "text"])
def test_invalid_timeout_is_usage_error(value):
    with pytest.raises(SystemExit) as caught:
        main(["publish", "--timeout", value])
    assert caught.value.code == 2


@pytest.mark.parametrize(
    "options", [["--topic", "same", "--dlq", "same"], ["--max-messages", "-1"]]
)
def test_invalid_consumer_options_do_not_create_database(tmp_path, options):
    path = tmp_path / "results.sqlite"
    with pytest.raises(SystemExit) as caught:
        main(["consume", "--db", str(path), *options])
    assert caught.value.code == 2
    assert not path.exists()
