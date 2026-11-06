import { memo } from 'react';
import ReactMarkdown from 'react-markdown';
import { useQueuedAnswer } from '../hooks/useQueuedAnswer';
import type { Message } from '../store/chatSlice';
import LevelBadge from './LevelBadge';

function ChatMessage({ message: m }: { message: Message }) {
  useQueuedAnswer(m.queue_id);

  if (m.pending) {
    return (
      <div className="w-2/3 animate-pulse space-y-2 rounded-2xl bg-white p-4 shadow-sm" aria-label="Waiting for the tutor">
        <div className="h-3 w-3/4 rounded bg-slate-200" />
        <div className="h-3 w-1/2 rounded bg-slate-200" />
      </div>
    );
  }
  if (m.role === 'user') {
    return <div className="ml-auto max-w-[85%] whitespace-pre-wrap break-words rounded-2xl bg-indigo-600 px-4 py-2 text-white">{m.text}</div>;
  }
  if (m.role === 'error') {
    return <div className="max-w-[85%] rounded-2xl bg-red-50 px-4 py-2 text-red-800">{m.text}</div>;
  }
  return (
    <div className="max-w-[85%] rounded-2xl bg-white px-4 py-3 shadow-sm">
      {m.level !== undefined && <LevelBadge level={m.level} />}
      {/* No rehype-raw: raw HTML in an answer stays inert text. */}
      <div className="markdown mt-1 break-words"><ReactMarkdown>{m.text}</ReactMarkdown></div>
      <p className="mt-1 text-xs text-slate-500">
        {m.latency_ms} ms · source: {m.source}
        {m.queue_id && m.position ? ` · queue position #${m.position}` : ''}
      </p>
    </div>
  );
}

export default memo(ChatMessage);
