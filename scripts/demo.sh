#!/usr/bin/env bash
# One-command demo start on the Mac (guide 7.1). Run from anywhere:
#
#   scripts/demo.sh            preflight, platform in cascadeshield mode on real Ollama, warm-up, reset
#   scripts/demo.sh --mock     same with LLM_BACKEND=mock (Ollama misbehaving)
#   scripts/demo.sh --single   also run the control room here (no network to Fedora); combine with --mock
#   scripts/demo.sh --stop     stop everything this script started (keeps the submissions volume)
#   scripts/demo.sh --prepare  build both images now, with internet, so --single works offline later
#
# Preflight failures are printed but do not stop the demo; fix them or carry on knowingly.
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export CS_PLATFORM_DIR="$ROOT/platform" CS_CONTROL_DIR="$ROOT/control"
# Without build attestations an unchanged image keeps its id, so a rerun does not recreate containers.
export BUILDX_NO_DEFAULT_ATTESTATIONS=1
LOG="$ROOT/.demo.log"; : > "$LOG"

MOCK=0 SINGLE=0 STOP=0 PREPARE=0
for arg in "$@"; do
  case "$arg" in
    --mock) MOCK=1 ;;
    --single) SINGLE=1 ;;
    --stop) STOP=1 ;;
    --prepare) PREPARE=1 ;;
    -h|--help) sed -n '2,10p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown option: $arg (try --help)"; exit 2 ;;
  esac
done

# .env value without its inline comment; the environment wins.
envval() {
  local v="${!1:-}"
  [ -n "$v" ] || v="$(sed -n "s/^$1=\([^ #]*\).*/\1/p" .env 2>/dev/null | head -1)"
  echo "${v:-$2}"
}
TOKEN="$(envval CS_TOKEN dev-token)"
PLATFORM_HOST="$(envval PLATFORM_HOST localhost)"
CONTROL_HOST="$(envval CONTROL_HOST localhost)"
MODEL="$(envval LLM_MODEL qwen2.5:0.5b)"

if [ -t 1 ]; then G=$'\033[32m' R=$'\033[31m' Y=$'\033[33m' B=$'\033[1m' N=$'\033[0m'; else G= R= Y= B= N=; fi
FAILS=0
pass() { echo "  ${G}PASS${N}  $1"; }
fail() { echo "  ${R}FAIL${N}  $1"; FAILS=$((FAILS + 1)); }
warn() { echo "  ${Y}WARN${N}  $1"; }
step() { echo; echo "${B}$1${N}"; }

if [ "$STOP" = 1 ]; then
  # Both profiles share one compose project and network: take the control containers down with it,
  # or a later --single finds them attached to a network that no longer exists.
  docker compose --profile platform --profile control down >>"$LOG" 2>&1 && echo "stopped (submissions volume kept)"
  exit 0
fi

if [ "$PREPARE" = 1 ]; then
  docker compose --profile platform --profile control build && ollama pull "$MODEL" \
    && echo "${G}images built and $MODEL pulled: --single and the platform now start without internet${N}"
  exit $?
fi

# --- 1. preflight -----------------------------------------------------------------------------
step "1. Preflight"
[ -f .env ] && pass ".env present" || fail ".env missing: cp .env.example .env and set CS_TOKEN, REDIS_PASSWORD"

if [ "$MOCK" = 1 ]; then
  warn "Ollama checks skipped (--mock)"
else
  if curl -sf -m 3 localhost:11434/api/version >/dev/null; then pass "Ollama responds on :11434"
  else fail "Ollama not responding: open the Ollama app, or rerun with --mock"; fi
  if ollama ps 2>/dev/null | grep -q "^$MODEL"; then pass "$MODEL loaded (ollama ps)"
  else warn "$MODEL not loaded yet; the warm-up loads it (check OLLAMA_KEEP_ALIVE=-1)"; fi
fi

if docker info >/dev/null 2>&1; then
  mem=$(docker info --format '{{.MemTotal}}')
  gb=$(awk -v m="$mem" 'BEGIN { printf "%.1f", m / 1e9 }')
  # Docker reports a little less than the setting: 2.5 GB shows as about 2.5e9 bytes
  if awk -v m="$mem" 'BEGIN { exit !(m > 2.3e9 && m < 2.8e9) }'; then pass "Docker memory ${gb} GB (setting 2.5 GB)"
  else fail "Docker memory ${gb} GB: set Settings -> Resources -> Memory to 2.5 GB"; fi
else
  fail "Docker is not running: start Docker Desktop"; echo; exit 1
fi

lan="$(ipconfig getifaddr en0 2>/dev/null || true)"
if [ "$SINGLE" = 1 ]; then
  warn "Fedora check skipped (--single: control room runs on this Mac)"
else
  if [ -n "$lan" ] && [ "$PLATFORM_HOST" != "$lan" ]; then
    fail "PLATFORM_HOST=$PLATFORM_HOST in .env but this Mac is $lan now: update .env on both machines"
  elif [ -n "$lan" ]; then pass "PLATFORM_HOST matches this Mac's address ($lan)"; fi
  if [ "$CONTROL_HOST" = localhost ] || [ "$CONTROL_HOST" = 127.0.0.1 ]; then
    fail "CONTROL_HOST is $CONTROL_HOST: set Fedora's IP in .env, or use --single"
  elif ping -c 1 -t 2 "$CONTROL_HOST" >/dev/null 2>&1; then pass "Fedora answers ping at $CONTROL_HOST"
  else fail "Fedora ($CONTROL_HOST) does not answer ping: same hotspot? Else use --single"; fi
fi

# kern.memorystatus_vm_pressure_level: 1 normal (green), 2 warning (yellow), 4 critical (red)
case "$(sysctl -n kern.memorystatus_vm_pressure_level 2>/dev/null)" in
  1) pass "memory pressure green" ;;
  2) fail "memory pressure yellow: close the browser and other apps" ;;
  4) fail "memory pressure red: close apps, or lower OLLAMA_NUM_PARALLEL to 1" ;;
  *) warn "memory pressure unknown" ;;
esac

# --- 2. platform ------------------------------------------------------------------------------
BACKEND=ollama; [ "$MOCK" = 1 ] && BACKEND=mock
step "2. Platform: PROTECTION_MODE=cascadeshield LLM_BACKEND=$BACKEND"
t0=$(date +%s)
if ! PROTECTION_MODE=cascadeshield LLM_BACKEND=$BACKEND docker compose --profile platform up -d --build --wait --quiet-pull >>"$LOG" 2>&1; then
  docker compose --profile platform ps --format 'table {{.Service}}\t{{.Status}}'
  echo "${R}platform did not become healthy: see .demo.log and docker compose --profile platform logs${N}"
  exit 1
fi
pass "all platform services healthy in $(( $(date +%s) - t0 )) s"

if [ "$SINGLE" = 1 ]; then
  step "2b. Control room on this Mac (--single)"
  PLATFORM_HOST=localhost python3 control/prometheus/render_targets.py >>"$LOG"
  # The control image holds only dependencies (its code is bind-mounted), so build it only when missing:
  # that needs internet, which --single may not have. scripts/demo.sh --prepare builds it beforehand.
  build=; docker image inspect cascadeshield-control:dev >/dev/null 2>&1 || { build=--build; warn "control image missing: building it (needs internet, several minutes)"; }
  if CS_PLATFORM_ADDR=compose docker compose --profile control up -d $build --quiet-pull >>"$LOG" 2>&1; then
    for _ in $(seq 1 45); do curl -sf -m 2 localhost:8600/state >/dev/null && break; sleep 2; done
    if curl -sf -m 2 localhost:8600/state >/dev/null; then
      model="$(curl -sf -m 2 localhost:8600/state | python3 -c 'import json,sys; print(json.load(sys.stdin).get("model") or "")')"
      pass "resilience core up on :8600"
      [ -n "$model" ] && pass "predictor model $model loaded" \
        || warn "no trained model on this Mac (control/models/*.joblib is git-ignored): the core uses the threshold rule; copy the .joblib files from Fedora"
    else
      fail "resilience core not answering: docker compose --profile control logs resilience-core"
    fi
  else
    fail "control room did not start: see .demo.log"
  fi
fi

# --- 3. warm-up -------------------------------------------------------------------------------
step "3. Warm-up (5 level-0 answers)"
qs=("What is a binary search tree?" "Why is quicksort slow on sorted input?" "What does a join do in SQL?"
    "What is a deadlock?" "How does a heap find the minimum?")
cs=(DSA101 DSA101 DBMS201 OS202 DSA101)
for i in 0 1 2 3 4; do
  t=$(date +%s)
  if curl -sf -m 60 -X POST localhost:8002/admin/answer -H "X-CS-Token: $TOKEN" -H 'Content-Type: application/json' \
      -d "{\"course\":\"${cs[$i]}\",\"question\":\"${qs[$i]}\",\"level\":0}" >/dev/null; then
    pass "warm-up $((i + 1)): $(( $(date +%s) - t )) s"
  else
    fail "warm-up $((i + 1)) failed: is the LLM backend up? (rerun with --mock)"
  fi
done

# --- 4. reset and URLs ------------------------------------------------------------------------
step "4. Reset"
if curl -sf -m 10 -X POST localhost:8002/admin/reset -H "X-CS-Token: $TOKEN" >/dev/null; then
  pass "POST /admin/reset (level 0, breaker closed, queues and chaos cleared)"
else fail "POST /admin/reset failed"; fi

host="${lan:-localhost}"
echo
echo "${B}Ready.${N}  $FAILS preflight/start problem(s)."
echo "  Student page      http://$host:8000/   (this Mac: http://localhost:8000/)"
echo "  Control state     curl -s -H 'X-CS-Token: \$CS_TOKEN' localhost:8002/control/state | python3 -m json.tool"
if [ "$SINGLE" = 1 ]; then
  echo "  Dashboard         http://localhost:8501/"
else
  echo "  Dashboard         http://$CONTROL_HOST:8501/   (Fedora)"
fi
echo "  Stop              scripts/demo.sh --stop"
exit 0
