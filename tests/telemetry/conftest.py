import pytest

from automation.telemetry.events import make_event


def pytest_addoption(parser):
    parser.addoption(
        "--run-kafka", action="store_true", help="Запустить интеграцию с настоящей Kafka"
    )
    parser.addoption("--kafka-bootstrap", default="localhost:9092")


def pytest_collection_modifyitems(config, items):
    if config.getoption("--run-kafka"):
        return
    selected, excluded = [], []
    for item in items:
        (excluded if item.get_closest_marker("kafka") else selected).append(item)
    items[:] = selected
    if excluded:
        config.hook.pytest_deselected(items=excluded)


@pytest.fixture
def event():
    return make_event(
        "run-1", "tests/ui/test_example.py::test_page", 1, "demoqa", "gw0", "passed", 12
    )
