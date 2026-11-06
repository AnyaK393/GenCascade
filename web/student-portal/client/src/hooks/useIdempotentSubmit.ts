import { useCallback, useState } from 'react';
import { useSubmitMutation } from '../store/api';
import type { ApiError } from '../types/api';

const RETRY_DELAYS_MS = [500, 1000, 2000];

export type SubmitPhase = 'idle' | 'submitting' | 'retrying' | 'committed' | 'duplicate' | 'unconfirmed';

/** crypto.randomUUID only exists on HTTPS and localhost; phones reach this portal over plain HTTP. */
export function newUuid(): string {
  const b = crypto.getRandomValues(new Uint8Array(16));
  b[6] = (b[6] & 0x0f) | 0x40;
  b[8] = (b[8] & 0x3f) | 0x80;
  const hex = Array.from(b, (x) => x.toString(16).padStart(2, '0')).join('');
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

/** Student id is part of the key: otherwise a shared phone would file one student's quiz as another's duplicate. */
export function useIdempotentSubmit(studentId: string, quizId: string) {
  const storageKey = `cs:submit:${studentId}:${quizId}`;
  const [submitQuiz] = useSubmitMutation();
  const [phase, setPhase] = useState<SubmitPhase>('idle');
  const [attempt, setAttempt] = useState(0);
  const [key, setKey] = useState(() => localStorage.getItem(storageKey));

  const submit = useCallback(async (answers: Record<string, string>) => {
    const idempotency_key = localStorage.getItem(storageKey) ?? newUuid();
    localStorage.setItem(storageKey, idempotency_key);
    setKey(idempotency_key);
    setPhase('submitting');

    for (let i = 0; i <= RETRY_DELAYS_MS.length; i++) {
      if (i > 0) {
        setAttempt(i);
        setPhase('retrying');
        await sleep(RETRY_DELAYS_MS[i - 1]);
      }
      const result = await submitQuiz({ quiz_id: quizId, answers, idempotency_key });
      if ('data' in result && result.data?.status === 'committed') {
        localStorage.removeItem(storageKey);
        setPhase(result.data.duplicate ? 'duplicate' : 'committed');
        return true;
      }
      const status = (result.error as ApiError | undefined)?.status;
      if (typeof status === 'number' && status >= 400 && status < 500) break; // retrying cannot help
    }
    setPhase('unconfirmed');
    return false;
  }, [storageKey, quizId, submitQuiz]);

  return { key, phase, attempt, submit };
}
