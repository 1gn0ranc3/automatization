import time
from uuid import uuid4

import pytest

from automation.telemetry.events import encode, make_event
from automation.telemetry.kafka import (
    consume,
    kafka_types,
    producer_for,
    publish_outbox,
    send_confirmed,
)
from automation.telemetry.storage import Outbox, Results

pytestmark = pytest.mark.kafka


@pytest.fixture
def broker_topics(request):
    # Запрошенная интеграция при отсутствии библиотеки/брокера падает, не превращается в skip.
    kafka_types()
    from confluent_kafka.admin import AdminClient, NewTopic

    bootstrap = request.config.getoption("--kafka-bootstrap")
    admin = AdminClient({"bootstrap.servers": bootstrap})
    token = uuid4().hex
    topics = [f"qa.test-results.it.{token}", f"qa.test-results.it.dlq.{token}"]
    try:
        futures = admin.create_topics(
            [NewTopic(topic, num_partitions=1, replication_factor=1) for topic in topics],
            request_timeout=10,
        )
        for future in futures.values():
            future.result(timeout=15)
        yield bootstrap, topics, f"qa-test-{token}"
    finally:
        # Удаляются только уникальные topics этого теста.
        for future in admin.delete_topics(topics, request_timeout=10).values():
            future.result(timeout=15)


def test_real_delivery_restart_duplicates_and_dlq(broker_topics, tmp_path, event):
    bootstrap, (topic, dlq), group = broker_topics
    producer = producer_for(bootstrap, 5)
    outbox = Outbox(tmp_path / "outbox.sqlite")
    outbox.append(event)
    assert publish_outbox(outbox, producer, topic)["pending"] == 0
    send_confirmed(producer, topic, event["test_id"], encode(event).encode())
    send_confirmed(producer, topic, "bad", b"not-json")
    other = make_event("run-2", event["test_id"], 1, "demoqa", "gw1", "failed", 50)
    send_confirmed(producer, topic, other["test_id"], encode(other).encode())
    path = tmp_path / "results.sqlite"
    first = consume(bootstrap, topic, dlq, group, Results(path), max_messages=1, idle_timeout=30)
    assert first == {"stored": 1, "duplicate": 0, "rejected": 0}
    # Новый consumer с той же group и новым объектом БД продолжает после offset.
    second = consume(bootstrap, topic, dlq, group, Results(path), max_messages=3, idle_timeout=30)
    assert second == {"stored": 1, "duplicate": 1, "rejected": 1}
    assert sum(row["attempts"] for row in Results(path).summary()) == 2
    _, consumer_type = kafka_types()
    reader = consumer_type(
        {
            "bootstrap.servers": bootstrap,
            "group.id": f"{group}-dlq",
            "auto.offset.reset": "earliest",
            "enable.auto.commit": False,
        }
    )
    try:
        reader.subscribe([dlq])
        deadline = time.monotonic() + 30
        received = None
        while received is None and time.monotonic() < deadline:
            received = reader.poll(0.5)
        assert received is not None, "DLQ message was not received"
        assert received.error() is None
        import json

        rejected = json.loads(received.value())
        assert rejected["event_type"] == "test.rejected"
        assert rejected["source"]["topic"] == topic
    finally:
        reader.close()
