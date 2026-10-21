"""Simulated students for exam-day load against the platform gateway.

Pick a scenario with CS_SCENARIO (a name in scenarios/ or a path to a YAML file):

    CS_SCENARIO=exam_ramp uv run locust -f chaos/locustfile.py --headless \
        --csv results/<run> --html results/<run>.html

The host defaults to http://$PLATFORM_HOST:8000. Every random choice derives from the
scenario's `seed`, so a run can be repeated.
"""

import itertools
import json
import os
import time
import random
import uuid
from pathlib import Path

import gevent
import yaml
from locust import HttpUser, LoadTestShape, between, task

from chaos.questions import COURSES, bank
from resilience_core.settings import settings

SCENARIO_DIR = Path(__file__).parent / "scenarios"


def load_scenario(name_or_path: str) -> dict:
    p = Path(name_or_path)
    if not p.exists():
        p = SCENARIO_DIR / f"{name_or_path}.yaml"
    cfg = yaml.safe_load(p.read_text())
    cfg.setdefault("name", p.stem)
    return cfg


SCENARIO = load_scenario(os.environ.get("CS_SCENARIO", "exam_ramp"))
SEED = int(SCENARIO.get("seed", 0))
random.seed(SEED)
# course: one course code, or "mixed" for students spread over every course
COURSE_CHOICES = COURSES if SCENARIO.get("course", "mixed") == "mixed" else [SCENARIO["course"]]
QUESTIONS = {c: bank(c, SCENARIO.get("question_length", "short")) for c in COURSE_CHOICES}
_user_ids = itertools.count()

# Optional per-request log (JSON lines) for the comparison experiment: session failure rate and
# lost quiz submissions need per-student detail that Locust's CSVs do not keep.
_REQUEST_LOG = open(os.environ["CS_REQUEST_LOG"], "a", buffering=1) if os.environ.get("CS_REQUEST_LOG") else None


def log_request(kind: str, student_id: str, r, **extra) -> None:
    if _REQUEST_LOG is None:
        return
    try:
        body = r.json() if r.status_code < 500 and r.content else {}
    except ValueError:
        body = {}
    _REQUEST_LOG.write(json.dumps({
        "t": time.time(), "kind": kind, "student": student_id, "status": r.status_code,
        "latency_s": round(r.elapsed.total_seconds(), 3) if r.elapsed else None,
        "level": body.get("level"), "source": body.get("source"),
        "duplicate": body.get("duplicate"), **extra}) + "\n")


def user_rng() -> random.Random:
    return random.Random(SEED * 1_000_003 + next(_user_ids))


def rng_uuid(rng: random.Random) -> str:
    return str(uuid.UUID(int=rng.getrandbits(128), version=4))


class TutorStudent(HttpUser):
    host = f"http://{settings.platform_host}:8000"
    weight = int(SCENARIO.get("tutor_weight", 7))
    wait_time = between(8, 20)

    def on_start(self):
        self.rng = user_rng()
        self.student_id = f"s{self.rng.randrange(10**6):06d}"
        self.session_id = rng_uuid(self.rng)
        self.course = self.rng.choice(COURSE_CHOICES)

    @task
    def ask(self):
        topic, question = self.rng.choice(QUESTIONS[self.course])
        body = {"student_id": self.student_id, "session_id": self.session_id,
                "course": self.course, "question": question}
        with self.client.post("/api/tutor/ask", json=body, name="/api/tutor/ask",
                              timeout=60, catch_response=True) as r:
            log_request("tutor", self.student_id, r, course=self.course)
            if r.status_code >= 400:
                r.failure(f"HTTP {r.status_code}")
            elif r.elapsed.total_seconds() > 15:
                r.failure("slow response (>15 s)")


class QuizTaker(HttpUser):
    host = f"http://{settings.platform_host}:8000"
    weight = int(SCENARIO.get("quiz_weight", 3))
    wait_time = between(20, 60)

    def on_start(self):
        self.rng = user_rng()
        self.student_id = f"q{self.rng.randrange(10**6):06d}"

    @task
    def submit(self):
        key = rng_uuid(self.rng)
        body = {"student_id": self.student_id, "quiz_id": f"quiz{self.rng.randrange(20)}",
                "answers": {f"q{i}": self.rng.choice("abcd") for i in range(5)},
                "idempotency_key": key}
        for attempt in range(4):  # first try + up to 3 retries with the same key
            with self.client.post("/api/quiz/submit", json=body, name="/api/quiz/submit",
                                  timeout=15, catch_response=True) as r:
                log_request("quiz", self.student_id, r, key=key, attempt=attempt + 1)
                if r.status_code == 202:
                    r.success()
                    return
                r.failure(f"HTTP {r.status_code} (attempt {attempt + 1})")
            gevent.sleep(1 + attempt)


# --- load shapes --------------------------------------------------------------------------

def lerp(a: float, b: float, frac: float) -> float:
    return a + (b - a) * min(1.0, max(0.0, frac))


def exam_ramp(t: float, c: dict) -> float | None:
    ramp, hold, taper, peak = c["ramp_s"], c["hold_s"], c["taper_s"], c["peak_users"]
    if t < ramp:
        return lerp(0, peak, t / ramp)
    if t < ramp + hold:
        return peak
    if t < ramp + hold + taper:
        return lerp(peak, 0, (t - ramp - hold) / taper)
    return None


def deadline_wave(t: float, c: dict) -> float | None:
    base, rise, hold, gap = c["base_users"], c["wave_rise_s"], c["wave_hold_s"], c["wave_gap_s"]
    warmup, period = 60, rise + hold + rise + gap
    if t < warmup:
        return lerp(0, base, t / warmup)
    k, x = divmod(t - warmup, period)
    if k >= c["waves"]:
        return None
    if x < rise:
        return base + lerp(0, c["wave_users"], x / rise)
    if x < rise + hold:
        return base + c["wave_users"]
    if x < rise + hold + rise:
        return base + lerp(c["wave_users"], 0, (x - rise - hold) / rise)
    return base


def steady_safe(t: float, c: dict) -> float | None:
    if t < c["ramp_s"]:
        return lerp(0, c["users"], t / c["ramp_s"])
    return c["users"] if t < c["ramp_s"] + c["hold_s"] else None


def flash_burst(t: float, c: dict) -> float | None:
    base_s, burst, hold = c["base_s"], c["burst_s"], c["hold_s"]
    if t < base_s:
        return c["base_users"]
    if t < base_s + burst:
        return lerp(c["base_users"], c["peak_users"], (t - base_s) / burst)
    return c["peak_users"] if t < base_s + burst + hold else None


SHAPES = {f.__name__: f for f in (exam_ramp, deadline_wave, steady_safe, flash_burst)}


class ScenarioShape(LoadTestShape):
    """The one shape class Locust sees; the YAML's `shape` picks the curve."""

    def tick(self):
        # optional lead-in at light load before the shape starts (students already online)
        t, lead_s = self.get_run_time(), SCENARIO.get("lead_s", 0)
        if t < lead_s:
            target = SCENARIO.get("lead_users", 1)
        else:
            target = SHAPES[SCENARIO["shape"]](t - lead_s, SCENARIO)
        if target is None:
            return None
        users = round(target)
        rate = max(1, abs(users - self.get_current_user_count()))
        return users, rate
