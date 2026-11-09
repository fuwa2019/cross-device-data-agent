import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


def now():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def encode(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True)


class Store:
    """One local database, serialized writers, atomic source updates."""

    def __init__(self, directory):
        self.directory = Path(directory).expanduser().resolve()
        self.directory.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.directory / "index.sqlite", timeout=5)
        # Rollback journal avoids a WAL sidecar. State must still be local.
        self.conn.execute("PRAGMA foreign_keys=ON")
        version = self.conn.execute("PRAGMA user_version").fetchone()[0]
        if version not in (0, 1):
            self.conn.close()
            raise ValueError(f"不支持数据库版本 {version}")
        if version == 0:
            self.conn.executescript("""
                BEGIN IMMEDIATE;
                CREATE TABLE IF NOT EXISTS sources (
                    source_id TEXT PRIMARY KEY, data TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS entries (
                    source_id TEXT NOT NULL REFERENCES sources(source_id),
                    path TEXT NOT NULL, data TEXT NOT NULL,
                    PRIMARY KEY(source_id, path));
                CREATE TABLE IF NOT EXISTS scans (
                    id TEXT PRIMARY KEY, source_id TEXT NOT NULL, data TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY, value TEXT NOT NULL);
                PRAGMA user_version=1;
            """)
            self.conn.execute("INSERT OR IGNORE INTO settings VALUES ('host_id',?)", (str(uuid4()),))
            self.conn.commit()
        self.host_id = self.conn.execute("SELECT value FROM settings WHERE key='host_id'").fetchone()[0]

    def close(self):
        self.conn.close()

    def source(self, source_id):
        row = self.conn.execute("SELECT data FROM sources WHERE source_id=?", (source_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def sources(self):
        return [json.loads(row[0]) for row in self.conn.execute("SELECT data FROM sources ORDER BY source_id")]

    def put_source(self, source):
        self.conn.execute("INSERT INTO sources VALUES (?,?) ON CONFLICT(source_id) DO UPDATE SET data=excluded.data",
                          (source["source_id"], encode(source)))

    def entries(self, source_id=None):
        query = "SELECT data FROM entries"
        args = ()
        if source_id is not None:
            query += " WHERE source_id=?"
            args = (source_id,)
        query += " ORDER BY source_id,path"
        return [json.loads(row[0]) for row in self.conn.execute(query, args)]

    def put_entry(self, entry):
        self.conn.execute("INSERT INTO entries VALUES (?,?,?) ON CONFLICT(source_id,path) DO UPDATE SET data=excluded.data",
                          (entry["source_id"], entry["path"], encode(entry)))

    def put_scan(self, scan):
        self.conn.execute("INSERT INTO scans VALUES (?,?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data",
                          (scan["id"], scan["source_id"], encode(scan)))

    def scans(self, source_id=None):
        rows = self.conn.execute("SELECT data FROM scans ORDER BY rowid")
        scans = [json.loads(row[0]) for row in rows]
        if source_id is None:
            return scans
        return [scan for scan in scans if scan["source_id"] == source_id]

    def writer_lock(self):
        return WriterLock(self.directory / "writer.lock")


class WriterLock:
    """OS-released process lock, including the committed running marker."""

    def __init__(self, path):
        self.path = path

    def __enter__(self):
        self.stream = self.path.open("a+b")
        try:
            if os.name == "nt":
                import msvcrt
                self.stream.seek(0)
                if not self.stream.read(1):
                    self.stream.write(b"0")
                    self.stream.flush()
                self.stream.seek(0)
                msvcrt.locking(self.stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.stream.close()
            raise ValueError("另一个写入任务正在运行，请稍后重试") from None
        return self

    def __exit__(self, *args):
        self.stream.close()
