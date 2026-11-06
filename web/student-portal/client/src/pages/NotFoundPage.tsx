import { Link } from 'react-router-dom';

export default function NotFoundPage() {
  return (
    <div className="p-8 text-center">
      <h1 className="mb-2 text-2xl font-bold">Page not found</h1>
      <Link className="text-indigo-700 underline" to="/">Back to the dashboard</Link>
    </div>
  );
}
