import { useEffect, useRef, useState, type FormEvent } from 'react';
import { nanoid } from '@reduxjs/toolkit';
import ChatMessage from '../components/ChatMessage';
import { useToast } from '../components/Toast';
import { newUuid } from '../hooks/useIdempotentSubmit';
import { useAppDispatch, useAppSelector } from '../store';
import { useAskMutation } from '../store/api';
import { answerReceived, askFailed, questionSent } from '../store/chatSlice';
import { COURSES, errorDetail, type ApiError, type Course } from '../types/api';

const NO_MESSAGES: never[] = [];
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
    <div className="flex h-[calc(100vh-11rem)] flex-col gap-3">
      <div className="flex items-center gap-2">
        <h1 className="whitespace-nowrap text-xl font-bold">AI Tutor</h1>
        <label htmlFor="tutor-course" className="sr-only">Course</label>
        <select id="tutor-course" className="field ml-auto w-auto" value={course} onChange={(e) => setCourse(e.target.value as Course)}>
          {COURSES.map((c) => <option key={c}>{c}</option>)}
        </select>
      </div>
      <div className="flex flex-1 flex-col gap-3 overflow-y-auto rounded-xl bg-slate-100 p-3" aria-live="polite">
        {messages.length === 0 && <p className="m-auto text-slate-500">Ask anything about {course}.</p>}
        {messages.map((m) => <ChatMessage key={m.id} message={m} />)}
        <div ref={endRef} />
      </div>
      <form onSubmit={onSubmit} className="flex gap-2">
        <label htmlFor="question" className="sr-only">Your question</label>
        <input id="question" ref={inputRef} className="field" maxLength={2000} placeholder="Type your question" value={question} onChange={(e) => setQuestion(e.target.value)} />
        <button className="btn" disabled={isLoading || !question.trim()}>Send</button>
      </form>
    </div>
  );
}
