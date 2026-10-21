"""Joint answer-quality rating (guide 7.4): 30 answers per level L0-L3, rated blind 1-5 on
"would this help a student move forward?" by both of you.

    # 1. collect answers (real Ollama: point PLATFORM_HOST at the Mac, LLM_BACKEND=ollama)
    uv run python -m experiments.answer_quality sheet [--per-level 30]
    # 2. each rater copies docs/ratings/sheet.csv to rater_a.csv / rater_b.csv and fills `rating`
    # 3. score -> docs/answer_quality.json (used by run_matrix for "learning utility retained")
    uv run python -m experiments.answer_quality score

L0/L1 come from the orchestrator's /admin/answer (forced LLM level). L2/L3 have no forced
endpoint, so this tool briefly acts as the control room: it needs the resilience core's kill
switch on (or the core stopped), writes the heartbeat itself and sets the level through the
control API, then puts level 0 back. The platform must be in PROTECTION_MODE=cascadeshield.
"""

import argparse
import csv
import json
import random
import time
from pathlib import Path

import httpx
import redis

from chaos.questions import COURSES, bank
from resilience_core.settings import settings

REPO = Path(__file__).resolve().parents[2]
RATINGS_DIR = REPO / "docs" / "ratings"
OUT = REPO / "docs" / "answer_quality.json"
HDR = {"X-CS-Token": settings.cs_token}
LEVELS = [0, 1, 2, 3]


def sample_questions(n: int, seed: int) -> list[tuple[str, str]]:
    rng = random.Random(seed)
    pool = [(c, q) for c in COURSES for _, q in bank(c)]
    return rng.sample(pool, n)


def collect(per_level: int, seed: int) -> None:
    orch, gw = settings.service_url("orchestrator"), settings.service_url("gateway")
    r = redis.Redis(host=settings.redis_host, port=settings.redis_port, password=settings.redis_password,
                    decode_responses=True)
    with httpx.Client(timeout=60) as client:
        state = client.get(f"{orch}/control/state", headers=HDR).json()
        if state.get("protection_mode") != "cascadeshield":
            raise SystemExit("platform must run PROTECTION_MODE=cascadeshield (levels 2-3 come from Fedora's level)")
        try:
            core = client.get(f"{settings.core_url}/state", timeout=3).json()
            if core.get("healthy") and not (core.get("ops") or {}).get("kill_switch"):
                raise SystemExit("turn the resilience core's kill switch on first, so it does not override the level")
        except httpx.HTTPError:
            pass  # core not running: fine

        rows = []
        questions = sample_questions(per_level * len(LEVELS), seed)
        for li, level in enumerate(LEVELS):
            if level >= 2:
                r.set("cs:control:heartbeat", f"{time.time():.3f}", ex=10)
                client.post(f"{orch}/control/mode", headers=HDR, json={
                    "level": level, "reason": "answer-quality rating", "actor": "rating"}).raise_for_status()
                time.sleep(1)
            for i, (course, q) in enumerate(questions[li * per_level:(li + 1) * per_level]):
                if level <= 1:
                    resp = client.post(f"{orch}/admin/answer", headers=HDR,
                                       json={"course": course, "question": q, "level": level})
                else:
                    r.set("cs:control:heartbeat", f"{time.time():.3f}", ex=10)
                    resp = client.post(f"{gw}/api/tutor/ask", json={
                        "student_id": f"rater{level}{i:03d}", "course": course, "question": q})
                resp.raise_for_status()
                d = resp.json()
                served = d.get("level", level)
                if served != level:
                    print(f"  warning: asked for L{level}, served L{served}")
                rows.append({"level": served, "source": d.get("source", "llm"), "course": course,
                             "question": q, "answer": d.get("answer") or d.get("text", "")})
                print(f"L{level} {i + 1}/{per_level}", end="\r", flush=True)
            print()
        client.post(f"{orch}/control/mode", headers=HDR, json={"level": 0, "reason": "rating done", "actor": "rating"})
        r.delete("cs:control:heartbeat")

    rng = random.Random(seed + 1)
    rng.shuffle(rows)
    RATINGS_DIR.mkdir(parents=True, exist_ok=True)
    with open(RATINGS_DIR / "sheet.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id", "course", "question", "answer", "rating"])
        for i, row in enumerate(rows, 1):
            w.writerow([i, row["course"], row["question"], row["answer"], ""])
    with open(RATINGS_DIR / "key.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id", "level", "source"])
        for i, row in enumerate(rows, 1):
            w.writerow([i, row["level"], row["source"]])
    print(f"wrote {RATINGS_DIR / 'sheet.csv'} ({len(rows)} answers, blind) and key.csv (do not open before rating)")


def read_ratings(path: Path, skip: set[int] = frozenset()) -> dict[int, float]:
    """id -> rating. Refuses ratings outside 1-5; unrated ids are reported and left out."""
    with open(path, newline="", encoding="utf-8-sig") as f:  # utf-8-sig: spreadsheets may add a BOM
        rows = list(csv.DictReader(f))
    out, bad, missing = {}, [], []
    for r in rows:
        if int(r["id"]) in skip:
            continue
        v = (r.get("rating") or "").strip()
        if not v:
            missing.append(r["id"])
            continue
        try:
            x = float(v)
        except ValueError:
            x = None
        if x is None or not 1 <= x <= 5:
            bad.append(f"id {r['id']}: {v!r}")
            continue
        out[int(r["id"])] = x
    if bad:
        raise SystemExit(f"{path.name}: ratings must be 1-5; fix {', '.join(bad)}")
    if missing:
        print(f"warning: {path.name} has {len(missing)} unrated answers (ids {', '.join(missing[:10])}); "
              "they are left out of the score")
    return out


def score(raters: list[Path], exclude: dict[int, str] | None = None) -> None:
    """exclude: {id: reason} for items dropped for every rater (e.g. a malformed question)."""
    exclude = exclude or {}
    with open(RATINGS_DIR / "key.csv") as f:
        key = {int(r["id"]): int(r["level"]) for r in csv.DictReader(f)}
    ratings = [{i: v for i, v in read_ratings(p, skip=set(exclude)).items()} for p in raters]
    common = sorted(set(key).intersection(*ratings))
    if not common:
        raise SystemExit("no answer rated by every rater")
    by_level: dict[int, list[float]] = {}
    agree = 0
    for i in common:
        vals = [r[i] for r in ratings]
        by_level.setdefault(key[i], []).append(sum(vals) / len(vals))
        agree += max(vals) - min(vals) <= 1
    result = {
        "raters": [p.name for p in raters], "answers_rated": len(common),
        "mean_by_level": {lv: round(sum(v) / len(v), 3) for lv, v in sorted(by_level.items())},
        "n_by_level": {lv: len(v) for lv, v in sorted(by_level.items())},
        "agreement_within_1": round(agree / len(common), 3),
        "excluded": {str(i): why for i, why in exclude.items()},
        "note": "1-5, 'would this help a student move forward?', rated blind; mean of raters per answer",
    }
    OUT.write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))
    print(f"wrote {OUT}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("sheet", help="collect answers into a blind rating sheet")
    s.add_argument("--per-level", type=int, default=30)
    s.add_argument("--seed", type=int, default=74)
    c = sub.add_parser("score", help="score the raters' sheets")
    c.add_argument("raters", nargs="*", type=Path,
                   default=[RATINGS_DIR / "rater_a.csv", RATINGS_DIR / "rater_b.csv"])
    c.add_argument("--exclude", action="append", default=[], metavar="ID:REASON",
                   help="drop an item for every rater, with the reason recorded (repeatable)")
    args = ap.parse_args()
    if args.cmd == "sheet":
        collect(args.per_level, args.seed)
    else:
        score(args.raters, {int(e.split(":", 1)[0]): e.split(":", 1)[-1] for e in args.exclude})


if __name__ == "__main__":
    main()
