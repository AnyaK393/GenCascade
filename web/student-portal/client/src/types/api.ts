export const COURSES = ['DSA101', 'DBMS201', 'OS202'] as const;
export type Course = (typeof COURSES)[number];

export interface Me {
  student_id: string;
  name: string;
  email: string;
  course: Course;
  exp: number;
}

export interface AskRequest {
  course: Course;
  question: string;
  session_id: string;
}

export interface AskResponse {
  answer: string;
  level: number;
  source: string;
  latency_ms: number;
  session_id: string;
  request_id: string;
  queue_id?: string;
  position?: number;
}

export interface QueuedResponse {
  status: 'queued' | 'answered';
  answer?: string;
  level?: number;
  source?: string;
  position?: number | null;
}

export interface Status {
  level: number | null;
  banner: string;
  color: 'green' | 'amber' | 'blue' | 'red';
  exam: { active: boolean; course?: string; ends_at?: string | null };
}

export interface QuizQuestion {
  question: string;
  options: string[];
}

export interface Quiz {
  course: Course;
  quiz_id: string;
  questions: QuizQuestion[];
}

export type AnswerList = (number | null)[];

export interface PracticeResult {
  score: number;
  total: number;
  results: { index: number; correct: boolean; correct_option: number }[];
}

export interface SubmitRequest {
  quiz_id: string;
  answers: Record<string, string>;
  idempotency_key: string;
}

export interface SubmitResponse {
  status: 'committed' | 'failed';
  duplicate?: boolean;
  detail?: string;
}

export type Profile =
  | { available: false }
  | { available: true; student_id: string; name: string; course: string; level: string; mastery: Record<string, number> };

export interface ApiError {
  status: number | string;
  data?: { detail?: unknown };
}

export function errorDetail(error: unknown, fallback: string): string {
  const detail = (error as ApiError | undefined)?.data?.detail;
  return typeof detail === 'string' && detail ? detail : fallback;
}
