import { useEffect, useRef, useState, type FormEvent } from 'react';
import { nanoid } from '@reduxjs/toolkit';
import ChatMessage from '../components/ChatMessage';
import Icon from '../components/Icon';
import { TutorBubbles } from '../components/Illustrations';
import { useToast } from '../components/Toast';
import { newUuid } from '../hooks/useIdempotentSubmit';
import { useAppDispatch, useAppSelector } from '../store';
import { useAskMutation } from '../store/api';
import { answerReceived, askFailed, questionSent } from '../store/chatSlice';
import { COURSES, errorDetail, type ApiError, type Course } from '../types/api';

const NO_MESSAGES: never[] = [];
const SUGGESTIONS: Record<Course, string[]> = {
  DSA101: ['What is a binary search tree?', 'Why is quicksort slow on sorted input?'],
  DBMS201: ['What does a join do in SQL?', 'Why do databases use indexes?'],
  OS202: ['What is a deadlock?', 'How does paging work?'],
};
const sessionId = newUuid();

export default function TutorPage() {
  const dispatch = useAppDispatch();
  const toast = useToast();
  const user = useAppSelector((s) => s.auth.user);
  const [course, setCourse] = useState<Course>(user?.course ?? COURSES[0]);
  const messages = useAppSelector((s) => s.chat.byCourse[course]) ?? NO_MESSAGES;
  const [ask, { isLoading }] = useAskMutation();
  const [question, setQuestion] = useState('');
  const inputRef = useRef<HTMLInputElement>(null);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => { inputRef.current?.focus(); }, [isLoading]);
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [messages]);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    const text = question.trim();
    if (!text || isLoading) return;
    setQuestion('');
    const botId = nanoid();
    dispatch(questionSent(course, text, botId));
    const result = await ask({ course, question: text, session_id: sessionId });
    if ('data' in result && result.data) {
      dispatch(answerReceived({ course, botId, response: result.data }));
      if (result.data.level === 4) toast(`Question queued at position #${result.data.position}. Your quiz is safe.`);
      return;
    }
    const limited = (result.error as ApiError | undefined)?.status === 429;
    if (limited) toast('Slow down: 6 questions per minute');
    dispatch(askFailed({ course, botId, text: errorDetail(result.error, 'The tutor could not answer. Try again in a moment.') }));
  };

  return (
    <div className="flex h-[calc(100dvh-14.5rem)] min-h-[26rem] flex-col gap-4">
      <div className="flex items-center gap-3">
        <div>
          <h1 className="whitespace-nowrap text-2xl font-extrabold sm:text-3xl">AI Tutor</h1>
          <p className="hidden text-sm text-ink-500 sm:block">Guiding questions that help you work it out yourself.</p>
        </div>
        <label htmlFor="tutor-course" className="sr-only">Course</label>
        <select id="tutor-course" className="field ml-auto w-auto" value={course} onChange={(e) => setCourse(e.target.value as Course)}>
          {COURSES.map((c) => <option key={c}>{c}</option>)}
        </select>
      </div>
      <div className="flex flex-1 flex-col gap-4 overflow-y-auto rounded-2xl border border-ink-100 bg-ink-50/60 p-4 sm:p-5" aria-live="polite">
        {messages.length === 0 && (
          <div className="m-auto max-w-md animate-fade-up text-center">
            <TutorBubbles className="mx-auto mb-4 w-36" />
            <p className="text-lg font-bold">Ask anything about {course}.</p>
            <p className="mb-4 text-sm text-ink-500">Stuck on where to start? Try one of these:</p>
            <div className="flex flex-col gap-2">
              {SUGGESTIONS[course].map((s) => (
                <button key={s} type="button" onClick={() => { setQuestion(s); inputRef.current?.focus(); }}
                  className="rounded-xl border border-ink-200 bg-white px-4 py-2.5 text-sm font-semibold text-ink-700 transition duration-200 hover:-translate-y-0.5 hover:border-brand-300 hover:text-brand-700 hover:shadow-card">{s}</button>
              ))}
            </div>
          </div>
        )}
        {messages.map((m) => <ChatMessage key={m.id} message={m} />)}
        <div ref={endRef} />
      </div>
      <form onSubmit={onSubmit} className="flex gap-2">
        <label htmlFor="question" className="sr-only">Your question</label>
        <input id="question" ref={inputRef} className="field" maxLength={2000} placeholder="Type your question" value={question} onChange={(e) => setQuestion(e.target.value)} />
        <button className="btn" disabled={isLoading || !question.trim()}><Icon name="send" className="h-4 w-4" />Send</button>
      </form>
    </div>
  );
}
