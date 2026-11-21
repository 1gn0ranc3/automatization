import json
import sqlite3
from types import SimpleNamespace

import pytest

from automation.telemetry import kafka
from automation.telemetry.events import InvalidEvent, decode, encode, make_event
from automation.telemetry.storage import Outbox
from tests.telemetry.fakes import ProducerDouble

pytestmark = pytest.mark.telemetry


@pytest.mark.parametrize("raw", [12, {}, b"", "я" * 40_000, b"[" * 1100 + b"]" * 1100, '"\ud800"'])
def test_bad_wire_values_are_schema_errors(raw):
    with pytest.raises(InvalidEvent):
        decode(raw)


def test_duplicate_json_fields_are_rejected(event):
    raw = encode(event)[:-1] + ', "outcome": "failed"}'
    with pytest.raises(InvalidEvent, match="duplicate"):
        decode(raw)


def test_utf16_without_bom_is_not_accepted_as_utf8(event):
    with pytest.raises(InvalidEvent):
        decode(encode(event).encode("utf-16-le"))


@pytest.mark.parametrize(
    "field,value", [("duration_ms", 10**400), ("attempt", 2**31), ("run_id", "\ud800")]
)
def test_extreme_values_are_schema_errors(event, field, value):
    with pytest.raises(InvalidEvent):
        encode({**event, field: value})


def test_escaped_surrogate_is_rejected(event):
    # worker_id не входит в event_id; JSON допустим, но Unicode payload — нет.
    event["worker_id"] = "\ud800"
    with pytest.raises(InvalidEvent):
        decode(json.dumps(event).encode())


def test_readonly_outbox_cannot_write(tmp_path, event):
    path = tmp_path / "data.sqlite"
    Outbox(path).append(event)
    readonly = Outbox(path, readonly=True)
    assert readonly.pending() == [event]
    with pytest.raises(sqlite3.OperationalError, match="readonly"):
        readonly.mark_delivered(event["event_id"])


def test_iterator_paginates_and_excludes_new_appends(tmp_path):
    outbox = Outbox(tmp_path / "outbox.sqlite")
    events = [make_event("run", str(i), 1, "internal", "controller", "passed", 1) for i in range(8)]
    for event in events[:7]:
        outbox.append(event)
    outbox.mark_delivered(events[1]["event_id"])
    iterator = outbox.iter_pending("run", batch_size=2)
    assert next(iterator) == events[0]
    outbox.append(events[7])
    assert list(iterator) == events[2:7]
    assert list(outbox.iter_pending("other")) == []


def test_publish_drains_more_than_ten_thousand_events(tmp_path, monkeypatch):
    outbox = Outbox(tmp_path / "outbox.sqlite")
    with outbox.connection() as db:
        for number in range(10_001):
            event = make_event("run", str(number), 1, "internal", "controller", "passed", 1)
            db.execute(
                "INSERT INTO outbox(event_id,run_id,payload) VALUES (?,?,?)",
                (event["event_id"], event["run_id"], encode(event)),
            )
    # Проверяем размер очереди независимо от скорости диска тестовой машины.
    monkeypatch.setattr(kafka, "time", SimpleNamespace(monotonic=lambda: 0))
    result = kafka.publish_outbox(outbox, ProducerDouble(), "results")
    assert result == {"pending": 0, "delivered": 10_001, "delivery_errors": 0}


def test_publish_scope_does_not_send_other_runs(tmp_path, event):
    outbox = Outbox(tmp_path / "outbox.sqlite")
    outbox.append(event)
    outbox.append(make_event("other", "test", 1, "internal", "controller", "passed", 1))
    producer = ProducerDouble()
    assert kafka.publish_outbox(outbox, producer, "results", run_id=event["run_id"])["pending"] == 0
    assert len(producer.sent) == 1
    assert outbox.counts() == {"pending": 1, "delivered": 1}


@pytest.mark.parametrize("operation", ["publish", "dlq"])
def test_full_producer_queue_obeys_deadline(tmp_path, event, monkeypatch, operation):
    now = [0.0]
    monkeypatch.setattr(kafka, "time", SimpleNamespace(monotonic=lambda: now[0]))

    class FullProducer(ProducerDouble):
        def produce(self, *args, **kwargs):
            raise BufferError("full")

        def poll(self, timeout):
            now[0] += timeout

    producer = FullProducer()
    if operation == "publish":
        outbox = Outbox(tmp_path / "outbox.sqlite")
        outbox.append(event)
        assert kafka.publish_outbox(outbox, producer, "topic", timeout=1)["pending"] == 1
    else:
        with pytest.raises(RuntimeError, match="not acknowledge"):
            kafka.send_confirmed(producer, "dlq", "key", b"value", timeout=1)
    assert now[0] == pytest.approx(1)


def test_dlq_retries_backpressure_without_duplicate_send():
    class BusyOnce(ProducerDouble):
        busy = True

        def produce(self, *args, **kwargs):
            if self.busy:
                self.busy = False
                raise BufferError("full")
            super().produce(*args, **kwargs)

    producer = BusyOnce()
    kafka.send_confirmed(producer, "dlq", "key", b"value")
    assert len(producer.sent) == 1


def test_late_ack_keeps_event_pending(tmp_path, event, monkeypatch):
    now = [0]
    monkeypatch.setattr(kafka, "time", SimpleNamespace(monotonic=lambda: now[0]))

    class LateProducer(ProducerDouble):
        def flush(self, timeout):
            now[0] = 6
            return super().flush(timeout)

    outbox = Outbox(tmp_path / "outbox.sqlite")
    outbox.append(event)
    assert kafka.publish_outbox(outbox, LateProducer(), "topic", timeout=5) == {
        "pending": 1,
        "delivered": 0,
        "delivery_errors": 1,
    }


def test_consumer_is_closed_if_producer_initialization_fails(monkeypatch):
    closed = []
    consumer = SimpleNamespace(close=lambda: closed.append(True))
    monkeypatch.setattr(kafka, "kafka_types", lambda: (None, lambda config: consumer))

    def failed_producer(*args):
        raise RuntimeError("producer creation failed")

    monkeypatch.setattr(kafka, "producer_for", failed_producer)
    with pytest.raises(RuntimeError, match="producer creation"):
        kafka.consume("localhost:9092", "results", "dlq", "group", None)
    assert closed == [True]
