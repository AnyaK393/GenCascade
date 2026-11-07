export default function ProgressBar({ value, max, label, tone = false }: { value: number; max: number; label: string; tone?: boolean }) {
  const share = max ? value / max : 0;
  const color = !tone || share >= 0.7 ? 'bg-brand-500' : share >= 0.4 ? 'bg-sun-500' : 'bg-coral-500';
  return (
    <div role="progressbar" aria-label={label} aria-valuenow={value} aria-valuemin={0} aria-valuemax={max}
      className="h-2.5 w-full overflow-hidden rounded-full bg-ink-100">
      <div className="h-full origin-left animate-grow rounded-full transition-[width] duration-500" style={{ width: `${share * 100}%` }}>
        <div className={`h-full w-full rounded-full ${color}`} />
      </div>
    </div>
  );
}
