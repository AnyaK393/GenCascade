# Web layer notes

Decisions made while building from `WEB_LAYER_PLAN.md`, and what is still unproven.

## Scope

- Built: A, B, C, D, E, F, G(3, 4), H, following the lean scope in section 0. F is in scope because A was
  built.
- A was built first, at the owner's request. F was built before the G and H docs so they describe the
  finished system.
- Nothing is committed, at the owner's request, although section 8 says to commit per phase.
- `STAFF_PORTAL_URL` was left out of `.env.example` because its only use was the calendar sync that
  section 0 skips. `CORE_URL` was added instead.
- `demo.sh` checks ":3000 responds" after starting the portal, because a true preflight would fail on
  every first run. A portal that is not built only gives a warning, so the existing demo is unchanged.
- One small JUnit test (`StatusLogicTest`) covers the status page's share and parsing logic.

## Versions

Newer than, or not named in, the plan: Express 5, React Router 7, Vite 8, TypeScript 7, Spring Boot
3.3.13. Tested on Node 24; the plan's Node 20 has not been tried.

## Behaviour worth knowing

- **Practice fails closed.** When the gateway is unreachable the server returns 503 and the button is
  disabled, because practice replies contain answers and an exam may be running.
- **Practice closes per course.** Only the course under exam is blocked.
- **Submit keys are per student and quiz** in `localStorage`, so a shared phone cannot file one
  student's quiz as another's duplicate. Quiz drafts are stored too, which is what the red banner
  promises.
- **Submit is blocked on the page once confirmed, but retaking the quiz after a reload is a
  new submission** with a new key, as on the old page.
- **`crypto.randomUUID` is not used in the browser**: it does not exist on plain HTTP origins, which is
  how phones reach the portal.
- **Helmet** has `upgrade-insecure-requests`, HSTS and COOP turned off because the demo runs on HTTP.
  Turn them back on behind HTTPS, and set the cookie's `secure` flag.
- **Register shares the login rate limiter** (10 attempts per 5 minutes per IP), so nobody can burn
  through the student id range.
- **Java's `HttpClient` is forced to HTTP/1.1.** Its default h2c upgrade makes uvicorn drop POST bodies.
- **The mastery panel shows the platform's record**, labelled with its course. Portal and platform seed
  students separately, so `s0001` may have a different course and name in each.
- **`/control/mode` needs a fresh heartbeat**, and with the core running the core can override the
  level. Check C's level changes were tested with a simulated heartbeat, as `ladder_check.py` does.

## Known limits

- Deleting or editing an exam does not reach the resilience core: `/ops/exam` can only add. To cancel a
  demo exam, restart the core. Exams are not synced back after a core restart either, because G1 was
  skipped.
- If the core was down when an exam was created, it must be created again.
- Uploading a topic that already exists in the curriculum adds to that topic rather than replacing it,
  and notes cannot be deleted through the API.
- `pending` uploads are not retried; upload again.
- The PHP and Spring logins have no rate limit. The apps are for staff on the local network.
- JWTs cannot be revoked: logout clears the cookie, and a copied token works until it expires (8 h).
- An open Socket.IO connection is not closed when its token expires. It only carries public status.
- The status page's healthy share only covers time since its first history row.
- A queued answer that expires makes that bubble keep polling until the page is closed.
- Status JSON is read with regular expressions, because the plan names no JSON library. The comment in
  `StatusPoller.java` says when to replace them.

- Overlapping exams: when any exam ends, the core sends "exam off", even if another is still running. The
  staff form does not stop overlaps. `/admin/reset` does not clear the core's calendar; restarting the core
  clears exams added at runtime. Avoid overlaps and restart the core between rehearsals.
- `data/exam_calendar.yaml` holds real exams (DSA101 on 2026-11-20 at 09:00, OS202 on 2026-11-24 at 14:00).
  A demo running at those times enters exam mode by itself.
- Locust's seeded scenarios reuse their idempotency keys, so repeat runs add no rows to `submissions`.
  `committed` does not grow by the request count, and that is correct.
- `exam_ramp` calls the gateway directly, so it does not load the Express portal. Portal memory below was
  measured during the ramp but with a single browser session on it.

## Verified, and how

Tested on the Mac with real services. Fedora's parts ran in Docker on the versions the plan names:
MySQL 8, Tomcat 10.1, Java 21, PHP 8.3.

| Check | Result |
| --- | --- |
| A | Upload, search, restart survival, rejected input, concurrent uploads. `smoke.py` and `ladder_check.py` pass. |
| B | All items, except that `audit.log` is cut by section 0. RSS 57-63 MB. |
| C | Scripted in headless Chrome at 375 px and 1280 px over the Mac's LAN IP. |
| D | `./mvnw test` on Java 21 and 24. `prod` on MySQL, exam form, real resilience core. Postman 8/8 in Newman. |
| E | Tomcat with MySQL: history rows, core offline, gateway offline, MySQL offline, theme cookie. |
| F | Browser flow, shared BCrypt login, pending and failed states, tutor answering from an upload at level 2. |
| G | `demo.sh --mock` starts the portal and `--stop` stops it. |
| Exam rehearsal (Mac, 2026-11-06) | `demo.sh --single` on real Ollama, exam created in the staff portal, full `exam_ramp`: 915 requests, 0 failed, quiz p95 48 ms, tutor p95 2 s; level 1 then 2 and breaker open at 0.97 risk; portal max 41 MB; 0 page errors. |
| `fedora-web.sh` (2026-11-06) | `setup`, `start`, `check`, `stop` in a Fedora 45 container with systemd, against the Mac's live stack: Java 25, MySQL 9.7, PHP 8.5, Tomcat 10.1.61. Exam reached the core, status history in MySQL, upload indexed and the tutor answered from it. Package choice also checked on Fedora 41 and 43. |

## Not verified here

Run these on demo hardware before the demo.

1. **Real phones:** open `http://<mac-ip>:3000` on an iPhone and an Android phone. Chrome's phone
   emulation is not Safari.
2. **Real Ollama:** `scripts/demo.sh`, then ask a question. Testing used the mock LLM.
3. **Fedora natively:** `scripts/fedora-web.sh` ran in a container, so firewalld, SELinux, x86_64 and a
   real network between the machines are untested.
4. **Two machines:** the core ran on the Mac for every test. Create an exam on Fedora, then confirm that the student banner shows exam mode on
   the Mac:
   `curl -s -H "X-CS-Token: $CS_TOKEN" http://<fedora-ip>:8600/state`
5. **Portal under many real users:** watch memory while everyone is logged in:
   `ps -o rss= -p $(lsof -tiTCP:3000 -sTCP:LISTEN)` (under 120000 KB).
6. **Postman app:** Collection Runner, as tested through Newman only.
7. **Control tests:** `pytest` in `control/` (needs a working `control/.venv`). They could not run here: that
   venv has no Python and the control image has no pytest. No code under `control/` was changed.
