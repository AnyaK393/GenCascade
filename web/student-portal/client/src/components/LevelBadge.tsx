const LEVELS = [
  { label: 'AI Tutor', className: 'bg-purple-100 text-purple-800' },
  { label: 'Light mode', className: 'bg-amber-100 text-amber-800' },
  { label: 'Course notes', className: 'bg-blue-100 text-blue-800' },
  { label: 'Hint', className: 'bg-gray-200 text-gray-800' },
  { label: 'Queued', className: 'bg-slate-200 text-slate-800' },
];

export default function LevelBadge({ level }: { level: number }) {
  const badge = LEVELS[level];
  if (!badge) return null;
  return <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${badge.className}`}>{badge.label}</span>;
}
