import json
import math
from datetime import datetime, timezone
from uuid import NAMESPACE_URL, uuid5

OUTCOMES = {"passed", "failed", "error", "skipped", "xfailed", "xpassed", "interrupted"}
SITES = {"demoqa", "reqres", "fakestore", "internal", "unknown"}
FIELDS = {
    "schema_version",
    "event_type",
    "event_id",
    "run_id",
    "test_id",
    "attempt",
    "site",
    "worker_id",
    "outcome",
    "duration_ms",
    "finished_at",
}
MAX_EVENT_BYTES = 65_536


class InvalidEvent(ValueError):
    pass


def event_id(run_id, test_id, attempt):
    identity = json.dumps([run_id, test_id, attempt], ensure_ascii=False)
    try:
        return str(uuid5(NAMESPACE_URL, identity))
    except UnicodeError:
        raise InvalidEvent("invalid Unicode in event identity") from None


def validate(event):
    if not isinstance(event, dict) or set(event) != FIELDS:
        raise InvalidEvent("event fields do not match schema v1")
    if type(event["schema_version"]) is not int or event["schema_version"] != 1:
        raise InvalidEvent("unsupported schema_version")
    if event["event_type"] != "test.finished":
        raise InvalidEvent("unsupported event_type")
    for name, limit in [("run_id", 128), ("test_id", 4096), ("worker_id", 128)]:
        if not isinstance(event[name], str) or not event[name].strip() or len(event[name]) > limit:
            raise InvalidEvent(f"invalid {name}")
    if type(event["attempt"]) is not int or not 1 <= event["attempt"] <= 2**31 - 1:
        raise InvalidEvent("attempt must be a positive 32-bit integer")
    if event["event_id"] != event_id(event["run_id"], event["test_id"], event["attempt"]):
        raise InvalidEvent("event_id does not match run/test/attempt")
    if not isinstance(event["site"], str) or event["site"] not in SITES:
        raise InvalidEvent("invalid site")
    if not isinstance(event["outcome"], str) or event["outcome"] not in OUTCOMES:
        raise InvalidEvent("invalid outcome")
    duration = event["duration_ms"]
    try:
        valid_duration = (
            type(duration) in (int, float) and math.isfinite(duration) and duration >= 0
        )
    except OverflowError:
        valid_duration = False
    if not valid_duration:
        raise InvalidEvent("duration_ms must be finite and non-negative")
    try:
        timestamp = datetime.fromisoformat(event["finished_at"])
        if timestamp.tzinfo is None:
            raise ValueError
    except (ValueError, TypeError):
        raise InvalidEvent("finished_at must be an ISO timestamp with timezone") from None
    return event


def encode(event):
    payload = json.dumps(validate(event), ensure_ascii=False, sort_keys=True, allow_nan=False)
    wire_bytes(payload)
    return payload


def wire_bytes(raw):
    if not isinstance(raw, (str, bytes, bytearray)):
        raise InvalidEvent("event must be UTF-8 JSON")
    if not raw or len(raw) > MAX_EVENT_BYTES:
        raise InvalidEvent("empty Kafka value or event larger than 64 KiB")
    try:
        raw = raw.encode("utf-8") if isinstance(raw, str) else bytes(raw)
        raw.decode("utf-8")
    except UnicodeError:
        raise InvalidEvent("invalid UTF-8 encoding") from None
    if not raw or len(raw) > MAX_EVENT_BYTES:
        raise InvalidEvent("empty Kafka value or event larger than 64 KiB")
    return raw


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise InvalidEvent("duplicate JSON field")
        result[key] = value
    return result


def decode(raw):
    raw = wire_bytes(raw)
    try:
        event = validate(json.loads(raw.decode("utf-8"), object_pairs_hook=unique_object))
        # JSON escapes могут содержать lone surrogate даже в корректных UTF-8 байтах.
        encode(event)
        return event
    except (ValueError, TypeError, RecursionError) as exc:
        if isinstance(exc, InvalidEvent):
            raise
        raise InvalidEvent("invalid JSON encoding") from None


def make_event(run_id, test_id, attempt, site, worker_id, outcome, duration_ms):
    return validate(
        {
            "schema_version": 1,
            "event_type": "test.finished",
            "event_id": event_id(run_id, test_id, attempt),
            "run_id": run_id,
            "test_id": test_id,
            "attempt": attempt,
            "site": site,
            "worker_id": worker_id,
            "outcome": outcome,
            "duration_ms": round(duration_ms, 3),
            "finished_at": datetime.now(timezone.utc).isoformat(),
        }
    )
