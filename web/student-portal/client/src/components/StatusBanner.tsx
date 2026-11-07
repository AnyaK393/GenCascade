import { useAppSelector } from '../store';

const COLORS = {
  green: { bar: 'bg-brand-50 text-brand-800', dot: 'bg-brand-500' },
  amber: { bar: 'bg-sun-100 text-sun-800', dot: 'bg-sun-500' },
  blue: { bar: 'bg-sky-100 text-sky-900', dot: 'bg-sky-600' },
  red: { bar: 'bg-coral-700 text-white', dot: 'bg-white' },
};

export default function StatusBanner() {
  const status = useAppSelector((s) => s.status.current);
  if (!status) return <div className="bg-ink-50 px-4 py-2 text-center text-sm text-ink-500">Checking tutor status…</div>;
  const { exam } = status;
  const color = COLORS[status.color];
  return (
    <div role="status" className={`transition-colors duration-500 ${color.bar}`}>
      <div className="mx-auto flex max-w-5xl flex-wrap items-center gap-x-3 gap-y-1 px-4 py-2 text-sm font-semibold sm:px-6">
        <span className="relative flex h-2.5 w-2.5 flex-none" aria-hidden="true">
          <span className={`absolute inline-flex h-full w-full animate-beacon rounded-full opacity-60 ${color.dot}`} />
          <span className={`relative inline-flex h-2.5 w-2.5 rounded-full ${color.dot}`} />
        </span>
        <span>{status.banner}</span>
        {exam.active && (
          <span className="animate-pop rounded-full bg-coral-700 px-3 py-0.5 text-xs font-bold text-white shadow-sm">
            Exam in progress: {exam.course}
            {exam.ends_at ? ` until ${new Date(exam.ends_at).toLocaleTimeString()}` : ''}
          </span>
        )}
      </div>
    </div>
  );
}
