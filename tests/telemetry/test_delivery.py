import json
from concurrent.futures import ThreadPoolExecutor

import pytest

from automation.telemetry.events import InvalidEvent, decode, encode
from automation.telemetry.kafka import process_message, publish_outbox
from automation.telemetry.storage import Outbox, Results
from tests.telemetry.fakes import ConsumerDouble, ProducerDouble, message

pytestmark = pytest.mark.telemetry


@pytest.mark.parametrize(
    "field,value",
    [
        ("schema_version", 2),
        ("schema_version", True),
        ("attempt", 0),
        ("duration_ms", float("nan")),
        ("duration_ms", -1),
        ("duration_ms", True),
        ("outcome", "green"),
        ("event_id", "wrong"),
        ("finished_at", "2026-11-11"),
    ],
)
def test_invalid_events_rejected(event, field, value):
    with pytest.raises(InvalidEvent):
        encode({**event, field: value})


@pytest.mark.parametrize("raw", [b"{", b"[]", b"null", b"\xff", None, b"x" * 65537])
def test_invalid_wire_value(raw):
    with pytest.raises(InvalidEvent):
        decode(raw)


@pytest.mark.parametrize("failure", ["timeout", "error"])
def test_unacknowledged_outbox_survives_restart_and_replays(tmp_path, event, failure):
    path = tmp_path / "outbox.sqlite"
    outbox = Outbox(path)
    outbox.append(event)
    first = ProducerDouble(failure)
    assert publish_outbox(outbox, first, "results")["pending"] == 1
    restarted = Outbox(path)
    second = ProducerDouble()
    assert publish_outbox(restarted, second, "results")["pending"] == 0
    assert first.sent[0] == second.sent[0]
    assert restarted.counts() == {"pending": 0, "delivered": 1}


def test_replay_after_offset_commit_failure_does_not_double_count(tmp_path, event):
    path = tmp_path / "results.sqlite"
    received = message(encode(event).encode())
    with pytest.raises(RuntimeError, match="before offset commit"):
        process_message(
            received, ConsumerDouble(fail_commit=True), Results(path), ProducerDouble(), "dlq"
        )
    consumer = ConsumerDouble()
    assert (
        process_message(received, consumer, Results(path), ProducerDouble(), "dlq") == "duplicate"
    )
    assert Results(path).summary()[0]["attempts"] == 1
    assert consumer.commits == [0]


def test_parallel_duplicate_processing_keeps_one_result(tmp_path, event):
    results = Results(tmp_path / "results.sqlite")
    with ThreadPoolExecutor(max_workers=2) as pool:
        inserted = list(pool.map(results.record, [event, event]))
    assert sorted(inserted) == [False, True]
    assert results.summary()[0]["attempts"] == 1


def test_poison_event_goes_to_dlq_before_commit(tmp_path):
    results, consumer, producer = (
        Results(tmp_path / "results.sqlite"),
        ConsumerDouble(),
        ProducerDouble(),
    )
    assert (
        process_message(message(b"not-json", 7), consumer, results, producer, "dlq") == "rejected"
    )
    assert consumer.commits == [7]
    envelope = json.loads(producer.sent[0][2])
    assert producer.sent[0][0] == "dlq"
    assert envelope["source"] == {"topic": "results", "partition": 0, "offset": 7}
    assert envelope["event_type"] == "test.rejected"
    assert results.summary() == []


def test_dlq_failure_does_not_commit_source(tmp_path):
    consumer = ConsumerDouble()
    with pytest.raises(RuntimeError, match="not acknowledged|not acknowledge"):
        process_message(
            message(b"bad"),
            consumer,
            Results(tmp_path / "results.sqlite"),
            ProducerDouble("timeout"),
            "dlq",
        )
    assert consumer.commits == []


def test_conflicting_duplicate_is_rejected_without_overwrite(tmp_path, event):
    results = Results(tmp_path / "results.sqlite")
    results.record(event)
    producer = ProducerDouble()
    conflict = {**event, "outcome": "failed"}
    assert (
        process_message(
            message(encode(conflict).encode()), ConsumerDouble(), results, producer, "dlq"
        )
        == "rejected"
    )
    assert results.summary()[0]["outcome"] == "passed"


def test_runs_and_attempts_are_counted_separately(tmp_path, event):
    from automation.telemetry.events import make_event

    results = Results(tmp_path / "results.sqlite")
    results.record(event)
    results.record(make_event("run-2", event["test_id"], 1, "demoqa", "gw0", "failed", 20))
    results.record(make_event("run-1", event["test_id"], 2, "demoqa", "gw1", "passed", 30))
    assert results.summary("run-1")[0]["attempts"] == 2
    assert results.summary("run-1")[0]["duration_ms"] == 42
    assert results.summary("run-2")[0]["attempts"] == 1


def test_parallel_outbox_writers_preserve_one_event(tmp_path, event):
    path = tmp_path / "outbox.sqlite"
    outboxes = [Outbox(path), Outbox(path)]
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda outbox: outbox.append(event), outboxes))
    assert Outbox(path).pending() == [event]


def test_conflicting_outbox_event_does_not_replace_delivered_payload(tmp_path, event):
    outbox = Outbox(tmp_path / "outbox.sqlite")
    outbox.append(event)
    outbox.mark_delivered(event["event_id"])
    with pytest.raises(InvalidEvent, match="conflicting outbox"):
        outbox.append({**event, "outcome": "failed"})
    outbox.append(event)
    assert outbox.counts() == {"pending": 0, "delivered": 1}
