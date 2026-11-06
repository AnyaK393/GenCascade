import crypto from 'node:crypto';
import { fileURLToPath } from 'node:url';
import dotenv from 'dotenv';

dotenv.config({ path: fileURLToPath(new URL('../../../../.env', import.meta.url)), quiet: true });

export const PORT = Number(process.env.PORT || 3000);
export const GATEWAY_URL = process.env.GATEWAY_URL || 'http://localhost:8000';
export const STUDENT_URL = process.env.STUDENT_URL || 'http://localhost:8001';
export const COURSES = ['DSA101', 'DBMS201', 'OS202'];
export const IS_PROD = process.env.NODE_ENV === 'production';

// No hard-coded fallback: a known key would let anyone forge a login. A random one only logs people out on restart.
export const JWT_SECRET = process.env.JWT_SECRET || crypto.randomBytes(32).toString('hex');
if (!process.env.JWT_SECRET) console.warn('JWT_SECRET not set: using a random key, logins end when the server restarts');
