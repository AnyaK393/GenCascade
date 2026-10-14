#!/usr/bin/env python3
"""Check every platform service exposes the metrics listed in contracts/metrics.md.

Scrapes http://$PLATFORM_HOST:800X/metrics and exits non-zero listing anything missing,
including cs_* metrics without a `service` label. Standard library only, so it runs on
either machine without a virtualenv.

    python3 scripts/check_contracts.py [--host HOST] [--phase 3]
"""

import argparse
import os
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVICES = {  # `service` label -> port, as in contracts/metrics.md
    "gateway": 8000,
    "student": 8001,
    "orchestrator": 8002,
    "curriculum_rag": 8003,
    "llm_inference": 8004,
}
EMITTER = {"all": list(SERVICES), "gateway": ["gateway"], "student": ["student"],
           "orchestrator": ["orchestrator"], "rag": ["curriculum_rag"], "llm": ["llm_inference"]}
# Suffixes the Prometheus text format adds to a base metric name.
SUFFIXES = ("", "_bucket", "_sum", "_count", "_total", "_created", "_info")


def read_env(name: str, default: str) -> str:
    if name in os.environ:
        return os.environ[name]
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if line.strip().startswith(f"{name}="):
                return line.split("=", 1)[1].split(" #")[0].strip()
    return default


def parse_contract(path: Path, phase: int) -> dict[str, set[str]]:
    """Return {service: {metric base names}} from the markdown tables in metrics.md."""
    expected: dict[str, set[str]] = {s: set() for s in SERVICES}
    section_phase = 1
    for line in path.read_text().splitlines():
        if line.startswith("## "):
            m = re.search(r"Phase (\d+)", line)
            section_phase = int(m.group(1)) if m else 1
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 4 or not cells[0].startswith("`") or section_phase > phase:
            continue
        emitters = EMITTER.get(cells[2].strip("`").strip())
        if emitters is None:
            continue
        for name in re.findall(r"`([a-z_:]+)", cells[0]):
            for s in emitters:
                expected[s].add(name)
    return expected


def scrape(url: str) -> str:
    with urllib.request.urlopen(url, timeout=3) as r:
        return r.read().decode()


# name, then an optional {...} whose quoted values may contain braces (route="/x/{id}")
SAMPLE_RE = re.compile(r'([a-zA-Z_:][a-zA-Z0-9_:]*)(\{(?:[^"}]|"(?:[^"\\]|\\.)*")*\})?')


def parse_exposition(text: str) -> dict[str, list[str]]:
    """Return {sample name: [label strings]} from Prometheus text format. A metric declared
    with `# TYPE` but without samples yet (a labelled metric before its first request) counts
    as present with no labels to check."""
    samples: dict[str, list[str]] = {}
    for line in text.splitlines():
        if line.startswith("# TYPE "):
            samples.setdefault(line.split()[2], [])
            continue
        if not line or line.startswith("#"):
            continue
        m = SAMPLE_RE.match(line)
        if m:
            samples.setdefault(m.group(1), []).append(m.group(2) or "")
    return samples


def present(base: str, samples: dict[str, list[str]]) -> list[str] | None:
    """Label strings of every sample belonging to `base`, or None if the metric is absent."""
    stem = base.removesuffix("_total")
    names = {n for suf in SUFFIXES for n in (base + suf, stem + suf) if n in samples}
    return [lbl for n in names for lbl in samples[n]] if names else None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--host", default=read_env("PLATFORM_HOST", "localhost"))
    ap.add_argument("--phase", type=int, default=1, help="include metrics added up to this phase")
    ap.add_argument("--contract", type=Path, default=ROOT / "contracts" / "metrics.md")
    args = ap.parse_args()

    expected = parse_contract(args.contract, args.phase)
    problems = 0
    for service, port in SERVICES.items():
        url = f"http://{args.host}:{port}/metrics"
        try:
            samples = parse_exposition(scrape(url))
        except OSError as e:
            print(f"FAIL {service:<15} {url} unreachable: {e}")
            problems += 1
            continue
        missing, unlabelled = [], []
        for base in sorted(expected[service]):
            labels = present(base, samples)
            if labels is None:
                missing.append(base)
            elif base.startswith("cs_") and not all('service="' in lbl for lbl in labels):
                unlabelled.append(base)
        if missing or unlabelled:
            problems += len(missing) + len(unlabelled)
            print(f"FAIL {service:<15} {url}")
            for m in missing:
                print(f"       missing     {m}")
            for m in unlabelled:
                print(f"       no service= {m}")
        else:
            print(f"ok   {service:<15} {len(expected[service])} metrics")
    print(f"\n{'PASS' if not problems else f'{problems} problem(s)'} against {args.host}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
