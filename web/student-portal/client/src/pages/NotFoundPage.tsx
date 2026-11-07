import { Link } from 'react-router-dom';
import { LostMap } from '../components/Illustrations';

export default function NotFoundPage() {
  return (
    <div className="py-10 text-center">
      <LostMap className="mx-auto mb-6 w-56" />
      <h1 className="mb-2 text-3xl font-extrabold">Page not found</h1>
      <p className="mb-5 text-ink-500">This page has wandered off the map.</p>
      <Link className="btn" to="/">Back to the dashboard</Link>
    </div>
  );
}
