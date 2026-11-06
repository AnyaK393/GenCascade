# CascadeShield web layer

Four web applications around the finished platform. Exam-critical parts stay on the Mac, so students
can log in, ask questions and submit quizzes with Fedora switched off.

| Part | Machine | URL | Technology |
| --- | --- | --- | --- |
| Student portal | Mac | `http://<mac-ip>:3000/` | React, Redux Toolkit, Express, Socket.IO, SQLite |
| Staff portal | Fedora | `http://<fedora-ip>:8085/` | Spring Boot, Thymeleaf, JPA, MySQL |
| Status page | Fedora | `http://<fedora-ip>:8080/status/` | Servlet, JSP, JSTL, JDBC, Tomcat 10.1 |
| Notes uploader | Fedora | `http://<fedora-ip>:8070/` | PHP 8, PDO, MySQL |

See `SYLLABUS_MAP.md` for the unit-by-unit map and `NOTES.md` for decisions and known limits.

## Demo accounts

| Who | Login | Password | Where |
| --- | --- | --- | --- |
| Students | `s0001@student.vit.edu` … `s0010@student.vit.edu` | `student123` | Student portal |
| Instructor | `instructor@vit.edu` | `instructor123` | Staff portal, notes uploader |
| Admin | `admin@vit.edu` | `admin123` | Staff portal, notes uploader |

All accounts are created automatically on first start. The uploader shares the staff portal's
accounts, so start the staff portal once before using it.

## Environment variables

Copy the `# --- web layer ---` block of `.env.example` into your `.env` and set real values. Secrets
are read on the server only and never reach a browser.

| Variable | Used by | Meaning |
| --- | --- | --- |
| `JWT_SECRET` | Express | Signs student logins. If unset, a random key is used and logins end on restart. |
| `GATEWAY_URL`, `STUDENT_URL` | Express, status page | Platform addresses. On Fedora, `GATEWAY_URL` must use the Mac's IP. |
| `CORE_URL` | Staff portal, status page | Resilience core, default `http://localhost:8600` |
| `CS_TOKEN` | Staff portal, uploader | Same token as the rest of the project |
| `MYSQL_HOST`, `MYSQL_DB`, `MYSQL_USER`, `MYSQL_PASSWORD` | All Fedora parts | MySQL connection |
| `RAG_URL` | Uploader | `http://<mac-ip>:8003` |
| `STATUS_PAGE_URL`, `NOTES_URL`, `DASHBOARD_URL` | Staff portal | Links on the home page |
| `VITE_STATUS_URL` | Client build | Footer link to the status page; empty hides it |

## Student portal (Mac)

Needs Node 20 or newer.

```bash
cd web/student-portal/client && npm ci
VITE_STATUS_URL=http://<fedora-ip>:8080/status/ npm run build
cd ../server && npm ci && npm start          # http://localhost:3000
```

`scripts/demo.sh` starts the portal for you once it is built, and `scripts/demo.sh --stop` stops it.

For development, run `npm run dev` in `server/` and in `client/` (Vite on port 5173, proxied to 3000).

Add `?debug=1` to any URL or press Ctrl+Shift+D for the network inspector.

## Fedora setup (once)

```bash
sudo dnf install java-21-openjdk-devel community-mysql-server php-cli php-mysqlnd
sudo systemctl enable --now mysqld
# Edit the password in web/sql/schema.sql to match MYSQL_PASSWORD, then:
sudo mysql < web/sql/schema.sql
# Open the ports (also needed so other devices can reach these pages):
sudo firewall-cmd --add-port={8085,8080,8070}/tcp --permanent && sudo firewall-cmd --reload
timedatectl    # must show your real time zone: the exam form uses the server's zone
```

Tomcat 10.1 comes from https://tomcat.apache.org (unpack the tar.gz into `~/tomcat`).

On the Mac, allow `node` when macOS asks to accept incoming connections (or System Settings ->
Network -> Firewall -> Options).

Load the settings in each terminal before running the commands below. Do this rather than expecting
the apps to read `.env`: its inline comments would become part of the values.

```bash
set -a; . ./.env; set +a
```

## Staff portal

```bash
cd web/staff-portal
./mvnw spring-boot:run                                       # Mac, dev: in-memory H2
./mvnw spring-boot:run -Dspring-boot.run.profiles=prod       # Fedora: MySQL
./mvnw test
```

Postman: import `postman/CascadeShield.postman_collection.json` and use the Collection Runner. Its
test exam is dated 30 days ahead because every created exam is also sent to the resilience core,
which cannot unschedule it.

## Status page

Set the environment in `~/tomcat/bin/setenv.sh`:

```bash
export GATEWAY_URL=http://<mac-ip>:8000
export CORE_URL=http://localhost:8600
export MYSQL_USER=csweb
export MYSQL_PASSWORD=<your password>
```

Then build and deploy:

```bash
cd web/status-page && ./mvnw package
cp target/status.war ~/tomcat/webapps/
~/tomcat/bin/startup.sh
```

To try it without MySQL, add `export STATUS_DB_URL='jdbc:h2:mem:status;DB_CLOSE_DELAY=-1;MODE=MySQL'`.

## Notes uploader

```bash
cd web/notes-uploader
RAG_URL=http://<mac-ip>:8003 php -S 0.0.0.0:8070 -t public
```

Uploaded files stay in `uploads/`, outside the web root. "Sent" notifications are text files in
`outbox/`.

## Troubleshooting

| Problem | Fix |
| --- | --- |
| Port already in use | `lsof -i :3000` (Mac) or `ss -ltnp \| grep 8085` (Fedora), then stop that process |
| Browser shows a CORS error in dev | Open `http://localhost:5173`, not `127.0.0.1` |
| Banner does not follow `POST /control/mode` | The level only applies while the control room's heartbeat is fresh; start the resilience core |
| `Access denied for user 'csweb'` | `MYSQL_PASSWORD` differs from the one in `schema.sql`, or `.env` was not loaded in this terminal |
| Status page shows "History is unavailable" | Variables missing from `setenv.sh`; restart Tomcat after changing them |
| "Saved, but CascadeShield was not notified" | Resilience core down, or `CS_TOKEN` differs between machines. The exam is saved but must be created again to reach the core. |
| Uploads stay `Pending` | The RAG service was unreachable. Check `RAG_URL` and upload again. |
| Exam starts at the wrong time | Fedora's time zone is wrong; check `timedatectl` |

## Demo script (about 8 minutes, two people)

Start with `scripts/demo.sh` on the Mac and the control room plus the three Fedora parts on Fedora.

1. **Fedora:** `http://<fedora-ip>:8085/` -> log in as instructor -> schedule a DSA101 exam 3 minutes
   ahead. Mention Spring Security roles, JPA + MySQL, Bean Validation.
2. **Fedora:** `http://<fedora-ip>:8070/` -> upload `tries.md` -> "Indexed, N chunks". Mention PHP
   sessions, file handling, validation, PDO.
3. **Mac / projector:** `http://<mac-ip>:3000/` -> log in -> ask "what is a trie?". Evaluators log in
   on their phones with `s0002` … `s0010`.
4. **Fedora:** `http://<fedora-ip>:8501/`: the exam appears and pre-warm fires. Start the Locust
   `exam_ramp` from `http://<fedora-ip>:8089/`.
5. **Mac:** the banner turns amber then blue, and badges change to Light mode, Course notes, Hint. A
   queued toast may appear. Submit the graded quiz: "Submitted ✓". Press Ctrl+Shift+D: show request
   ids, live events and latency per request.
6. **Fedora:** dashboard: risk crosses the threshold before the latency SLO, with SHAP reasons.
7. **Any browser:** `http://<fedora-ip>:8080/status/`: a history row for each level change. Stop the
   student portal for a moment: the status page keeps working.
8. Postman Collection Runner: all green.
