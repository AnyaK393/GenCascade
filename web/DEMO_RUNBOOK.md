# Two-machine demo runbook

Mac = platform and student portal. Fedora = control room, staff portal, status page, notes uploader.

## 1. Fedora: first time only (about 10 minutes, needs internet)

```bash
git pull
```

In `.env` at the repo root, set these. `CS_TOKEN` and `REDIS_PASSWORD` must match the Mac's exactly.

```bash
PLATFORM_HOST=<mac-ip>
CONTROL_HOST=<fedora-ip>
CS_TOKEN=<same as the Mac>
REDIS_PASSWORD=<same as the Mac>
MYSQL_PASSWORD=<8 or more letters and digits>
```

```bash
scripts/fedora-web.sh setup     # installs Java, MySQL and PHP, downloads Tomcat, builds both Java apps
timedatectl                     # must show Asia/Kolkata: the exam form uses this zone
```

Ends with `Done. Next: scripts/fedora-web.sh start`. It asks for the sudo password.

## 2. Every session: find the addresses

Both laptops on the same phone hotspot (not college Wi-Fi).

```bash
ipconfig getifaddr en0      # Mac
hostname -I                 # Fedora
```

Put them in `PLATFORM_HOST` and `CONTROL_HOST` in `.env` on **both** machines. They change with the network.

## 3. Start, in this order

**Mac:**

```bash
VITE_STATUS_URL=http://<fedora-ip>:8080/status/ npm --prefix web/student-portal/client run build
scripts/demo.sh
```

The first line sets the footer's status link; repeat it only when Fedora's IP changes. When macOS asks
whether `node` may accept connections, choose Allow.

Expect a `PASS` on every line, then `Ready.` A `FAIL memory pressure yellow` means: close apps.

**Fedora:**

```bash
make control-up
scripts/fedora-web.sh start
```

Expect `ALL PASS`. This is the integration check: it tests all parts and every link between the machines.

## 4. Test it (about 15 minutes)

| # | Do | Where | You should see |
| --- | --- | --- | --- |
| 1 | Log in as `instructor@vit.edu` / `instructor123`, schedule DSA101 **3 minutes ahead**, 10 min, 40 students, topics `bst,heaps` | `http://<fedora-ip>:8085/` | Green "Exam saved and CascadeShield notified." Not the amber "Saved, but..." |
| 2 | Log in with the same account. Topic `tries`, upload a `.md` file | `http://<fedora-ip>:8070/` | "Indexed, N chunks." Topics allow lowercase, digits and `_`, not `-` |
| 3 | Log in as `s0001@student.vit.edu` / `student123` on a laptop **and an iPhone** | `http://<mac-ip>:3000/` | Dashboard with mastery bars, green "Tutor running normally" |
| 4 | Tutor: pick DSA101, ask "what is a binary search tree?" | Student portal | "AI Tutor" badge, answer in a few seconds |
| 5 | Wait for the exam start | Student portal, no reload | Amber "Tutor in light mode" and a red pill "Exam in progress: DSA101 until..." |
| 6 | Open the quiz for DSA101 | Student portal | Practice is greyed out: "Practice is closed during the exam" |
| 7 | Start load: `make load SCENARIO=exam_ramp` (11 minutes) | Fedora terminal | |
| 8 | Watch risk | `http://<fedora-ip>:8501/` | Exam listed, pre-warm done, risk climbs and crosses the threshold, SHAP reasons, level rises |
| 9 | About 3 minutes in, watch the banner, then ask a question | Student portal | Blue "High demand: showing course notes and hints", "Course notes" badge, answer in about a second |
| 10 | Submit the graded quiz | Student portal | "Submitted ✓" within a second, no score shown |
| 11 | Press Ctrl+Shift+D | Student portal | Inspector: requests, live events, no secrets |
| 12 | Open the status page | `http://<fedora-ip>:8080/status/` | Current level, control room online, one history row per level change |
| 13 | Check the Locust summary | Fedora terminal | `0(0.00%)` failures on both lines. Quiz p95 well under 1 s |
| 14 | Run the Postman collection | Fedora | 8/8 pass |

Numbers to compare with, from the Mac rehearsal on real Ollama: 915 requests, 0 failed, quiz p95 48 ms,
tutor p95 2 s. Red "Tutor service unreachable" should appear only if the gateway is really down, about 4 s
after it stops.

## 5. Before the next run

```bash
make control-down && make control-up      # Fedora: clears exams from the last run
```

An exam still running from an earlier run ends the next one early when its time is up. Delete old rows from
the staff portal's list too; that only tidies the list, because deleting does not reach the core.

## 6. Stop

```bash
scripts/fedora-web.sh stop && make control-down     # Fedora
scripts/demo.sh --stop                              # Mac
```

## If something fails

| `check` says, or you see | Fix |
| --- | --- |
| `gateway`, `RAG` or `student portal` FAIL | Same hotspot? `PLATFORM_HOST` right? `scripts/demo.sh` running? On the Mac allow Docker and node in the firewall |
| `the Mac ignores this control room` | `REDIS_PASSWORD` differs, or `make control-up` not running. Then `curl -H "X-CS-Token: $CS_TOKEN" http://<mac-ip>:8002/control/state` |
| `orchestrator :8002 unreachable or CS_TOKEN differs` | Make `CS_TOKEN` identical on both, restart both sides |
| Other devices cannot open Fedora pages | `sudo firewall-cmd --list-ports` must show 8085, 8080, 8070 |
| `make load` says no module named locust | `cd control && uv sync --group load` |
| Exam starts at the wrong time | `timedatectl` on Fedora |
| Tutor slow or failing on Ollama | `ollama list` must show `qwen2.5:0.5b`. Otherwise run `scripts/demo.sh --mock` |
| Network gone | Mac alone: `scripts/demo.sh --single` |
| Quiz says "Not confirmed yet" | Press Submit again: it is safe, the same key cannot store twice |
