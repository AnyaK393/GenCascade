import { Link } from 'react-router-dom';
import ProgressBar from '../components/ProgressBar';
import { useAppSelector } from '../store';
import { useProfileQuery } from '../store/api';

export default function DashboardPage() {
  const user = useAppSelector((s) => s.auth.user);
  const { data: profile, isLoading } = useProfileQuery();

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">Hello, {user?.name}</h1>
      <p className="text-slate-600">Your course: <b>{user?.course}</b></p>
      <div className="flex flex-wrap gap-2">
        <Link className="btn" to="/tutor">Ask the tutor</Link>
        <Link className="btn-secondary" to="/quiz">Take a quiz</Link>
      </div>
      <section className="rounded-xl bg-white p-4 shadow-sm">
        <h2 className="mb-1 text-lg font-semibold">Topic mastery</h2>
        {isLoading && <p className="text-slate-500">Loading…</p>}
        {profile && !profile.available && <p className="text-slate-500">Mastery data is unavailable right now.</p>}
        {profile?.available && (
          <>
            <p className="mb-3 text-sm text-slate-600">Platform record: {profile.course}, level {profile.level}</p>
            <ul className="space-y-2">
              {Object.entries(profile.mastery).map(([topic, value]) => (
                <li key={topic}>
                  <div className="flex justify-between text-sm">
                    <span>{topic.replaceAll('_', ' ')}</span><span>{Math.round(value * 100)}%</span>
                  </div>
                  <ProgressBar value={value} max={1} label={`${topic} mastery`} />
                </li>
              ))}
            </ul>
          </>
        )}
      </section>
    </div>
  );
}
