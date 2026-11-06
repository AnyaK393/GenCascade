# CascadeShield Web Layer — Build Spec for Claude Code

**Read this whole file before writing any code.** It is the complete brief. Do not ask the user
questions that this file answers. If something is genuinely missing, choose the simplest option
that matches the rules in section 2 and note your choice in `web/NOTES.md`.

**Time budget: 2 days, one developer (on the Mac), with a second person testing on Fedora.**
Build in the phase order in section 5. Keep everything small and working. A finished simple
feature beats an unfinished impressive one.

---

## 0. LEAN SCOPE — THIS OVERRIDES THE REST OF THE FILE

The team chose a reduced scope to save time and avoid integration risk. Build the phases below
**as written in this section**; where this section and a later section disagree, this section wins.

| Phase | Decision |
|---|---|
| A (RAG notes endpoint) | **Build last, only if time remains.** It is the only change to existing platform code. |
| B (Express) | Build in full, except: no `audit.js` (morgan access log is enough). |
| C (React) | Build, but **cut**: dark mode, the Recharts latency chart in the network inspector, the Recharts mastery chart (use plain Tailwind bars instead). Keep everything else. |
| D (Spring Boot) | Build, but **cut**: `/admin/live` (Redis), `/admin/users`, `spring-boot-starter-data-redis`, `micrometer-registry-prometheus`. Keep Actuator `/actuator/health` only. |
| D — new integration | When an exam is **created** through the form or `POST /api/exams`, Spring Boot also calls the resilience core's **existing** endpoint `POST {CORE_URL}/ops/exam` (header `X-CS-Token: ${CS_TOKEN}`) with `{"course", "in_minutes" (start minus now, in minutes, minimum 0.1), "duration_min", "expected_students", "topics", "prewarm_min": 1.5}`. `CORE_URL` defaults to `http://localhost:8600`. If the call fails, the exam is still saved and the page shows a warning "Saved, but CascadeShield was not notified". This needs **no change to the control room code**. |
| E (JSP status page) | Build in full. No backend changes. |
| F (PHP uploader) | Build **only if Phase A is built**. If A is skipped, skip F too and mark Unit I as "not used" in `SYLLABUS_MAP.md`. |
| G (Integration) | **Skip items 1 and 2** (calendar sync in the resilience core, Prometheus job). Keep item 3 (links) and item 4 (`demo.sh`). |
| H (Docs, tests) | Keep `web/README.md`, `web/SYLLABUS_MAP.md`, the Postman collection, the Spring `MockMvc` test. **Cut** the Vitest and supertest tests. |

**Build order:** B → C → D → E → G(3, 4) → H → (A → F if time remains).
Two Claude Code sessions may run in parallel: session 1 does B → C, session 2 does D → E.

With this scope the **only** files outside `web/` that change are `.gitignore`, `.env.example`,
`README.md` (one row) and `scripts/demo.sh` — plus `platform/services/rag/main.py` and
`platform/compose.yml` only if Phase A is built.

**Firewall (add to `web/README.md`):** these pages are opened from other devices, so inbound
ports must be allowed. Fedora: `sudo firewall-cmd --add-port={8085,8080,8070}/tcp --permanent && sudo firewall-cmd --reload`.
Mac: allow `node` when macOS asks to accept incoming connections (or System Settings → Network →
Firewall → Options).

---

## 1. Context

This repository (`GenCascade` / CascadeShield) is **already finished and working**:

- `platform/` (runs on an M1 Mac, 8 GB): five FastAPI services (gateway 8000, student 8001,
  orchestrator 8002, rag 8003, llm_inference 8004), Redis 6379, Ollama, and a one-file student
  page at `platform/web/index.html`.
- `control/` (runs on a Fedora laptop): Prometheus 9090, resilience core 8600 (ML predictor,
  dependency graph, containment engine, exam calendar), Streamlit dashboard 8501, Locust 8089.
- `contracts/` describes metrics, Redis keys and the control API. Read
  `contracts/control_api.md` and `contracts/redis_keys.md` before touching integrations.

**Goal of this work:** add a proper web application layer so the project covers the college's
Web Technology syllabus with features that have a real job:

| Syllabus unit | What we add | Folder | Runs on |
|---|---|---|---|
| II React, V Advanced React | Student portal SPA (React + TypeScript + Redux Toolkit + React Router + Tailwind) | `web/student-portal/client` | Mac |
| VI Node.js | Express server: login, API proxy, Socket.IO live status, serves the SPA | `web/student-portal/server` | Mac |
| IV Spring Boot | Staff portal: Spring Security, JPA + MySQL, Redis, Actuator, REST API, Postman | `web/staff-portal` | Fedora |
| III Servlet / JSP | Public system status page (Servlet + JSP + JavaBean, MVC, JDBC to MySQL) | `web/status-page` | Fedora |
| I PHP | Course notes uploader (forms, sessions, cookies, file handling, validation, MySQL/PDO) | `web/notes-uploader` | Fedora |

**Do not rewrite or refactor existing code.** The only existing-code changes allowed are the
small ones listed in Phase A and Phase G.

---

## 2. Ground rules (apply to every phase)

1. **Exam-critical things stay on the Mac; staff tools live on Fedora.** Students must be able
   to log in, ask questions and submit quizzes even if Fedora is switched off. Never make the
   student portal depend on MySQL, Spring Boot, PHP or Tomcat.
2. **The browser never sees `CS_TOKEN` or `REDIS_PASSWORD`.** Only server-side code (Express,
   Spring, PHP, Servlet) may use them, read from environment variables.
3. **The student never sends their own `student_id`.** Express takes it from the verified JWT.
4. **No fake UI states.** Every badge, spinner and banner reflects a real server response.
5. **Small and readable over clever.** Plain code, short files, comments only where the reason is
   not obvious. No extra frameworks beyond those named here.
6. **Ports are fixed** (section 3). Configuration comes from environment variables with the
   defaults given, so the same code runs on both machines.
7. **Every phase ends with its check list passing.** Do not start the next phase of the same
   component with a failing check.
8. **Memory on the Mac is tight.** The Node server must stay under ~120 MB. Do not run MySQL,
   Spring Boot, Tomcat or PHP on the Mac while the platform is running; use the dev profiles
   (H2 / SQLite) described below when developing on the Mac.

---

## 3. Ports, hosts and shared configuration

| Component | Machine | Port |
|---|---|---|
| Student portal (Express + built React) | Mac | **3000** |
| React dev server (development only) | Mac | 5173 |
| Staff portal (Spring Boot) | Fedora | **8085** |
| Status page (Tomcat 10.1) | Fedora | **8080** |
| Notes uploader (PHP built-in server) | Fedora | **8070** |
| MySQL 8 | Fedora | 3306 |

Existing ports (do not reuse): 8000–8004, 6379, 11434 on the Mac; 8501, 8600, 8089, 9090 on Fedora.

Add these to the root `.env.example` (append, do not reorder existing lines):

```
# --- web layer ---
JWT_SECRET=change-me-long-random       # student portal JWT signing key (Mac)
GATEWAY_URL=http://localhost:8000      # used by Express on the Mac
STUDENT_URL=http://localhost:8001      # used by Express on the Mac
MYSQL_HOST=localhost                   # Fedora
MYSQL_DB=cascadeshield_web
MYSQL_USER=csweb
MYSQL_PASSWORD=change-me
STAFF_PORTAL_URL=                      # e.g. http://host.docker.internal:8085 ; empty = calendar sync off
```

Shared MySQL database `cascadeshield_web` on Fedora. Table ownership:

| Table | Created by | Used by |
|---|---|---|
| `staff_user`, `course`, `exam` | Spring Boot (JPA, `ddl-auto=update`) | Spring Boot, PHP (reads `staff_user` for login) |
| `status_history` | `web/sql/schema.sql` | Status page |
| `note_upload` | `web/sql/schema.sql` | Notes uploader |

Staff passwords are stored as **plain BCrypt hashes** (`$2a$...`, no `{bcrypt}` prefix) so PHP's
`password_verify()` can check the same accounts.

**Demo accounts** (seeded automatically, listed in `web/README.md`):

| Who | Login | Password | Where |
|---|---|---|---|
| Students | `s0001@student.vit.edu` … `s0010@student.vit.edu` | `student123` | Student portal |
| Instructor | `instructor@vit.edu` | `instructor123` | Staff portal, notes uploader |
| Admin | `admin@vit.edu` | `admin123` | Staff portal, notes uploader |

---

## 4. Final folder layout

```
web/
├── README.md                    how to run each part on each machine, demo accounts, demo script
├── NOTES.md                     decisions made while building
├── SYLLABUS_MAP.md              unit → feature → file paths (for the viva)
├── sql/schema.sql               status_history, note_upload, CREATE DATABASE/USER helper
├── student-portal/
│   ├── server/                  Node 20 + Express (ESM)
│   └── client/                  Vite + React 18 + TypeScript
├── staff-portal/                Spring Boot 3 (Java 21, Maven wrapper)
├── status-page/                 Jakarta Servlet 6 + JSP (Maven, WAR for Tomcat 10.1)
└── notes-uploader/              PHP 8 (no framework)
```

Add `node_modules/`, `dist/`, `target/`, `*.db`, `web/notes-uploader/outbox/`,
`web/notes-uploader/uploads/` and `web/student-portal/server/logs/` to `.gitignore`.

---

## 5. Phases

Phases **A → B → C** are the student portal and are the top priority. Phases **D, E, F** are
independent of each other and of B/C; build them after C in the order D, E, F. If time runs out,
cut from the end (F, then E). Phase G and H wrap up.

```
A (platform tweak) ─┐
                    ├─ B (Express) ─ C (React) ─┐
                    └─ F (PHP uses A)           ├─ G (integration) ─ H (docs, tests, demo)
D (Spring Boot) ─────────────────────────────────┤
E (JSP status page) ─────────────────────────────┘
```

---

### Phase A — Platform tweak for uploaded notes (about 1 hour)

Goal: the RAG service can accept new course notes at runtime and re-index, so the PHP uploader
(Phase F) makes uploaded notes searchable by the tutor immediately.

Changes in `platform/services/rag/main.py` only:

1. Add a notes directory: `NOTES_DIR = Path(os.environ.get("NOTES_DIR", "/notes"))`.
2. Make `load_chunks()` read `settings.data_dir / "curriculum"` **and** `NOTES_DIR` (same
   `<COURSE>/<topic>.md` layout, same chunking). Skip `NOTES_DIR` silently if it does not exist.
3. Move the index-building code from `lifespan` into `def build_index() -> dict` that returns a
   new dict; `lifespan` calls it and does `index.update(...)`. Keep `reload_cache_vectors()` after it.
4. New endpoint, token-protected like the others:

```
POST /admin/notes   (header X-CS-Token)
body: {"course": "DSA101", "topic": "tries", "markdown": "## Concept\n..."}
```

   - Validate: `course` in the courses that exist under `curriculum/`; `topic` matches
     `^[a-z0-9_]{2,40}$`; `markdown` 20–100 000 chars and contains at least one `## ` heading.
     Return 422 with a clear message otherwise.
   - Write `NOTES_DIR/<course>/<topic>.md` (create folders), rebuild with `build_index()` inside an
     `asyncio.Lock`, swap the dict contents in one `index.clear(); index.update(new)` step, then
     `await reload_cache_vectors()`.
   - Return `{"ok": true, "chunks": <number of chunks for this file>, "total_chunks": <n>}`.
5. `GET /admin/notes` (token) returns the list of uploaded `{course, topic, bytes}`.

Change in `platform/compose.yml`: give the `rag` service a named volume `notes-data:/notes` and an
env var `NOTES_DIR: /notes`; declare `notes-data` under `volumes:`.

**Check A**
- [ ] `curl -X POST localhost:8003/admin/notes -H "X-CS-Token: $CS_TOKEN" -H 'Content-Type: application/json' -d '{"course":"DSA101","topic":"tries","markdown":"## Concept\n\nA trie stores strings by prefix..."}'` returns ok.
- [ ] `POST /search {"query":"trie prefix","course":"DSA101"}` returns the new chunk.
- [ ] Notes survive `docker compose restart rag`.
- [ ] Existing tools (`platform/tools/smoke.py`, `ladder_check.py`) still pass.

---

### Phase B — Student portal server: Node.js + Express (about 4 hours)

Folder `web/student-portal/server`. Node 20, ES modules (`"type": "module"`).

**Dependencies:** `express`, `helmet`, `cors`, `cookie-parser`, `jsonwebtoken`, `bcryptjs`,
`better-sqlite3`, `express-rate-limit`, `morgan`, `socket.io`, `dotenv`, `zod`.
Dev: `nodemon`. (No ORM, no extra frameworks.)

**Files (one module per concern, to show Node's module system):**

```
server/
├── package.json          scripts: dev (nodemon), start (node src/index.js), seed
├── src/
│   ├── index.js          creates app + http server + Socket.IO, mounts routes, serves client/dist
│   ├── config.js         reads env (dotenv loads ../../../.env), exports constants
│   ├── db.js             better-sqlite3 → data/portal.db, creates tables, seed()
│   ├── auth.js           hash/verify, sign/verify JWT, requireAuth middleware
│   ├── routes/auth.js    /auth/*
│   ├── routes/api.js     /api/* (proxy to FastAPI + quizzes)
│   ├── liveStatus.js     polls gateway /api/status, broadcasts over Socket.IO
│   ├── audit.js          appends JSON lines to logs/audit.log with fs.promises
│   └── quizzes.json      quiz bank moved from platform/web/index.html, plus correct answers
└── data/                 portal.db lives here (gitignored)
```

**Database (SQLite, file `data/portal.db`, WAL mode):**

```sql
CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  email TEXT UNIQUE NOT NULL,
  name TEXT NOT NULL,
  student_id TEXT UNIQUE NOT NULL,   -- s0000..s1499, matches platform student_service
  course TEXT NOT NULL,              -- DSA101 | DBMS201 | OS202
  password_hash TEXT NOT NULL,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
```

Seed on first start: `s0001`…`s0010`, emails `s0001@student.vit.edu`…, password `student123`,
courses rotating DSA101, DBMS201, OS202, names like "Student 01".

**Auth endpoints:**

| Method, path | Body | Behaviour |
|---|---|---|
| `POST /auth/register` | `{name, email, password, course}` | zod-validate (email format, password ≥ 8, course in list). Assign the lowest unused id in `s0011`–`s1499`. Hash with bcrypt (10 rounds). Log in immediately (set cookie). 409 if email exists. |
| `POST /auth/login` | `{email, password}` | Rate-limited: 10 attempts / 5 min / IP. On success set cookie `cs_auth` = JWT `{sub: student_id, name, email, course}`, 8 h expiry; cookie `httpOnly`, `sameSite: 'lax'`, `secure: false` (local HTTP demo). 401 with a generic message on failure. Write an audit line. |
| `POST /auth/logout` | none | Clear the cookie. |
| `GET /auth/me` | none | 200 with the JWT claims (`student_id, name, email, course, exp`) or 401. |

**API endpoints (all require auth; `student_id` always comes from the JWT):**

| Method, path | Forwards to | Notes |
|---|---|---|
| `POST /api/tutor/ask` `{course, question, session_id?}` | `POST {GATEWAY_URL}/api/tutor/ask` | Add `student_id` from JWT. Pass through status codes (429, 504) and body. Add `request_id` (uuid) and measured `latency_ms` to the response. Timeout 30 s. |
| `GET /api/tutor/queued/:qid` | `GET {GATEWAY_URL}/api/tutor/queued/:qid` | Pass through. |
| `POST /api/quiz/submit` `{quiz_id, answers, idempotency_key}` | `POST {GATEWAY_URL}/api/quiz/submit` | Add `student_id`. Validate `idempotency_key` is a UUID. Pass through 202 / 503. Timeout 5 s. |
| `GET /api/quizzes/:course` | local `quizzes.json` | Questions and options **without** the answers. |
| `POST /api/quizzes/:course/practice` `{answers}` | local | Returns `{score, total, results:[{index, correct, correct_option}]}`. **Returns 403 if an exam is active for that course** (from the latest status). |
| `GET /api/profile` | `GET {STUDENT_URL}/profile/{student_id}` | Pass through mastery and level; on failure return `{"available": false}` with 200. |
| `GET /api/status` | latest cached status from `liveStatus.js` | Fallback for clients without WebSocket. |
| `GET /health` | none | `{ok: true}` (no auth). |

Quiz ids: `<COURSE>-quiz1`, same as the old page. Copy the questions exactly from
`platform/web/index.html` (`QUIZZES` constant) and add the correct option index for each.

**Live status (`liveStatus.js`):** every 2 s `GET {GATEWAY_URL}/api/status` (timeout 1.5 s).
Keep the last value. When `level`, `banner` or `exam.active` changes, `io.emit("status", value)`.
On connect, send the current value at once. If the gateway is unreachable, emit
`{level: null, banner: "Tutor service unreachable. Your quiz answers are kept in this browser.", color: "red", exam: {active: false}}`.
Socket.IO connections must be authenticated: read and verify the `cs_auth` cookie in
`io.use(...)`; reject without it.

**Middleware order in `index.js`:** `helmet()` (with a CSP that allows `'self'`, the Socket.IO
connection and inline styles Tailwind needs; no remote scripts) → `morgan('combined')` to
`logs/access.log` via `fs.createWriteStream` → `express.json({limit: '100kb'})` →
`cookie-parser` → `cors({origin: 'http://localhost:5173', credentials: true})` only when
`NODE_ENV !== 'production'` → routes → static `../client/dist` → SPA fallback (`index.html` for
any non-API GET) → a final JSON error handler (never leak stack traces).

**Check B**
- [ ] `npm run dev` starts on 3000; `GET /health` ok; memory under 120 MB (`ps`).
- [ ] Login with `s0001@student.vit.edu / student123` sets an httpOnly cookie; `/auth/me` returns claims.
- [ ] `POST /api/tutor/ask` with the cookie returns an answer with `level`, `source`, `request_id`.
- [ ] Without the cookie every `/api/*` route returns 401.
- [ ] Same `idempotency_key` submitted twice → second reply has `duplicate: true`.
- [ ] 11 wrong logins in a row → 429.
- [ ] `logs/audit.log` and `logs/access.log` are written.

---

### Phase C — Student portal client: React + TypeScript (about 8 hours)

Folder `web/student-portal/client`. Vite + React 18 + TypeScript (strict).

**Dependencies:** `react-router-dom`, `@reduxjs/toolkit`, `react-redux`, `socket.io-client`,
`react-markdown`, `tailwindcss` (v3, with PostCSS), `recharts` (for one small chart).
Vite dev proxy: `/auth`, `/api`, `/socket.io` → `http://localhost:3000` (with `ws: true`).
Production: `npm run build` → `dist/`, served by Express.

**Structure:**

```
src/
├── main.tsx                Provider(store) + RouterProvider
├── types/api.ts            TypeScript interfaces: AskResponse, Status, Quiz, Profile, Me, ...
├── store/
│   ├── index.ts            configureStore
│   ├── api.ts              RTK Query: me, login, register, logout, ask, queued, quizzes, practice, submit, profile
│   ├── authSlice.ts        current user
│   ├── statusSlice.ts      live status from Socket.IO
│   └── chatSlice.ts        chat messages per course
├── hooks/
│   ├── useLiveStatus.ts    Socket.IO connect, dispatch status; falls back to polling /api/status every 3 s if the socket fails
│   ├── useIdempotentSubmit.ts  key in localStorage until confirmed; retries 3× (0.5 s, 1 s, 2 s backoff) with the SAME key
│   └── useQueuedAnswer.ts  polls /api/tutor/queued/:id every 3 s until answered
├── components/
│   ├── Layout.tsx          navbar + <StatusBanner/> + <Outlet/>; mobile hamburger menu
│   ├── StatusBanner.tsx    colour by level (green/amber/blue/red), exam badge
│   ├── LevelBadge.tsx      L0 "AI Tutor" purple, L1 "Light mode" amber, L2 "Course notes" blue, L3 "Hint" grey, L4 "Queued" slate
│   ├── ChatMessage.tsx     React.memo; renders answer with react-markdown (NO rehype-raw, raw HTML stays disabled)
│   ├── QuestionCard.tsx    one quiz question, radio options (controlled input, props + onChange callback to parent)
│   ├── ProgressBar.tsx
│   ├── Toast.tsx           small toast system (context) for queue position and errors
│   ├── ErrorBoundary.tsx   CLASS component with componentDidCatch (covers lifecycle/Component API)
│   └── NetworkInspector.tsx  bottom drawer, opened with ?debug=1 or Ctrl+Shift+D
├── pages/
│   ├── LoginPage.tsx, RegisterPage.tsx
│   ├── DashboardPage.tsx   greeting, course, mastery bars (Recharts BarChart from /api/profile), quick links
│   ├── TutorPage.tsx       chat
│   ├── QuizPage.tsx        stepper
│   └── NotFoundPage.tsx
└── routes.tsx              createBrowserRouter; <RequireAuth> wrapper; React.lazy + Suspense per page
```

**Page behaviour:**

- **Login / Register:** controlled forms, inline validation messages, disabled button while
  submitting, server error shown. Register has a course dropdown. On success go to `/`.
- **RequireAuth:** calls `/auth/me` once; redirects to `/login` on 401, keeping the intended path.
- **Tutor page:** message list (keys = message ids), input with `useRef` to auto-focus after send
  and to auto-scroll to the newest message. While waiting, show a Tailwind `animate-pulse`
  skeleton bubble. Each answer shows `<LevelBadge>`, latency in ms, and source. On 429 show a toast
  "Slow down: 6 questions per minute". For `level 4` responses show a toast
  "Question queued at position #N. Your quiz is safe." and use `useQueuedAnswer` to replace the
  bubble when the answer arrives.
- **Quiz page:** one question per step with Back / Next, `<ProgressBar>`, review screen, then two
  modes:
  - *Practice* (only when no exam is active for the course): calls `/practice`, shows a result
    modal with green/red per question and the score.
  - *Submit for grading*: `useIdempotentSubmit`. Show a small "Idempotency protected" chip with
    the first 8 characters of the key, real states "Submitting…", "Retrying (2/3)…",
    "Submitted ✓ committed" or "Already received ✓" (duplicate). If all retries fail, keep the key
    and show "Not confirmed yet. Press Submit again — it is safe to retry." Never show a score
    for graded submissions.
- **Status banner:** always visible under the navbar, updates live; text from the server.
- **Network inspector (viva feature):** tabs **Requests** (last 20: method, path, status,
  latency, `request_id`, level/source if present, click to see the JSON body), **Live events**
  (Socket.IO messages with timestamps), **Session** (decoded claims from `/auth/me`, socket
  connection state). It must never display tokens, cookies or secrets. Also a tiny Recharts line
  chart: tutor latency vs quiz-submit latency over the last 20 calls.
- **Responsive:** works at 375 px wide (phone) and 1280 px (projector). Respect
  `prefers-color-scheme` for dark mode. Buttons and inputs have labels; keyboard reachable.

**Check C**
- [ ] `npm run build` has no TypeScript errors; Express serves the build at `http://<mac-ip>:3000`.
- [ ] Full flow on a phone browser on the same network: register, login, ask, practice quiz, graded submit.
- [ ] Changing the level with `POST /control/mode` (curl on the orchestrator) changes the banner within 3 s with no page reload, and new answers show the matching badge.
- [ ] Stop the gateway container: banner turns red; start it again: banner recovers.
- [ ] Kill the network mid-submit (DevTools offline): retries show; reconnect + Submit → "Already received" or "committed", never a duplicate row.
- [ ] Network inspector shows requests and events and no secrets.
- [ ] Old page at `http://<mac>:8000/` still works (do not delete it).

---

### Phase D — Staff portal: Spring Boot (about 5 hours)

Folder `web/staff-portal`. Java 21, Spring Boot 3.3.x, Maven wrapper (`./mvnw`), package
`edu.vit.cascadeshield.staff`. Server-rendered UI with **Thymeleaf** (no second SPA).

**Starters:** web, thymeleaf, security, data-jpa, validation, data-redis, actuator; drivers
`mysql-connector-j` and `h2`; `micrometer-registry-prometheus`; test: spring-boot-starter-test,
spring-security-test.

**Profiles:**
- `dev` (default on the Mac): H2 in-memory, Redis disabled-tolerant (pages show "Redis offline").
- `prod` (Fedora): MySQL from `MYSQL_*` env vars; Redis at `PLATFORM_HOST:6379` with
  `REDIS_PASSWORD`.
`server.port=8085`.

**Entities (JPA):**

- `StaffUser { id, email (unique), name, passwordHash, role (INSTRUCTOR|ADMIN) }`
- `Course { code (PK, e.g. DSA101), title }` — seed DSA101 "Data Structures", DBMS201
  "Database Systems", OS202 "Operating Systems".
- `Exam { id, course (ManyToOne), startAt (OffsetDateTime), durationMin, expectedStudents,
  topics (comma-separated string), createdBy, createdAt }`, Bean Validation: start in the future,
  duration 5–240, expectedStudents 1–2000, topics match `^[a-z0-9_]+(,[a-z0-9_]+)*$`.

Repositories with Spring Data JPA. A `DataSeeder` (`CommandLineRunner`) inserts courses and the two
staff users (section 3) if missing, with `BCryptPasswordEncoder` (bean of that exact type).

**Security:**
- Form login at `/login` for web pages; logout at `/logout`.
- `/exams/**` → INSTRUCTOR or ADMIN. `/admin/**` → ADMIN.
- REST `/api/**`: HTTP Basic, `GET /api/exams/upcoming` is `permitAll` (the resilience core reads
  it; data is not sensitive). Write endpoints need INSTRUCTOR or ADMIN. CSRF disabled for
  `/api/**` only.
- `/actuator/health` and `/actuator/prometheus` are `permitAll`; other actuator endpoints ADMIN.

**Web pages (Thymeleaf, one shared layout, simple clean CSS, responsive):**

| Path | Role | Content |
|---|---|---|
| `/login` | all | Login form |
| `/` | staff | Welcome, counts (courses, upcoming exams), links |
| `/exams` | INSTRUCTOR, ADMIN | Table of upcoming exams; delete button (POST with CSRF) |
| `/exams/new` | INSTRUCTOR, ADMIN | Form: course dropdown, start (datetime-local), duration, expected students, topics; validation errors shown next to fields |
| `/admin/live` | ADMIN | Current degradation level, breaker state and exam mode read from Redis (`cs:mode:level`, `cs:breaker:llm`, `cs:mode:exam`) and the last 20 entries of the `cs:actions` stream (XREVRANGE), auto-refresh every 5 s with a meta refresh or tiny fetch |
| `/admin/users` | ADMIN | List staff users; form to add an instructor |

**REST API (for Postman and the resilience core):**

| Method, path | Auth | Body / result |
|---|---|---|
| `GET /api/courses` | Basic | list |
| `GET /api/exams` | Basic | all exams |
| `GET /api/exams/upcoming` | public | exams whose end is in the future, JSON `[{id, course, start (ISO 8601 with offset), duration_min, expected_students, topics: [..]}]` — **this exact shape is used in Phase G** |
| `POST /api/exams` | Basic | create (validated, 400 with field errors as JSON) |
| `PUT /api/exams/{id}` | Basic | update |
| `DELETE /api/exams/{id}` | Basic | 204 |

**Tests:** one `@SpringBootTest` + `MockMvc` class: upcoming is public; POST without auth → 401;
POST with instructor basic auth and a valid body → 201; invalid body → 400.

**Postman:** `web/staff-portal/postman/CascadeShield.postman_collection.json` with a collection
variable `baseUrl` (`http://localhost:8085`), Basic auth at collection level using the instructor
account, requests for every REST endpoint, and a `pm.test` status-code check in each.

**Check D**
- [ ] `./mvnw spring-boot:run` (dev) starts; login works; an exam can be created through the form.
- [ ] `./mvnw test` passes.
- [ ] On Fedora with `-Dspring-boot.run.profiles=prod`, tables appear in MySQL and `/admin/live` shows real Redis values from the Mac.
- [ ] Postman collection runs green (Collection Runner).
- [ ] `curl localhost:8085/actuator/prometheus` returns metrics.

---

### Phase E — Status page: Servlet + JSP on Tomcat (about 3 hours)

Folder `web/status-page`. Maven WAR, `jakarta.servlet-api` 6.0 (provided),
`jakarta.servlet.jsp.jstl` (Glassfish JSTL 3.0 impl + API), `mysql-connector-j`, `h2` (dev),
Java 21. Final name `status.war` → served at `http://<fedora>:8080/status/`.
Package `edu.vit.cascadeshield.status`.

**Components (classic MVC):**

- `StatusBean` (JavaBean: getters/setters, no-arg constructor): `level`, `levelName`, `banner`,
  `color`, `examActive`, `examCourse`, `coreHealthy`, `risk` (LLM risk from core `/state` if
  present), `checkedAt`.
- `StatusPoller` (`@WebListener ServletContextListener`): on `contextInitialized` starts a
  single-thread `ScheduledExecutorService` every 5 s: `GET {GATEWAY_URL}/api/status` and
  `GET {CORE_URL}/state` with `java.net.http.HttpClient` (2 s timeout). Builds a `StatusBean`,
  stores it in an `AtomicReference` in the servlet context. If the level changed since the last
  poll, inserts a row into `status_history`. On `contextDestroyed` shuts the executor down.
  (Shows servlet lifecycle and concurrency.)
- `Db` helper: JDBC `DriverManager` with URL/user/password from env
  (`STATUS_DB_URL` default `jdbc:mysql://localhost:3306/cascadeshield_web`, `MYSQL_USER`,
  `MYSQL_PASSWORD`); try-with-resources everywhere; `PreparedStatement` only.
- `StatusServlet` (`@WebServlet("/")`): reads the bean and the last 20 history rows, computes
  "healthy share of the last 24 h" (share of time at level 0–1), sets request attributes, forwards
  to `/WEB-INF/jsp/status.jsp`. Increments a visit counter in the `HttpSession` and shows it.
- `ThemeServlet` (`@WebServlet("/theme")`): toggles a `theme` cookie (`light`/`dark`, 30 days)
  and redirects back using `response.encodeRedirectURL` (URL rewriting when cookies are off).
- `status.jsp`: JSTL only (`c:forEach`, `c:choose`, `fmt:formatDate`), no Java scriptlets. Big
  coloured current-status card, exam badge, "Control room: online/offline", history table, theme
  toggle link built with `<c:url>`. Meta refresh every 10 s. Responsive CSS in the page.

`web/sql/schema.sql`:

```sql
CREATE TABLE IF NOT EXISTS status_history (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  level INT NULL,
  banner VARCHAR(200) NOT NULL,
  exam_active BOOLEAN NOT NULL,
  changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

Env vars on Fedora: `GATEWAY_URL=http://<mac-ip>:8000`, `CORE_URL=http://localhost:8600`. Set them
in Tomcat's `bin/setenv.sh` (document this in `web/README.md`).

**Check E**
- [ ] `./mvnw package` builds `target/status.war`; copying it to Tomcat `webapps/` serves `/status/`.
- [ ] Changing the level on the Mac adds a history row within 5 s and the page shows it.
- [ ] Stopping the resilience core shows "Control room: offline" while the platform status still shows.
- [ ] Theme cookie persists across reloads; no scriptlets in the JSP.

---

### Phase F — Notes uploader: PHP 8 (about 3 hours)

Folder `web/notes-uploader`. Plain PHP 8 (no framework, no Composer packages). Run with
`php -S 0.0.0.0:8070 -t public`.

```
notes-uploader/
├── config.php        env vars: MYSQL_*, RAG_URL (http://<mac-ip>:8003), CS_TOKEN
├── lib/db.php        PDO (ERRMODE_EXCEPTION), helper functions
├── lib/auth.php      session start, login check, CSRF token helpers
├── lib/rag.php       sendToRag(course, topic, markdown) with curl or file_get_contents + stream context
├── public/index.php  upload form + list of past uploads (requires login)
├── public/login.php  login form
├── public/logout.php
├── public/upload.php POST handler (redirect back with flash message)
├── uploads/          saved files (gitignored)
└── outbox/           "sent" notification e-mails as .eml text files (gitignored)
```

**Behaviour:**

- **Login:** checks `staff_user` (shared with Spring Boot) using `password_verify()`. Starts a
  session (`session_regenerate_id(true)` on login). "Remember my email" checkbox sets an
  `uploader_email` cookie (30 days) that pre-fills the form.
- **Upload form:** course (`<select>` of DSA101, DBMS201, OS202), topic slug, either a `.md`/`.txt`
  file **or** pasted Markdown, and an optional "notify e-mail" field. CSRF token in a hidden field.
- **Validation (server side, show all errors at once):** course in the list; topic matches
  `^[a-z0-9_]{2,40}$`; file ≤ 200 KB with extension `.md` or `.txt` and `text/plain` or
  `text/markdown` MIME (use `finfo`); content contains at least one `## ` heading; notify e-mail
  passes `filter_var(..., FILTER_VALIDATE_EMAIL)` when given.
- **On valid upload:** save to `uploads/<course>/<topic>-<timestamp>.md` (`move_uploaded_file`),
  call `sendToRag()` → `POST {RAG_URL}/admin/notes` with `X-CS-Token`, insert a row into
  `note_upload`, and if a notify address was given write a plain-text e-mail file into `outbox/`
  ("New notes for DSA101: tries"). Show a flash message with the number of chunks indexed.
  Wrap the RAG call and DB insert in `try/catch`; if the RAG is unreachable, keep the file, store
  status `pending`, and show a clear warning.
- **List:** table of the last 20 uploads (course, topic, uploader, time, status, chunks) using
  string and array functions to format sizes and dates.

`web/sql/schema.sql` (append):

```sql
CREATE TABLE IF NOT EXISTS note_upload (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  course VARCHAR(16) NOT NULL,
  topic VARCHAR(40) NOT NULL,
  filename VARCHAR(255) NOT NULL,
  uploaded_by VARCHAR(120) NOT NULL,
  status VARCHAR(16) NOT NULL,          -- indexed | pending | failed
  chunks INT NULL,
  uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**Check F**
- [ ] Login with the instructor account works; wrong password shows an error.
- [ ] Uploading `tries.md` for DSA101 shows "indexed, N chunks"; asking the tutor at level 2 ("what is a trie") in the student portal returns text from that file.
- [ ] Invalid inputs (bad slug, `.exe`, too large, bad e-mail) show errors and save nothing.
- [ ] With the Mac unreachable, the upload is saved with status `pending`.

---

### Phase G — Integration (about 1.5 hours)

1. **Exam calendar sync (resilience core).** In `control/resilience_core/main.py`, add an async
   task `sync_staff_exams()` that runs every 30 s **only if `STAFF_PORTAL_URL` is set**: `GET
   {STAFF_PORTAL_URL}/api/exams/upcoming` (timeout 2 s). For each item build an `Exam` (topics
   list, start parsed with `datetime.fromisoformat`). Call `self.calendar.add(exam, now)` **only
   when `exam.id` is not already in `self.calendar.exams`** (re-adding resets progress). Log and
   ignore all errors. Pass `STAFF_PORTAL_URL` into the control containers in
   `control/compose.yml` (`${STAFF_PORTAL_URL:-}`); on Fedora use
   `http://host.docker.internal:8085`. Add one unit test in `control/tests/test_calendar.py` for
   "already known exam is not re-added".
2. **Prometheus monitors the staff portal.** In `control/prometheus/prometheus.yml` add a job
   `staff_portal` with `metrics_path: /actuator/prometheus`, target `host.docker.internal:8085`.
   Missing target must not break anything else.
3. **Links.** The student portal footer links to the public status page URL
   (`VITE_STATUS_URL`, default empty = hidden). The staff portal home links to the status page,
   the notes uploader and the Streamlit dashboard (URLs from config properties).
4. **`scripts/demo.sh`:** add a preflight line "student portal :3000 responds" and start the
   portal (`node src/index.js` in the background, log to `.demo.log`) after the platform is up;
   stop it in `--stop`. Do not change existing behaviour.

**Check G**
- [ ] Create an exam in the staff portal starting in 3 minutes → within 30 s the Streamlit dashboard lists it → pre-warm and exam mode fire on time → student banner shows exam mode.
- [ ] Prometheus target `staff_portal` is UP.
- [ ] `scripts/demo.sh` starts the student portal; `--stop` stops it.

---

### Phase H — Docs, tests, demo (about 2 hours)

1. `web/README.md`: per component, prerequisites, env vars, run commands for dev (Mac) and prod
   (Fedora), demo accounts, troubleshooting (ports busy, CORS, MySQL access denied, Tomcat env).
2. `web/SYLLABUS_MAP.md`: table *Unit → syllabus topic → where it is in our code (file path) →
   one-line explanation*. Cover every topic we actually used; mark topics we did not use
   (Flux, SSR, Laravel, Messaging) as "not used, reason: …". Honest, no stretching.
3. `web/student-portal/client`: two Vitest + React Testing Library tests (`LevelBadge` renders
   the right label per level; `useIdempotentSubmit` reuses the same key on retry).
4. One Node test file with `node:test` + `supertest` (add as dev dependency): `/api/*` without a
   cookie → 401; login with a wrong password → 401.
5. Update the root `README.md` table with a `web/` row (one line).
6. Fill in section 7's demo script with real URLs in `web/README.md`.

---

## 6. Acceptance (the whole web layer is done when)

- [ ] A student can register, log in, chat with level badges, take a practice quiz and submit a graded quiz on a phone.
- [ ] The banner changes live during a Locust exam ramp with no page reload.
- [ ] An instructor schedules an exam in the Spring Boot portal and CascadeShield acts on it.
- [ ] An instructor uploads notes in PHP and the tutor uses them.
- [ ] The JSP status page shows the live state and history and keeps working while the React portal is stopped.
- [ ] No secret appears in any browser-visible response, page or bundle (`grep -r CS_TOKEN client/dist` finds nothing).
- [ ] All existing platform and control tests still pass.

---

## 7. Demo script (about 8 minutes, two people)

1. **(Fedora)** Staff portal → log in as instructor → schedule a DSA101 exam in 3 minutes.
   Mention Spring Security roles, JPA + MySQL, Bean Validation.
2. **(Fedora)** Notes uploader → upload `tries.md` → "indexed, N chunks". Mention PHP sessions,
   file handling, validation, PDO.
3. **(Mac / projector)** Student portal → log in → ask "what is a trie?" → AI Tutor answer.
   Ask evaluators to scan the QR code and log in on their phones with `s0002…s0010`.
4. **(Fedora)** Streamlit dashboard: the exam appears, pre-warm fires. Start the Locust
   `exam_ramp`.
5. **(Mac)** Banner turns amber then blue, badges change to Light mode / Course notes / Hint,
   a queued toast may appear. Submit the graded quiz: "Submitted ✓". Open the network inspector
   (Ctrl+Shift+D): show request ids, live events, tutor vs quiz latency.
6. **(Fedora)** Dashboard: risk crossing the threshold before the latency SLO, SHAP reasons.
7. **(Any browser)** Status page `/status/`: history rows of each level change. Stop the React
   portal for a moment: the status page still works (that is why it is server-rendered and
   separate).
8. Postman Collection Runner: all green.

---

## 8. Instructions for Claude Code on how to work

- Create a task list from the phases above, in order A, B, C, D, E, F, G, H. Mark each check item.
- Phases D, E and F do not depend on B or C; if you can run work in parallel, D/E/F may be built
  alongside B/C. Phase F's RAG call needs Phase A merged first.
- Commit after each phase with a message like `web: phase B express server`.
- Use the existing code style. Do not reformat existing files.
- Never put real secrets in committed files; use `.env` and `.env.example`.
- When a check cannot be run in this environment (for example it needs MySQL or the Mac's
  Ollama), say so in `web/NOTES.md` and give the exact command the user should run.
- If a library version named here is unavailable, use the nearest stable version and note it.
