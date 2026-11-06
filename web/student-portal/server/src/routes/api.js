import crypto from 'node:crypto';
import { readFileSync } from 'node:fs';
import { Router } from 'express';
import { z } from 'zod';
import { requireAuth } from '../auth.js';
import { COURSES, GATEWAY_URL, STUDENT_URL } from '../config.js';
import { getStatus } from '../liveStatus.js';

const quizzes = JSON.parse(readFileSync(new URL('../quizzes.json', import.meta.url)));

const router = Router();
router.use(requireAuth);

const askBody = z.object({
  course: z.enum(COURSES),
  question: z.string().trim().min(1).max(2000),
  session_id: z.string().max(64).optional(),
});
const submitBody = z.object({
  quiz_id: z.enum(COURSES.map((c) => `${c}-quiz1`)),
  answers: z.union([z.record(z.string(), z.string()), z.array(z.unknown())]),
  idempotency_key: z.uuid(),
});
const practiceBody = z.object({ answers: z.array(z.number().int().nullable()).max(50) });

function parse(schema, req, res) {
  const body = schema.safeParse(req.body);
  if (!body.success) res.status(400).json({ detail: body.error.issues[0].message });
  return body.success ? body.data : null;
}

/** Calls an upstream FastAPI service. Non-JSON bodies become {detail}; throws on network failure or timeout. */
async function upstream(url, timeoutMs, body) {
  const r = await fetch(url, {
    method: body ? 'POST' : 'GET',
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
    signal: AbortSignal.timeout(timeoutMs),
  });
  const text = await r.text();
  try {
    return { status: r.status, data: JSON.parse(text) };
  } catch {
    return { status: r.status, data: { detail: text } };
  }
}

router.post('/tutor/ask', async (req, res) => {
  const body = parse(askBody, req, res);
  if (!body) return;
  const t0 = performance.now();
  let result;
  try {
    result = await upstream(`${GATEWAY_URL}/api/tutor/ask`, 30000, { ...body, student_id: req.user.sub });
  } catch {
    result = { status: 504, data: { detail: 'Tutor unavailable. Try again in a moment.' } };
  }
  res.status(result.status).json({
    ...result.data,
    request_id: crypto.randomUUID(),
    latency_ms: Math.round(performance.now() - t0),
  });
});

router.get('/tutor/queued/:qid', async (req, res) => {
  try {
    const { status, data } = await upstream(`${GATEWAY_URL}/api/tutor/queued/${encodeURIComponent(req.params.qid)}`, 5000);
    res.status(status).json(data);
  } catch {
    res.status(504).json({ detail: 'Tutor unavailable' });
  }
});

router.post('/quiz/submit', async (req, res) => {
  const body = parse(submitBody, req, res);
  if (!body) return;
  try {
    const { status, data } = await upstream(`${GATEWAY_URL}/api/quiz/submit`, 5000, { ...body, student_id: req.user.sub });
    res.status(status).json(data);
  } catch {
    res.status(503).json({ status: 'failed', detail: 'retry with the same idempotency_key' });
  }
});

function courseQuiz(req, res) {
  if (Object.hasOwn(quizzes, req.params.course)) return quizzes[req.params.course];
  res.status(404).json({ detail: 'Unknown course' });
  return null;
}

router.get('/quizzes/:course', (req, res) => {
  const quiz = courseQuiz(req, res);
  if (!quiz) return;
  res.json({
    course: req.params.course,
    quiz_id: `${req.params.course}-quiz1`,
    questions: quiz.map(({ question, options }) => ({ question, options })),
  });
});

router.post('/quizzes/:course/practice', (req, res) => {
  const quiz = courseQuiz(req, res);
  const body = quiz && parse(practiceBody, req, res);
  if (!body) return;
  const status = getStatus();
  // level null: the gateway is unreachable, so an exam may be running. Practice replies contain the answers.
  if (status.level === null) return res.status(503).json({ detail: 'Cannot confirm that no exam is running. Try again shortly.' });
  if (status.exam?.active && status.exam.course === req.params.course) {
    return res.status(403).json({ detail: 'Practice is closed during the exam for this course' });
  }
  const results = quiz.map((q, index) => ({ index, correct: body.answers[index] === q.answer, correct_option: q.answer }));
  res.json({ score: results.filter((r) => r.correct).length, total: quiz.length, results });
});

router.get('/profile', async (req, res) => {
  try {
    const { status, data } = await upstream(`${STUDENT_URL}/profile/${encodeURIComponent(req.user.sub)}`, 2000);
    res.json(status === 200 ? { available: true, ...data } : { available: false });
  } catch {
    res.json({ available: false });
  }
});

router.get('/status', (req, res) => res.json(getStatus()));

router.use((req, res) => res.status(404).json({ detail: 'Not found' }));

export default router;
