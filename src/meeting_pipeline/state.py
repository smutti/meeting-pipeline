from __future__ import annotations
import sqlite3
import time
from .common import save, read, digest


class State:
    def __init__(self, home):
        self.home = home
        home.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(home / "state.sqlite3", timeout=30)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY, status TEXT NOT NULL,
          source TEXT NOT NULL, created REAL NOT NULL, updated REAL NOT NULL, error TEXT);
        CREATE TABLE IF NOT EXISTS steps(job TEXT NOT NULL, name TEXT NOT NULL,
          signature TEXT NOT NULL, status TEXT NOT NULL, updated REAL NOT NULL,
          PRIMARY KEY(job,name));
        CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY, job TEXT,
          kind TEXT NOT NULL, payload TEXT NOT NULL, created REAL NOT NULL);
        """)

    def job(self, job_id):
        row = self.db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        if row is None:
            raise ValueError(f"Unknown job: {job_id}")
        return dict(row)

    def jobs(self):
        return [
            dict(r) for r in self.db.execute("SELECT * FROM jobs ORDER BY created DESC")
        ]

    def register(self, job_id, source):
        now = time.time()
        self.db.execute(
            "INSERT OR IGNORE INTO jobs VALUES(?,?,?,?,?,NULL)",
            (job_id, "queued", str(source), now, now),
        )
        self.db.commit()

    def status(self, job_id, status, error=None):
        self.db.execute(
            "UPDATE jobs SET status=?, error=?, updated=? WHERE id=?",
            (status, error, time.time(), job_id),
        )
        self.db.commit()

    def event(self, job_id, kind, payload):
        import json

        self.db.execute(
            "INSERT INTO events(job,kind,payload,created) VALUES(?,?,?,?)",
            (job_id, kind, json.dumps(payload, ensure_ascii=False), time.time()),
        )
        self.db.commit()

    def step(self, job_id, name, signature, action):
        target = self.home / "jobs" / job_id / f"{name}.json"
        sig = digest(signature)
        row = self.db.execute(
            "SELECT * FROM steps WHERE job=? AND name=?", (job_id, name)
        ).fetchone()
        if (
            row
            and row["signature"] == sig
            and row["status"] == "complete"
            and target.is_file()
        ):
            return read(target)
        self.db.execute(
            "INSERT OR REPLACE INTO steps VALUES(?,?,?,?,?)",
            (job_id, name, sig, "running", time.time()),
        )
        self.db.commit()
        result = action()
        save(target, result)
        self.db.execute(
            "UPDATE steps SET status='complete', updated=? WHERE job=? AND name=?",
            (time.time(), job_id, name),
        )
        self.db.commit()
        return result
