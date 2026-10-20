"""Exam calendar (guide 6.6). For each exam in data/exam_calendar.yaml (plus any scheduled at
runtime from the dashboard):

1. start - prewarm_min (10 min): POST /control/prewarm with the exam's topics.
2. start: POST /control/exam active, with floor 1 if expected_students exceeds capacity.
3. end: exam mode off.

The calendar only decides what is due; the core sends it. After a restart, an exam already
under way is started again (the call is idempotent) without a second pre-warm.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

import yaml

CALENDAR_FILE = Path(__file__).resolve().parents[1] / "data" / "exam_calendar.yaml"


@dataclass
class Exam:
    course: str
    start: datetime  # timezone-aware
    duration_min: float
    expected_students: int
    topics: list[str] = field(default_factory=list)
    prewarm_min: float = 10
    id: str = ""

    def __post_init__(self):
        self.id = self.id or f"{self.course}@{self.start.isoformat()}"

    @property
    def end(self) -> datetime:
        return self.start + timedelta(minutes=self.duration_min)

    @property
    def prewarm_at(self) -> datetime:
        return self.start - timedelta(minutes=self.prewarm_min)


@dataclass
class Due:
    exam: Exam
    step: str  # prewarm | start | end


class ExamCalendar:
    def __init__(self, exams: list[Exam], now: datetime):
        self.exams: dict[str, Exam] = {}
        self.done: dict[str, set[str]] = {}
        for e in exams:
            self.add(e, now)

    @classmethod
    def load(cls, path: Path, now: datetime) -> "ExamCalendar":
        raw = yaml.safe_load(path.read_text()) if path.exists() else None
        exams = []
        for item in (raw or {}).get("exams", []):
            start = item["start"]
            start = start if isinstance(start, datetime) else datetime.fromisoformat(str(start))
            if start.tzinfo is None:
                start = start.astimezone()  # local time
            exams.append(Exam(course=item["course"], start=start, duration_min=item["duration_min"],
                              expected_students=item.get("expected_students", 0),
                              topics=item.get("topics", []), prewarm_min=item.get("prewarm_min", 10)))
        return cls(exams, now)

    def add(self, exam: Exam, now: datetime) -> None:
        self.exams[exam.id] = exam
        done = set()
        if now >= exam.end:
            done = {"prewarm", "start", "end"}  # already over: nothing to do
        elif now >= exam.start:
            done = {"prewarm"}  # under way: start (again) but no late pre-warm
        self.done[exam.id] = done

    def due(self, now: datetime) -> list[Due]:
        out = []
        for e in self.exams.values():
            d = self.done[e.id]
            if "prewarm" not in d and e.prewarm_at <= now < e.start:
                out.append(Due(e, "prewarm"))
            if "start" not in d and e.start <= now < e.end:
                out.append(Due(e, "start"))
            if "start" in d and "end" not in d and now >= e.end:
                out.append(Due(e, "end"))
        return out

    def mark(self, due: Due) -> None:
        self.done[due.exam.id].add(due.step)
        if due.step == "start":
            self.done[due.exam.id].add("prewarm")

    def upcoming(self, now: datetime) -> list[dict]:
        return [{"id": e.id, "course": e.course, "start": e.start.isoformat(), "end": e.end.isoformat(),
                 "expected_students": e.expected_students, "topics": e.topics,
                 "status": "done" if "end" in self.done[e.id] else "running" if "start" in self.done[e.id]
                 else "prewarmed" if "prewarm" in self.done[e.id] else "scheduled"}
                for e in sorted(self.exams.values(), key=lambda e: e.start) if now < e.end + timedelta(minutes=30)]
