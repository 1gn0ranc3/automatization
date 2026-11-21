import base64
import hashlib
import json
import math
import time

from automation.telemetry.events import InvalidEvent, decode, encode


def validate_timeout(timeout):
    if type(timeout) not in (int, float) or not math.isfinite(timeout) or not 0 < timeout <= 30:
        raise ValueError("timeout must be between 0 and 30 seconds")


def kafka_types():
    try:
        from confluent_kafka import Consumer, Producer
    except ImportError:
        raise RuntimeError("Установите опцию: pip install -r requirements-kafka.txt") from None
    return Producer, Consumer


def producer_for(bootstrap, timeout):
    validate_timeout(timeout)
    producer_type, _ = kafka_types()
    return producer_type(
        {
            "bootstrap.servers": bootstrap,
            "enable.idempotence": True,
            "message.timeout.ms": max(1000, int(timeout * 1000)),
            "socket.timeout.ms": 1000,
            "socket.connection.setup.timeout.ms": 1000,
            "log_level": 0,
        }
    )


def publish_outbox(outbox, producer, topic, timeout=5, run_id=None):
    """Удалённое подтверждение — единственная причина отметить событие доставленным."""
    validate_timeout(timeout)
    deadline = time.monotonic() + timeout
    errors = 0

    def callback(event_id):
        def delivered(error, message):
            nonlocal errors
            if error is not None:
                errors += 1
                return
            if time.monotonic() >= deadline:
                errors += 1
                return
            try:
                outbox.mark_delivered(event_id)
            except Exception:
                # Повтор допустим; при ошибке записи локальный статус не меняется.
                errors += 1

        return delivered

    for event in outbox.iter_pending(run_id):
        while time.monotonic() < deadline:
            try:
                producer.produce(
                    topic,
                    key=f"{event['run_id']}:{event['test_id']}",
                    value=encode(event).encode(),
                    on_delivery=callback(event["event_id"]),
                )
                producer.poll(0)
                break
            except BufferError:
                producer.poll(min(0.05, max(0, deadline - time.monotonic())))
        else:
            break
    producer.flush(max(0, deadline - time.monotonic()))
    return {**outbox.counts(run_id), "delivery_errors": errors}


def send_confirmed(producer, topic, key, payload, timeout=5):
    validate_timeout(timeout)
    deadline = time.monotonic() + timeout
    result = []
    while time.monotonic() < deadline:
        try:
            producer.produce(
                topic,
                key=key,
                value=payload,
                on_delivery=lambda error, message: result.append((error, time.monotonic())),
            )
            break
        except BufferError:
            producer.poll(min(0.05, max(0, deadline - time.monotonic())))
    producer.flush(max(0, deadline - time.monotonic()))
    if len(result) != 1 or result[0][0] is not None or result[0][1] >= deadline:
        raise RuntimeError("Kafka did not acknowledge message; offset was not committed")


def rejection(message, reason):
    raw = message.value() or b""
    return json.dumps(
        {
            "schema_version": 1,
            "event_type": "test.rejected",
            "reason": str(reason),
            "source": {
                "topic": message.topic(),
                "partition": message.partition(),
                "offset": message.offset(),
            },
            "sha256": hashlib.sha256(raw).hexdigest(),
            "size_bytes": len(raw),
            "value_base64": base64.b64encode(raw[:16384]).decode(),
            "truncated": len(raw) > 16384,
        },
        sort_keys=True,
    ).encode()


def process_message(message, consumer, results, dlq_producer, dlq_topic, timeout=5):
    if message.error():
        raise RuntimeError(f"Kafka consume error: {message.error()}")
    try:
        event = decode(message.value())
        outcome = "stored" if results.record(event) else "duplicate"
    except InvalidEvent as exc:
        key = f"{message.topic()}:{message.partition()}:{message.offset()}"
        send_confirmed(dlq_producer, dlq_topic, key, rejection(message, exc), timeout)
        outcome = "rejected"
    # Если commit не прошёл, запись будет прочитана ещё раз. Results распознает дубль.
    consumer.commit(message=message, asynchronous=False)
    return outcome


def consume(bootstrap, topic, dlq_topic, group, results, max_messages=0, idle_timeout=0):
    if topic == dlq_topic:
        raise ValueError("Source and DLQ topics must differ")
    if type(max_messages) is not int or max_messages < 0:
        raise ValueError("max_messages must be a non-negative integer")
    if idle_timeout != 0:
        validate_timeout(idle_timeout)
    _, consumer_type = kafka_types()
    consumer = consumer_type(
        {
            "bootstrap.servers": bootstrap,
            "group.id": group,
            "auto.offset.reset": "earliest",
            "enable.auto.commit": False,
            "enable.auto.offset.store": False,
            "log_level": 0,
        }
    )
    counts = {"stored": 0, "duplicate": 0, "rejected": 0}
    last_message = time.monotonic()
    try:
        producer = producer_for(bootstrap, 5)
        consumer.subscribe([topic])
        while not max_messages or sum(counts.values()) < max_messages:
            message = consumer.poll(0.5)
            if message is None:
                if idle_timeout and time.monotonic() - last_message >= idle_timeout:
                    raise TimeoutError("No Kafka messages before idle deadline")
                continue
            outcome = process_message(message, consumer, results, producer, dlq_topic)
            counts[outcome] += 1
            last_message = time.monotonic()
    finally:
        consumer.close()
    return counts
