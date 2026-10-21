"""student_service (port 8001): profiles and durable, idempotent quiz submissions in SQLite (WAL).
Endpoints are `async def` and use SQLite inline: each statement takes well under a millisecond, and
running on the single event-loop thread serialises access without a lock or threadpool hand-off."""

import json
import sqlite3
import time

from fastapi import Depends, HTTPException
from fastapi.responses import JSONResponse
from prometheus_client import Counter
from pydantic import BaseModel

from cs_common import create_app, settings
from cs_common.metrics import metric
from cs_common.redis_client import require_token
from data.seed import seed

SUBS = metric(Counter, "cs_submissions_total", "Quiz submits by outcome", ("status",))
for s in ("committed", "duplicate", "failed"):
    SUBS(s)

SCHEMA = """
CREATE TABLE IF NOT EXISTS students (id TEXT PRIMARY KEY, name TEXT, course TEXT, mastery_json TEXT);
CREATE TABLE IF NOT EXISTS submissions (idempotency_key TEXT PRIMARY KEY, student_id TEXT,
    quiz_id TEXT, answers_json TEXT, received_at REAL);
"""

settings.db_path.parent.mkdir(parents=True, exist_ok=True)
db = sqlite3.connect(settings.db_path, isolation_level=None, timeout=5)
db.row_factory = sqlite3.Row
db.execute("PRAGMA journal_mode=WAL")
db.execute("PRAGMA synchronous=NORMAL")  # WAL: durable across app/container crashes
db.executescript(SCHEMA)
if db.execute("SELECT COUNT(*) FROM students").fetchone()[0] == 0:
    seed(db)

app = create_app()


def level_of(mastery: dict) -> str:
    avg = sum(mastery.values()) / max(1, len(mastery))
    return "beginner" if avg < 0.4 else "advanced" if avg > 0.7 else "intermediate"


@app.get("/profile/{student_id}")
async def profile(student_id: str):
    row = db.execute("SELECT * FROM students WHERE id = ?", (student_id,)).fetchone()
    if not row:
        raise HTTPException(404, "unknown student")
    mastery = json.loads(row["mastery_json"])
    return {"student_id": row["id"], "name": row["name"], "course": row["course"],
            "mastery": mastery, "level": level_of(mastery)}


class SubmitBody(BaseModel):
    student_id: str
    quiz_id: str
    answers: dict | list
    idempotency_key: str


@app.post("/submissions", status_code=202)
async def submit(b: SubmitBody):
    try:
        cur = db.execute("INSERT OR IGNORE INTO submissions VALUES (?, ?, ?, ?, ?)",
                         (b.idempotency_key, b.student_id, b.quiz_id, json.dumps(b.answers), time.time()))
        if cur.rowcount == 0:
            row = db.execute("SELECT * FROM submissions WHERE idempotency_key = ?",
                             (b.idempotency_key,)).fetchone()
            SUBS("duplicate").inc()
            return {"status": "duplicate", "idempotency_key": row["idempotency_key"],
                    "received_at": row["received_at"]}
    except sqlite3.Error as e:
        SUBS("failed").inc()
        return JSONResponse({"status": "failed", "error": str(e)}, status_code=503)
    SUBS("committed").inc()
    return {"status": "committed", "idempotency_key": b.idempotency_key}


@app.get("/admin/stats")
async def stats():
    n, distinct = db.execute("SELECT COUNT(*), COUNT(DISTINCT student_id) FROM submissions").fetchone()
    students = db.execute("SELECT COUNT(*) FROM students").fetchone()[0]
    return {"committed": n, "students_submitted": distinct, "students": students}


@app.post("/admin/reset", dependencies=[Depends(require_token)])
async def admin_reset():
    """Wipe submissions between comparison runs (guide 7.2)."""
    n = db.execute("DELETE FROM submissions").rowcount
    return {"ok": True, "deleted": n}
