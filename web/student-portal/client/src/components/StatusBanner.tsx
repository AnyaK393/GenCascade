import { useAppSelector } from '../store';

const COLORS = {
  green: 'bg-green-100 text-green-900',
  amber: 'bg-amber-100 text-amber-900',
  blue: 'bg-blue-100 text-blue-900',
  red: 'bg-red-600 text-white',
};

export default function StatusBanner() {
  const status = useAppSelector((s) => s.status.current);
  if (!status) return <div className="bg-slate-100 px-4 py-2 text-sm text-slate-600">Checking tutor status…</div>;
  const { exam } = status;
  return (
    <div role="status" className={`flex flex-wrap items-center gap-2 px-4 py-2 text-sm font-medium ${COLORS[status.color]}`}>
      <span>{status.banner}</span>
      {exam.active && (
        <span className="rounded-full bg-red-700 px-2 py-0.5 text-xs font-semibold text-white">
          Exam in progress: {exam.course}
          {exam.ends_at ? ` until ${new Date(exam.ends_at).toLocaleTimeString()}` : ''}
        </span>
      )}
    </div>
  );
}
