"""Seed synthetic students (ids s0000..s1499) with random mastery per topic of their course.
Called by student_service on first start; also runnable: python -m data.seed <db_path>."""

import json
import random
import sqlite3
import sys
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent
FIRST = ["Aarav", "Diya", "Ishaan", "Ananya", "Kabir", "Meera", "Rohan", "Saanvi", "Vihaan", "Zara"]
LAST = ["Sharma", "Iyer", "Patel", "Khan", "Reddy", "Das", "Nair", "Joshi", "Gupta", "Singh"]


def course_topics() -> dict[str, list[str]]:
    root = DATA_DIR / "curriculum"
    return {d.name: sorted(p.stem for p in d.glob("*.md")) for d in sorted(root.iterdir()) if d.is_dir()}


def seed(conn: sqlite3.Connection, n: int = 1500, rng_seed: int = 42) -> int:
    rng = random.Random(rng_seed)
    topics = course_topics()
    courses = list(topics)
    rows = []
    for i in range(n):
        course = rng.choice(courses)
        mastery = {t: round(rng.betavariate(2, 2), 2) for t in topics[course]}
        rows.append((f"s{i:04d}", f"{rng.choice(FIRST)} {rng.choice(LAST)}", course, json.dumps(mastery)))
    conn.executemany("INSERT OR IGNORE INTO students VALUES (?, ?, ?, ?)", rows)
    return len(rows)


if __name__ == "__main__":
    c = sqlite3.connect(sys.argv[1] if len(sys.argv) > 1 else "student.db", isolation_level=None)
    c.execute("CREATE TABLE IF NOT EXISTS students (id TEXT PRIMARY KEY, name TEXT, course TEXT, mastery_json TEXT)")
    print("seeded", seed(c))
