import { memo } from 'react';
import ReactMarkdown from 'react-markdown';
import { useQueuedAnswer } from '../hooks/useQueuedAnswer';
import type { Message } from '../store/chatSlice';
import Icon from './Icon';
import LevelBadge from './LevelBadge';

function ChatMessage({ message: m }: { message: Message }) {
  useQueuedAnswer(m.queue_id);

  if (m.pending) {
    return (
      <div className="flex animate-pop items-center gap-1.5 self-start rounded-2xl rounded-bl-md border border-ink-100 bg-white px-5 py-4 shadow-card" aria-label="Waiting for the tutor">
        {[0, 150, 300].map((delay) => (
          <span key={delay} className="h-2 w-2 animate-dot rounded-full bg-brand-500" style={{ animationDelay: `${delay}ms` }} />
        ))}
      </div>
    );
  }
  if (m.role === 'user') {
    return <div className="ml-auto max-w-[85%] animate-pop whitespace-pre-wrap break-words rounded-2xl rounded-br-md bg-brand-700 px-4 py-2.5 text-white shadow-sm">{m.text}</div>;
  }
  if (m.role === 'error') {
    return <div className="max-w-[85%] animate-pop rounded-2xl rounded-bl-md border border-coral-100 bg-coral-50 px-4 py-2.5 text-coral-700">{m.text}</div>;
  }
  return (
    <div className="flex max-w-[92%] animate-pop items-start gap-2.5 sm:max-w-[85%]">
      <span className="mt-1 hidden h-8 w-8 flex-none items-center justify-center rounded-xl bg-brand-100 text-brand-700 sm:flex"><Icon name="shield" className="h-4 w-4" /></span>
      <div className="min-w-0 rounded-2xl rounded-tl-md border border-ink-100 bg-white px-4 py-3 shadow-card">
        {m.level !== undefined && <LevelBadge level={m.level} />}
        {/* No rehype-raw: raw HTML in an answer stays inert text. */}
        <div className="markdown mt-2 break-words leading-relaxed"><ReactMarkdown>{m.text}</ReactMarkdown></div>
        <p className="mt-2 text-xs text-ink-500">
          {m.latency_ms} ms · source: {m.source}
          {m.queue_id && m.position ? ` · queue position #${m.position}` : ''}
        </p>
      </div>
    </div>
  );
}

export default memo(ChatMessage);
