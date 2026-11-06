import bcrypt from 'bcryptjs';
import jwt from 'jsonwebtoken';
import { JWT_SECRET } from './config.js';

export const COOKIE = 'cs_auth';
export const COOKIE_OPTIONS = { httpOnly: true, sameSite: 'lax', secure: false }; // secure off: local HTTP demo
const EIGHT_HOURS_MS = 8 * 3600 * 1000;

export const hashPassword = (password) => bcrypt.hash(password, 10);
export const verifyPassword = (password, hash) => bcrypt.compare(password, hash);

export function setAuthCookie(res, user) {
  const claims = { sub: user.student_id, name: user.name, email: user.email, course: user.course };
  const token = jwt.sign(claims, JWT_SECRET, { algorithm: 'HS256', expiresIn: '8h' });
  res.cookie(COOKIE, token, { ...COOKIE_OPTIONS, maxAge: EIGHT_HOURS_MS });
}

export function verifyToken(token) {
  try {
    return jwt.verify(token, JWT_SECRET, { algorithms: ['HS256'] });
  } catch {
    return null;
  }
}

export function requireAuth(req, res, next) {
  req.user = verifyToken(req.cookies?.[COOKIE]);
  if (!req.user) return res.status(401).json({ detail: 'Please log in' });
  next();
}
