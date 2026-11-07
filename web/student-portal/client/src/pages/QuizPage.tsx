import { useEffect, useRef, useState } from 'react';
import Icon from '../components/Icon';
import ProgressBar from '../components/ProgressBar';
import QuestionCard from '../components/QuestionCard';
import { useIdempotentSubmit, type SubmitPhase } from '../hooks/useIdempotentSubmit';
import { useAppSelector } from '../store';
import { usePracticeMutation, useQuizQuery } from '../store/api';
import { COURSES, errorDetail, type AnswerList, type Course, type PracticeResult, type Quiz } from '../types/api';

const PHASE_TEXT: Record<SubmitPhase, string> = {
  idle: '',
  submitting: 'Submitting…',
  retrying: '',
  committed: 'Submitted ✓ committed',
  duplicate: 'Already received ✓',
  unconfirmed: 'Not confirmed yet. Press Submit again — it is safe to retry.',
};

function loadDraft(key: string, length: number): AnswerList {
  try {
    const saved = JSON.parse(localStorage.getItem(key) ?? 'null');
    if (Array.isArray(saved) && saved.length === length) return saved;
  } catch {
    // corrupt draft: start empty
  }
  return Array<null>(length).fill(null);
}

function ResultModal({ quiz, result, onClose }: { quiz: Quiz; result: PracticeResult; onClose: () => void }) {
  const closeRef = useRef<HTMLButtonElement>(null);
  useEffect(() => { closeRef.current?.focus(); }, []);
  return (
    <div role="dialog" aria-modal="true" aria-labelledby="result-title" className="fixed inset-0 z-30 flex items-center justify-center bg-ink-900/60 p-4 backdrop-blur-sm">
      <div className="max-h-[80vh] w-full max-w-md animate-pop overflow-y-auto rounded-2xl bg-white p-6 shadow-lift">
        <h2 id="result-title" className="mb-4 text-2xl font-extrabold">Practice score: {result.score} / {result.total}</h2>
        <ul className="mb-4 space-y-2 text-sm">
          {result.results.map((r) => (
            <li key={r.index} className={`rounded-xl px-3 py-2.5 ${r.correct ? 'bg-brand-50 text-brand-800' : 'bg-coral-50 text-coral-700'}`}>
              {r.correct ? '✓' : '✗'} {quiz.questions[r.index].question}
              {!r.correct && <div className="font-bold">Correct: {quiz.questions[r.index].options[r.correct_option]}</div>}
            </li>
          ))}
        </ul>
        <button ref={closeRef} className="btn w-full" onClick={onClose}>Close</button>
      </div>
    </div>
  );
}

function QuizRunner({ quiz, studentId }: { quiz: Quiz; studentId: string }) {
  const draftKey = `cs:draft:${studentId}:${quiz.quiz_id}`;
  const count = quiz.questions.length;
  const [answers, setAnswers] = useState(() => loadDraft(draftKey, count));
  const [step, setStep] = useState(0);
  const [practiceResult, setPracticeResult] = useState<PracticeResult | null>(null);
  const [practice, { isLoading: practising, error: practiceError }] = usePracticeMutation();
  const { key, phase, attempt, submit } = useIdempotentSubmit(studentId, quiz.quiz_id);
  const status = useAppSelector((s) => s.status.current);

  const answered = answers.filter((a) => a !== null).length;
  const onReview = step === count;
  const sending = phase === 'submitting' || phase === 'retrying';
  const confirmed = phase === 'committed' || phase === 'duplicate';
  const statusKnown = status !== null && status.level !== null;
  const examHere = status?.exam.active && status.exam.course === quiz.course;
  const canPractise = statusKnown && !examHere;

  const choose = (option: number) => {
    const next = answers.map((a, i) => (i === step ? option : a));
    setAnswers(next);
    localStorage.setItem(draftKey, JSON.stringify(next));
  };

  const onPractice = async () => {
    const result = await practice({ course: quiz.course, answers });
    if ('data' in result && result.data) setPracticeResult(result.data);
  };

  const onSubmit = async () => {
    const payload: Record<string, string> = {};
    answers.forEach((a, i) => {
      if (a !== null) payload[`q${i + 1}`] = String.fromCharCode(97 + a); // same format as the old page
    });
    if (await submit(payload)) localStorage.removeItem(draftKey);
  };

  return (
    <div className="space-y-5">
      <ProgressBar value={onReview ? count : step} max={count} label="Quiz progress" />
      {!onReview && (
        <>
          <p className="eyebrow">Question {step + 1} of {count}</p>
          <QuestionCard index={step} question={quiz.questions[step]} selected={answers[step]} onChange={choose} />
        </>
      )}
      {onReview && (
        <section className="card animate-fade-up space-y-4">
          <h2 className="text-xl font-extrabold">Review</h2>
          <ol className="list-decimal space-y-2 pl-5 text-sm">
            {quiz.questions.map((q, i) => (
              <li key={q.question}>
                {q.question} <b className="text-brand-700">{answers[i] === null ? 'Not answered' : q.options[answers[i]]}</b>
              </li>
            ))}
          </ol>
          {answered < count && <p className="rounded-xl bg-sun-100 px-4 py-2.5 text-sm font-medium text-sun-800">{count - answered} question(s) not answered.</p>}
          <div className="flex flex-wrap items-center gap-2">
            <button className="btn-secondary" disabled={!canPractise || practising} onClick={onPractice}>
              {practising ? 'Checking…' : 'Practice'}
            </button>
            <button className="btn" disabled={sending || confirmed} onClick={onSubmit}>Submit for grading</button>
            {key && <span className="inline-flex items-center gap-1 rounded-full bg-brand-50 px-3 py-1 text-xs font-bold text-brand-700"><Icon name="shield" className="h-3.5 w-3.5" />Idempotency protected · {key.slice(0, 8)}</span>}
          </div>
          {examHere && <p className="text-sm text-ink-500">Practice is closed during the exam for this course.</p>}
          {status?.level === null && <p className="text-sm text-ink-500">Practice needs the tutor service, which is unreachable right now.</p>}
          {practiceError && <p role="alert" className="text-sm text-coral-700">{errorDetail(practiceError, 'Practice failed. Try again.')}</p>}
          <p role="status" aria-live="polite" className={`text-sm font-medium ${phase === 'unconfirmed' ? 'text-coral-700' : confirmed ? 'animate-pop text-brand-700' : 'text-ink-800'}`}>
            {phase === 'retrying' ? `Retrying (${attempt}/3)…` : PHASE_TEXT[phase]}
          </p>
        </section>
      )}
      <div className="flex justify-between">
        <button className="btn-secondary" disabled={step === 0} onClick={() => setStep(step - 1)}><Icon name="back" className="h-4 w-4" />Back</button>
        {!onReview && <button className="btn" onClick={() => setStep(step + 1)}>{step === count - 1 ? 'Review' : 'Next'}<Icon name="arrow" className="h-4 w-4" /></button>}
      </div>
      {practiceResult && <ResultModal quiz={quiz} result={practiceResult} onClose={() => setPracticeResult(null)} />}
    </div>
  );
}

export default function QuizPage() {
  const user = useAppSelector((s) => s.auth.user);
  const [course, setCourse] = useState<Course>(user?.course ?? COURSES[0]);
  const { data: quiz, isFetching, error } = useQuizQuery(course);

  return (
    <div className="mx-auto max-w-2xl space-y-5">
      <div className="flex items-center gap-3">
        <div>
          <h1 className="text-2xl font-extrabold sm:text-3xl">Quiz</h1>
          <p className="hidden text-sm text-ink-500 sm:block">Your answers save in this browser as you go.</p>
        </div>
        <label htmlFor="quiz-course" className="sr-only">Course</label>
        <select id="quiz-course" className="field ml-auto w-auto" value={course} onChange={(e) => setCourse(e.target.value as Course)}>
          {COURSES.map((c) => <option key={c}>{c}</option>)}
        </select>
      </div>
      {isFetching && <p className="text-ink-500">Loading…</p>}
      {error && <p role="alert" className="text-coral-700">{errorDetail(error, 'Could not load the quiz.')}</p>}
      {quiz && !isFetching && user && <QuizRunner key={quiz.quiz_id} quiz={quiz} studentId={user.student_id} />}
    </div>
  );
}
