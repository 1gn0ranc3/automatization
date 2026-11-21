import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from automation.telemetry.events import InvalidEvent, encode


class Database:
    def __init__(self, path, *, create=True, readonly=False):
        self.path = Path(path)
        self.mode = "ro" if readonly else "rwc" if create else "rw"
        if self.mode == "rwc":
            self.path.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def connection(self):
        db = sqlite3.connect(
            f"{self.path.resolve().as_uri()}?mode={self.mode}", uri=True, timeout=2
        )
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()


class Outbox(Database):
    def __init__(self, path, *, create=True, readonly=False):
        super().__init__(path, create=create, readonly=readonly)
        if self.mode != "rwc":
            return
        with self.connection() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS outbox (
                event_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, payload TEXT NOT NULL,
                delivered INTEGER NOT NULL DEFAULT 0 CHECK(delivered IN (0,1)))""")
            db.execute("CREATE INDEX IF NOT EXISTS outbox_pending ON outbox(delivered,run_id)")

    def append(self, event):
        payload = encode(event)
        with self.connection() as db:
            inserted = db.execute(
                "INSERT OR IGNORE INTO outbox(event_id,run_id,payload) VALUES (?,?,?)",
                (event["event_id"], event["run_id"], payload),
            ).rowcount
            if not inserted:
                old = db.execute(
                    "SELECT payload FROM outbox WHERE event_id=?", (event["event_id"],)
                ).fetchone()
                if old is None or old["payload"] != payload:
                    raise InvalidEvent("conflicting outbox event_id")

    def pending(self, run_id=None, limit=10000):
        with self.connection() as db:
            rows = db.execute(
                "SELECT payload FROM outbox WHERE delivered=0 AND (? IS NULL OR run_id=?) "
                "ORDER BY rowid LIMIT ?",
                (run_id, run_id, limit),
            )
            return [json.loads(row["payload"]) for row in rows]

    def iter_pending(self, run_id=None, batch_size=500):
        """Один проход по очереди ограниченными порциями, без открытой транзакции при yield."""
        if type(batch_size) is not int or batch_size < 1:
            raise ValueError("batch_size must be a positive integer")
        with self.connection() as db:
            last = db.execute("SELECT COALESCE(MAX(rowid),0) FROM outbox").fetchone()[0]
        cursor = 0
        while cursor < last:
            with self.connection() as db:
                rows = db.execute(
                    "SELECT rowid,payload FROM outbox WHERE delivered=0 "
                    "AND rowid>? AND rowid<=? AND (? IS NULL OR run_id=?) "
                    "ORDER BY rowid LIMIT ?",
                    (cursor, last, run_id, run_id, batch_size),
                ).fetchall()
            if not rows:
                break
            for row in rows:
                cursor = row["rowid"]
                yield json.loads(row["payload"])

    def mark_delivered(self, event_id):
        with self.connection() as db:
            db.execute("UPDATE outbox SET delivered=1 WHERE event_id=?", (event_id,))

    def counts(self, run_id=None):
        with self.connection() as db:
            rows = db.execute(
                "SELECT delivered, COUNT(*) AS n FROM outbox WHERE ? IS NULL OR run_id=? "
                "GROUP BY delivered",
                (run_id, run_id),
            )
            counts = {row["delivered"]: row["n"] for row in rows}
        return {"pending": counts.get(0, 0), "delivered": counts.get(1, 0)}


class Results(Database):
    def __init__(self, path, *, create=True, readonly=False):
        super().__init__(path, create=create, readonly=readonly)
        if self.mode != "rwc":
            return
        with self.connection() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS results (
                event_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, test_id TEXT NOT NULL,
                attempt INTEGER NOT NULL, site TEXT NOT NULL, outcome TEXT NOT NULL,
                duration_ms REAL NOT NULL, payload TEXT NOT NULL,
                UNIQUE(run_id,test_id,attempt))""")

    def record(self, event):
        payload = encode(event)
        with self.connection() as db:
            # Уникальный индекс разрешает гонку двух обработчиков на одной БД.
            changed = db.execute(
                "INSERT OR IGNORE INTO results VALUES (?,?,?,?,?,?,?,?)",
                tuple(
                    event[k]
                    for k in (
                        "event_id",
                        "run_id",
                        "test_id",
                        "attempt",
                        "site",
                        "outcome",
                        "duration_ms",
                    )
                )
                + (payload,),
            ).rowcount
            if not changed:
                previous = db.execute(
                    "SELECT payload FROM results WHERE event_id=?", (event["event_id"],)
                ).fetchone()
                if previous is None or previous["payload"] != payload:
                    raise InvalidEvent("conflicting result for the same test attempt")
        return bool(changed)

    def summary(self, run_id=None):
        with self.connection() as db:
            rows = db.execute(
                "SELECT run_id,site,outcome,COUNT(*) AS attempts,"
                "ROUND(SUM(duration_ms),3) AS duration_ms "
                "FROM results WHERE ? IS NULL OR run_id=? GROUP BY run_id,site,outcome "
                "ORDER BY run_id,site,outcome",
                (run_id, run_id),
            )
            return [dict(row) for row in rows]
