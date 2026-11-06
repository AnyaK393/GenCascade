# Syllabus map

Where each Web Technology topic is used in this project. Paths are relative to `web/`.

## Unit I: PHP (`notes-uploader/`)

| Topic | Where | What it does |
| --- | --- | --- |
| Forms and validation | `public/upload.php` | Server-side checks; all errors shown at once |
| File handling | `public/upload.php` | `move_uploaded_file`, `file_put_contents`, `finfo` MIME check |
| Sessions | `lib/auth.php`, `public/login.php` | Login state, `session_regenerate_id` on login, flash messages |
| Cookies | `public/login.php` | "Remember my e-mail" cookie for 30 days |
| Database with PDO | `lib/db.php` | Prepared statements on MySQL |
| Functions, strings, arrays | `public/index.php` | `format_size`, `array_map`, `date`, `str_replace` for the upload table |
| Exceptions | `public/upload.php` | The file is kept as `pending` when the RAG service is unreachable |
| Mail | `public/upload.php` | Writes notification e-mails as `.eml` files; no mail server is used |
| Laravel | not used | Reason: the plan asks for plain PHP to show the basics |

## Unit II: React (`student-portal/client/`)

| Topic | Where | What it does |
| --- | --- | --- |
| Components and props | `src/components/QuestionCard.tsx` | One question; passes the choice to its parent through a callback |
| State | `src/pages/QuizPage.tsx` | Answers, current step, submit state |
| Controlled forms | `src/pages/LoginPage.tsx`, `RegisterPage.tsx` | Inline validation |
| Lists and keys | `src/pages/TutorPage.tsx` | Chat messages keyed by id |
| Conditional rendering | `src/components/StatusBanner.tsx` | Exam badge and colour from live status |
| Hooks | `src/pages/TutorPage.tsx` | `useState`, `useEffect`, `useRef` for focus and scrolling |
| Styling | `src/index.css`, `tailwind.config.js` | Tailwind, responsive from 375 px |

## Unit III: Servlet and JSP (`status-page/`)

| Topic | Where | What it does |
| --- | --- | --- |
| Servlet | `src/main/java/.../StatusServlet.java` | Controller: gathers data, forwards to the JSP |
| Servlet lifecycle, listener | `src/main/java/.../StatusPoller.java` | Starts and stops the poller with the context |
| JavaBean | `src/main/java/.../StatusBean.java` | The model the JSP reads |
| MVC | `StatusServlet`, `StatusBean`, `status.jsp` | Controller, model, view |
| JSP and JSTL | `src/main/webapp/WEB-INF/jsp/status.jsp` | `c:forEach`, `c:choose`, `fmt:formatDate`; no scriptlets |
| JDBC | `src/main/java/.../Db.java` | `PreparedStatement`, try-with-resources |
| Sessions | `StatusServlet.java` | Visit counter |
| Cookies, URL rewriting | `src/main/java/.../ThemeServlet.java` | Theme cookie; `encodeRedirectURL` |
| Concurrency | `StatusPoller.java` | `ScheduledExecutorService`, `AtomicReference` |

## Unit IV: Spring Boot (`staff-portal/`)

| Topic | Where | What it does |
| --- | --- | --- |
| Auto-configuration, profiles | `src/main/resources/application*.properties` | `dev` uses H2, `prod` uses MySQL |
| Spring MVC | `src/main/java/.../web/ExamController.java` | Thymeleaf pages |
| REST | `src/main/java/.../web/ApiController.java` | CRUD API for exams |
| Spring Data JPA | `src/main/java/.../repo/`, `model/` | Entities and repositories on MySQL |
| Bean Validation | `src/main/java/.../model/Exam.java` | Rules shared by the form and the API |
| Spring Security | `src/main/java/.../SecurityConfig.java` | Form login, HTTP Basic, roles, BCrypt |
| Dependency injection | `src/main/java/.../service/ExamService.java` | Constructor injection |
| Actuator | `application.properties` | `/actuator/health` |
| Testing | `src/test/java/.../ExamApiTest.java` | `@SpringBootTest` with `MockMvc` |
| Postman | `postman/CascadeShield.postman_collection.json` | Every endpoint, with tests |
| Redis, Prometheus metrics | not used | Reason: cut from the lean scope to reduce integration risk |

## Unit V: Advanced React (`student-portal/client/`)

| Topic | Where | What it does |
| --- | --- | --- |
| TypeScript | `src/types/api.ts`, `tsconfig.json` | Strict mode; typed API responses |
| Redux Toolkit | `src/store/*Slice.ts` | Auth, live status, chat, inspector state |
| RTK Query | `src/store/api.ts` | All server calls; polling for queued answers |
| React Router | `src/routes.tsx` | Nested routes, `RequireAuth` guard |
| Code splitting | `src/routes.tsx` | `React.lazy` and `Suspense` per page |
| Custom hooks | `src/hooks/` | `useLiveStatus`, `useIdempotentSubmit`, `useQueuedAnswer` |
| Context | `src/components/Toast.tsx` | Toast system |
| Class components, error boundaries | `src/components/ErrorBoundary.tsx` | `componentDidCatch` |
| Memoisation | `src/components/ChatMessage.tsx` | `React.memo` |
| Flux | not used directly | Reason: Redux Toolkit replaces hand-written Flux stores |
| Server-side rendering | not used | Reason: the portal is a client-rendered SPA served by Express |

## Unit VI: Node.js (`student-portal/server/`)

| Topic | Where | What it does |
| --- | --- | --- |
| ES modules | `src/` | One module per concern |
| Express and middleware | `src/index.js` | Helmet, logging, JSON, cookies, CORS, error handler |
| Routing | `src/routes/auth.js`, `src/routes/api.js` | Login and proxy routes |
| Authentication | `src/auth.js` | BCrypt, JWT in an `httpOnly` cookie |
| Input validation | `src/routes/auth.js` | zod schemas |
| Rate limiting | `src/routes/auth.js` | `express-rate-limit` on login and register |
| Database | `src/db.js` | SQLite through `better-sqlite3` |
| Filesystem and streams | `src/index.js` | Access log through a write stream |
| Calling other services | `src/routes/api.js` | `fetch` with timeouts to FastAPI |
| WebSockets | `src/liveStatus.js`, `src/index.js` | Socket.IO live status with cookie authentication |
| Messaging | not used | Reason: services here talk over HTTP and Socket.IO; no message broker is needed |
