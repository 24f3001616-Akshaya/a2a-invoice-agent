import hashlib
import json
import sqlite3
import uuid
from threading import RLock

def canonical_json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

class TaskStore:
    def __init__(self, path):
        self.path = path
        self.lock = RLock()
        with self.connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS tasks (
                task_id TEXT PRIMARY KEY, principal TEXT NOT NULL, task_json TEXT NOT NULL
            )""")
            db.execute("""CREATE TABLE IF NOT EXISTS messages (
                principal TEXT NOT NULL, message_id TEXT NOT NULL, message_hash TEXT NOT NULL,
                task_id TEXT NOT NULL, PRIMARY KEY(principal, message_id)
            )""")

    def connect(self):
        db = sqlite3.connect(self.path, timeout=20, isolation_level="IMMEDIATE")
        db.row_factory = sqlite3.Row
        return db

    def new_id(self):
        return str(uuid.uuid4())

    def lookup_message(self, principal, message_id, message):
        digest = hashlib.sha256(canonical_json(message).encode()).hexdigest()
        with self.lock, self.connect() as db:
            row = db.execute("SELECT message_hash, task_id FROM messages WHERE principal=? AND message_id=?",
                             (principal, message_id)).fetchone()
            if not row:
                return None
            if row["message_hash"] != digest:
                raise ValueError("IDEMPOTENCY_CONFLICT")
            task_row = db.execute("SELECT task_json FROM tasks WHERE task_id=?", (row["task_id"],)).fetchone()
            return json.loads(task_row["task_json"]) if task_row else None

    def create_task(self, principal, message_id, message, task):
        digest = hashlib.sha256(canonical_json(message).encode()).hexdigest()
        with self.lock, self.connect() as db:
            db.execute("INSERT INTO tasks(task_id, principal, task_json) VALUES (?, ?, ?)",
                       (task["id"], principal, canonical_json(task)))
            db.execute("INSERT INTO messages(principal, message_id, message_hash, task_id) VALUES (?, ?, ?, ?)",
                       (principal, message_id, digest, task["id"]))

    def get_task(self, principal, task_id):
        if not task_id:
            return None
        with self.lock, self.connect() as db:
            row = db.execute("SELECT task_json FROM tasks WHERE task_id=? AND principal=?",
                             (task_id, principal)).fetchone()
            return json.loads(row["task_json"]) if row else None

    def list_tasks(self, principal):
        with self.lock, self.connect() as db:
            rows = db.execute("SELECT task_json FROM tasks WHERE principal=? ORDER BY rowid DESC",
                              (principal,)).fetchall()
            return [json.loads(r["task_json"]) for r in rows]

    def update_task(self, principal, task_id, task):
        with self.lock, self.connect() as db:
            cur = db.execute("UPDATE tasks SET task_json=? WHERE task_id=? AND principal=?",
                             (canonical_json(task), task_id, principal))
            if cur.rowcount != 1:
                raise ValueError("Task not found")
