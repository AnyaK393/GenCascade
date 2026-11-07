const LEVELS = [
  { label: 'AI Tutor', className: 'bg-brand-100 text-brand-800' },
  { label: 'Light mode', className: 'bg-sun-100 text-sun-800' },
  { label: 'Course notes', className: 'bg-sky-100 text-sky-900' },
  { label: 'Hint', className: 'bg-ink-100 text-ink-700' },
  { label: 'Queued', className: 'bg-coral-100 text-coral-700' },
];

export default function LevelBadge({ level }: { level: number }) {
  const badge = LEVELS[level];
  if (!badge) return null;
  return <span className={`rounded-full px-2.5 py-0.5 text-xs font-bold ${badge.className}`}>{badge.label}</span>;
}
