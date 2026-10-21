#!/usr/bin/env python3
"""Fairness check (guide 6.5): each course's share of degraded answers (level >= 2), from the
orchestrator's cs_orch_responses_total{level,source,course}. Standard library only.

    python3 platform/tools/fairness.py [--host localhost]
"""

import argparse
import re
import urllib.request
from collections import defaultdict


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="localhost")
    a = ap.parse_args()
    text = urllib.request.urlopen(f"http://{a.host}:8002/metrics", timeout=5).read().decode()
    by = defaultdict(lambda: defaultdict(float))
    for labels, value in re.findall(r"^cs_orch_responses_total\{([^}]*)\} (\S+)", text, re.M):
        lab = dict(re.findall(r'(\w+)="([^"]*)"', labels))
        by[lab["course"]][int(lab["level"])] += float(value)
    if not by:
        raise SystemExit("no answers recorded yet")
    print(f"{'course':10} {'answers':>8} " + " ".join(f"{'L' + str(lv):>6}" for lv in range(5)) + "  degraded")
    shares = {}
    for course, lv in sorted(by.items()):
        total = sum(lv.values())
        shares[course] = sum(v for k, v in lv.items() if k >= 2) / total
        print(f"{course:10} {total:8.0f} " + " ".join(f"{lv.get(k, 0) / total:6.0%}" for k in range(5)) + f"  {shares[course]:7.0%}")
    spread = max(shares.values()) - min(shares.values())
    print(f"\nspread in degraded share: {spread:.0%}" + ("  (over 20%: consider round-robin shedding)" if spread > 0.2 else ""))


if __name__ == "__main__":
    main()
