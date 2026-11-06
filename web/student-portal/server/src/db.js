import fs from 'node:fs';
import { fileURLToPath } from 'node:url';
import bcrypt from 'bcryptjs';
import Database from 'better-sqlite3';
import { COURSES } from './config.js';

const DATA = fileURLToPath(new URL('../data/', import.meta.url));
fs.mkdirSync(DATA, { recursive: true });

export const db = new Database(`${DATA}portal.db`);
db.pragma('journal_mode = WAL');
db.exec(`CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  email TEXT UNIQUE NOT NULL,
  name TEXT NOT NULL,
  student_id TEXT UNIQUE NOT NULL,
  course TEXT NOT NULL,
  password_hash TEXT NOT NULL,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
)`);

export function seed() {
  if (db.prepare("SELECT 1 FROM users WHERE student_id = 's0001'").get()) return 0;
  const insert = db.prepare('INSERT OR IGNORE INTO users (email, name, student_id, course, password_hash) VALUES (?, ?, ?, ?, ?)');
  const hash = bcrypt.hashSync('student123', 10);
  for (let i = 1; i <= 10; i++) {
    const n = String(i).padStart(2, '0');
    insert.run(`s00${n}@student.vit.edu`, `Student ${n}`, `s00${n}`, COURSES[(i - 1) % COURSES.length], hash);
  }
  return 10;
}

seed();
