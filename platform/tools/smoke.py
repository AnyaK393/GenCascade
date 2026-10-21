#!/usr/bin/env python3
"""End-to-end smoke test of the running platform (standard library only).

    python3 platform/tools/smoke.py [--host localhost]

Checks every /health, asks a tutor question, submits a quiz twice (second must be a duplicate),
forces level 3 through the control API, checks the hint path and the banner, then resets.
"""

import argparse
import json
import os
import time
import urllib.request
import uuid
from pathlib import Path


def env(name, default):
    p = Path(__file__).resolve().parents[2] / ".env"
    if name in os.environ:
        return os.environ[name]
    for line in (p.read_text().splitlines() if p.exists() else []):
        if line.startswith(f"{name}="):
            return line.split("=", 1)[1].split("#")[0].strip()
    return default


def call(url, body=None, token=None, timeout=60):
    req = urllib.request.Request(url, json.dumps(body).encode() if body is not None else None,
                                 {"Content-Type": "application/json", **({"X-CS-Token": token} if token else {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, json.load(r)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="localhost")
    a = ap.parse_args()
    gw, orch, tok = f"http://{a.host}:8000", f"http://{a.host}:8002", env("CS_TOKEN", "dev-token")
    ok = True

    def check(name, cond, detail=""):
        nonlocal ok
        ok &= bool(cond)
        print(f"{'PASS' if cond else 'FAIL'}  {name}  {detail}")

    for port in range(8000, 8005):
        try:
            check(f"health :{port}", call(f"http://{a.host}:{port}/health")[0] == 200)
        except Exception as e:
            check(f"health :{port}", False, str(e))
    t0 = time.time()
    _, d = call(f"{gw}/api/tutor/ask", {"student_id": "s0001", "session_id": "smoke", "course": "DSA101",
                                         "question": "Why does inserting sorted keys make a BST slow?"})
    check("tutor answer", d.get("answer"), f"level={d.get('level')} source={d.get('source')} "
          f"{time.time() - t0:.1f}s\n      {d.get('answer', '')[:200]}")
    key = str(uuid.uuid4())
    quiz = {"student_id": "s0001", "quiz_id": "quiz1", "answers": {"q1": "a"}, "idempotency_key": key}
    s1, d1 = call(f"{gw}/api/quiz/submit", quiz)
    s2, d2 = call(f"{gw}/api/quiz/submit", quiz)
    check("quiz commit + idempotent retry", s1 == s2 == 202 and not d1["duplicate"] and d2["duplicate"])
    call(f"{orch}/control/mode", {"level": 3, "reason": "smoke test", "actor": "operator"}, tok)
    _, st = call(f"{orch}/control/state", token=tok)
    _, d = call(f"{gw}/api/tutor/ask", {"student_id": "s0002", "course": "OS202",
                                         "question": "How do I avoid deadlock with two locks?"})
    note = f"(control_source={st['control_source']}: remote level only applies while Fedora's heartbeat is fresh)"
    if st["control_source"] == "remote":
        check("level 3 serves a hint", d["source"] == "hint" and d["level"] == 3, d["answer"][:120])
    else:
        print(f"SKIP  level 3 via control API {note}")
    _, s = call(f"{gw}/api/status")
    check("status banner", s.get("banner"), json.dumps(s))
    call(f"{orch}/admin/reset", {}, tok)
    print("\nALL PASS" if ok else "\nSOME CHECKS FAILED")
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
