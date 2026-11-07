import { Link } from 'react-router-dom';
import Icon from '../components/Icon';
import { StudyDesk } from '../components/Illustrations';
import ProgressBar from '../components/ProgressBar';
import { useAppSelector } from '../store';
import { useProfileQuery } from '../store/api';

const pretty = (topic: string) => topic.replaceAll('_', ' ');

function Stat({ icon, label, value, tint, delay }: { icon: 'book' | 'target' | 'star'; label: string; value: string; tint: string; delay: number }) {
  return (
    <div className="card flex animate-fade-up items-center gap-4 !p-4 sm:!p-5" style={{ animationDelay: `${delay}ms` }}>
      <span className={`flex h-11 w-11 flex-none items-center justify-center rounded-xl ${tint}`}><Icon name={icon} /></span>
      <div className="min-w-0">
        <p className="eyebrow">{label}</p>
        <p className="truncate text-lg font-extrabold capitalize">{value}</p>
      </div>
    </div>
  );
}

export default function DashboardPage() {
  const user = useAppSelector((s) => s.auth.user);
  const { data: profile, isLoading } = useProfileQuery();
  const topics = profile?.available ? Object.entries(profile.mastery) : [];
  const average = topics.length ? Math.round((topics.reduce((sum, [, v]) => sum + v, 0) / topics.length) * 100) : null;
  const ranked = [...topics].sort((a, b) => a[1] - b[1]);

  return (
    <div className="space-y-6">
      <section className="relative overflow-hidden rounded-3xl bg-brand-800 px-6 py-7 text-white shadow-lift sm:px-9 sm:py-9">
        <div className="absolute -right-16 -top-24 h-72 w-72 rounded-full bg-brand-700" aria-hidden="true" />
        <div className="relative flex flex-col-reverse gap-6 md:flex-row md:items-center md:justify-between">
          <div className="min-w-0">
            <h1 className="text-3xl font-extrabold sm:text-4xl">Hello, {user?.name}</h1>
            <p className="mt-2 text-brand-100">Your course: <b className="text-white">{user?.course}</b></p>
            <div className="mt-6 flex flex-wrap gap-3">
              <Link className="btn !bg-white !text-brand-800 hover:!bg-brand-50" to="/tutor"><Icon name="chat" />Ask the tutor</Link>
              <Link className="btn !bg-brand-700 ring-1 ring-brand-400 hover:!bg-brand-600" to="/quiz"><Icon name="quiz" />Take a quiz</Link>
            </div>
          </div>
          <StudyDesk className="mx-auto w-56 flex-none md:mx-0 md:w-72" />
        </div>
      </section>

      <div className="grid gap-4 sm:grid-cols-3">
        <Stat icon="book" label="Average mastery" value={average === null ? '–' : `${average}%`} tint="bg-brand-100 text-brand-700" delay={60} />
        <Stat icon="star" label="Strongest topic" value={ranked.length ? pretty(ranked[ranked.length - 1][0]) : '–'} tint="bg-sun-100 text-sun-800" delay={120} />
        <Stat icon="target" label="Focus next" value={ranked.length ? pretty(ranked[0][0]) : '–'} tint="bg-coral-100 text-coral-700" delay={180} />
      </div>

      <section className="card animate-fade-up" style={{ animationDelay: '240ms' }}>
        <h2 className="text-xl font-extrabold">Topic mastery</h2>
        {isLoading && <p className="mt-2 text-ink-500">Loading…</p>}
        {profile && !profile.available && <p className="mt-2 text-ink-500">Mastery data is unavailable right now.</p>}
        {profile?.available && (
          <>
            <p className="mb-5 mt-1 text-sm text-ink-500">Platform record: {profile.course}, level {profile.level}</p>
            <ul className="grid gap-x-10 gap-y-5 sm:grid-cols-2">
              {topics.map(([topic, value]) => (
                <li key={topic}>
                  <div className="mb-1.5 flex justify-between text-sm font-semibold">
                    <span className="capitalize">{pretty(topic)}</span><span className="text-ink-500">{Math.round(value * 100)}%</span>
                  </div>
                  <ProgressBar value={value} max={1} label={`${topic} mastery`} tone />
                </li>
              ))}
            </ul>
          </>
        )}
      </section>
    </div>
  );
}
