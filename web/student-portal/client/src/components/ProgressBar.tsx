export default function ProgressBar({ value, max, label }: { value: number; max: number; label: string }) {
  return (
    <div role="progressbar" aria-label={label} aria-valuenow={value} aria-valuemin={0} aria-valuemax={max}
      className="h-2 w-full overflow-hidden rounded-full bg-slate-200">
      <div className="h-full bg-indigo-600 transition-all" style={{ width: `${max ? (value / max) * 100 : 0}%` }} />
    </div>
  );
}
