import crypto from 'node:crypto';
import { Router } from 'express';
import rateLimit from 'express-rate-limit';
import { z } from 'zod';
import { COOKIE, COOKIE_OPTIONS, hashPassword, requireAuth, setAuthCookie, verifyPassword } from '../auth.js';
import { COURSES } from '../config.js';
import { db } from '../db.js';

const router = Router();
const limiter = rateLimit({
  windowMs: 5 * 60 * 1000,
  limit: 10,
  standardHeaders: true,
  legacyHeaders: false,
  message: { detail: 'Too many attempts. Try again in a few minutes.' },
});

const email = z.string().trim().toLowerCase().pipe(z.email('Enter a valid e-mail address'));
const registerBody = z.object({
  name: z.string().trim().min(1, 'Enter your name').max(80),
  email,
  password: z.string().min(8, 'Password must be at least 8 characters').max(72, 'Password must be at most 72 characters'),
  course: z.enum(COURSES, 'Choose a course'),
});
const loginBody = z.object({ email, password: z.string().max(72) });

// bcrypt also runs for unknown e-mails, so response time does not reveal which accounts exist.
const DUMMY_HASH = await hashPassword(crypto.randomUUID());

const FIRST_ID = 11;
const LAST_ID = 1499; // platform students stop at s1499
const insertUser = db.transaction((user) => {
  if (db.prepare('SELECT 1 FROM users WHERE email = ?').get(user.email)) return null;
  const used = new Set(db.prepare('SELECT student_id FROM users').pluck().all());
  for (let i = FIRST_ID; i <= LAST_ID; i++) {
    const student_id = `s${String(i).padStart(4, '0')}`;
    if (!used.has(student_id)) {
      db.prepare('INSERT INTO users (email, name, student_id, course, password_hash) VALUES (?, ?, ?, ?, ?)')
        .run(user.email, user.name, student_id, user.course, user.password_hash);
      return { ...user, student_id };
    }
  }
  throw Object.assign(new Error('No student ids left'), { status: 503 });
});

router.post('/register', limiter, async (req, res) => {
  const body = registerBody.safeParse(req.body);
  if (!body.success) return res.status(400).json({ detail: body.error.issues[0].message });
  const { password, ...fields } = body.data;
  const user = insertUser({ ...fields, password_hash: await hashPassword(password) });
  if (!user) return res.status(409).json({ detail: 'This e-mail is already registered' });
  setAuthCookie(res, user);
  res.status(201).json({ student_id: user.student_id, name: user.name, email: user.email, course: user.course });
});

router.post('/login', limiter, async (req, res) => {
  const body = loginBody.safeParse(req.body);
  if (!body.success) return res.status(401).json({ detail: 'Wrong e-mail or password' });
  const user = db.prepare('SELECT * FROM users WHERE email = ?').get(body.data.email);
  const ok = await verifyPassword(body.data.password, user?.password_hash ?? DUMMY_HASH);
  if (!user || !ok) return res.status(401).json({ detail: 'Wrong e-mail or password' });
  setAuthCookie(res, user);
  res.json({ student_id: user.student_id, name: user.name, email: user.email, course: user.course });
});

router.post('/logout', (req, res) => {
  res.clearCookie(COOKIE, COOKIE_OPTIONS);
  res.json({ ok: true });
});

router.get('/me', requireAuth, (req, res) => {
  const { sub, name, email: mail, course, exp } = req.user;
  res.json({ student_id: sub, name, email: mail, course, exp });
});

export default router;
