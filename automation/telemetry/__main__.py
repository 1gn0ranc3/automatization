import argparse
import json
import sys

from automation.telemetry.kafka import consume, producer_for, publish_outbox
from automation.telemetry.storage import Outbox, Results


def positive(value):
    number = float(value)
    if not 0 < number <= 30:
        raise argparse.ArgumentTypeError("Нужен timeout 0..30 секунд")
    return number


def main(argv=None):
    parser = argparse.ArgumentParser(description="Kafka telemetry для результатов автотестов")
    commands = parser.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init", help="Создать result/DLQ topics, без удаления существующих")
    publish = commands.add_parser(
        "publish", help="Повторить отправку неподтверждённых событий outbox"
    )
    consumer = commands.add_parser("consume", help="Сохранить результаты, обработать дубли и DLQ")
    for cmd in (init, publish, consumer):
        cmd.add_argument("--bootstrap", default="localhost:9092")
        cmd.add_argument("--topic", default="qa.test-results.v1")
    for cmd in (init, consumer):
        cmd.add_argument("--dlq", default="qa.test-results.dlq.v1")
    publish.add_argument("--outbox", default="artifacts/telemetry/outbox.sqlite")
    publish.add_argument("--run-id")
    publish.add_argument("--timeout", type=positive, default=5)
    consumer.add_argument("--db", default="artifacts/telemetry/results.sqlite")
    consumer.add_argument("--group", default="qa-results-v1")
    consumer.add_argument("--max-messages", type=int, default=0)
    consumer.add_argument("--idle-timeout", type=positive, default=0)
    summary = commands.add_parser("summary", help="Статистика по запуску/сайту/исходу")
    summary.add_argument("--db", default="artifacts/telemetry/results.sqlite")
    summary.add_argument("--run-id")
    status = commands.add_parser("status", help="Состояние локальной очереди, без Kafka")
    status.add_argument("--outbox", default="artifacts/telemetry/outbox.sqlite")
    status.add_argument("--run-id")
    args = parser.parse_args(argv)
    if args.command in {"init", "consume"} and args.topic == args.dlq:
        parser.error("Result и DLQ topics должны отличаться")
    if args.command == "consume" and args.max_messages < 0:
        parser.error("--max-messages должен быть >= 0")
    try:
        if args.command == "init":
            from automation.telemetry.kafka import kafka_types

            kafka_types()
            from confluent_kafka import KafkaError
            from confluent_kafka.admin import AdminClient, NewTopic

            admin = AdminClient({"bootstrap.servers": args.bootstrap})
            futures = admin.create_topics(
                [
                    NewTopic(name, num_partitions=3, replication_factor=1)
                    for name in (args.topic, args.dlq)
                ],
                request_timeout=10,
            )
            for name, future in futures.items():
                try:
                    future.result(timeout=15)
                except Exception as exc:
                    if (
                        not exc.args
                        or not hasattr(exc.args[0], "code")
                        or exc.args[0].code() != KafkaError.TOPIC_ALREADY_EXISTS
                    ):
                        raise
                print(f"Topic ready: {name}")
        elif args.command == "publish":
            outbox = Outbox(args.outbox, create=False)
            if not outbox.counts(args.run_id)["pending"]:
                print(json.dumps(outbox.counts(args.run_id)))
                return 0
            result = publish_outbox(
                outbox,
                producer_for(args.bootstrap, args.timeout),
                args.topic,
                args.timeout,
                args.run_id,
            )
            print(json.dumps(result))
            return 1 if result["pending"] or result["delivery_errors"] else 0
        elif args.command == "consume":
            result = consume(
                args.bootstrap,
                args.topic,
                args.dlq,
                args.group,
                Results(args.db),
                args.max_messages,
                args.idle_timeout,
            )
            print(json.dumps(result))
        elif args.command == "status":
            print(json.dumps(Outbox(args.outbox, readonly=True).counts(args.run_id)))
        else:
            print(
                json.dumps(
                    Results(args.db, readonly=True).summary(args.run_id),
                    ensure_ascii=False,
                    indent=2,
                )
            )
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        print(f"Telemetry: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
