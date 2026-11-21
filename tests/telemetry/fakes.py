from types import SimpleNamespace


class ProducerDouble:
    """Только для проверки отказов приложения; не эмулирует протокол Kafka."""

    def __init__(self, delivery="ack"):
        self.delivery = delivery
        self.sent = []
        self.callbacks = []

    def produce(self, topic, key, value, on_delivery):
        self.sent.append((topic, key, value))
        self.callbacks.append(on_delivery)

    def poll(self, timeout):
        return 0

    def flush(self, timeout):
        if self.delivery == "timeout":
            return len(self.callbacks)
        callbacks, self.callbacks = self.callbacks, []
        for callback in callbacks:
            callback(None if self.delivery == "ack" else "broker error", None)
        return 0


class ConsumerDouble:
    def __init__(self, fail_commit=False):
        self.commits = []
        self.fail_commit = fail_commit

    def commit(self, message, asynchronous):
        assert asynchronous is False
        if self.fail_commit:
            raise RuntimeError("simulated crash before offset commit")
        self.commits.append(message.offset())


def message(raw, offset=0):
    return SimpleNamespace(
        value=lambda: raw,
        topic=lambda: "results",
        partition=lambda: 0,
        offset=lambda: offset,
        error=lambda: None,
    )
