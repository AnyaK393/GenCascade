import { lazy, Suspense } from 'react';
import { createBrowserRouter, Navigate, useLocation } from 'react-router-dom';
import Layout from './components/Layout';
import { useMeQuery } from './store/api';
import type { ApiError } from './types/api';

const LoginPage = lazy(() => import('./pages/LoginPage'));
const RegisterPage = lazy(() => import('./pages/RegisterPage'));
const DashboardPage = lazy(() => import('./pages/DashboardPage'));
const TutorPage = lazy(() => import('./pages/TutorPage'));
const QuizPage = lazy(() => import('./pages/QuizPage'));
const NotFoundPage = lazy(() => import('./pages/NotFoundPage'));

const loading = <p className="p-8 text-center text-ink-500">Loading…</p>;

function RequireAuth() {
  const location = useLocation();
  const { data, error, isLoading, refetch } = useMeQuery();
  if (isLoading) return loading;
  if ((error as ApiError | undefined)?.status === 401) return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  if (!data) {
    return (
      <div className="p-8 text-center">
        <p className="mb-4">Cannot reach the student portal.</p>
        <button className="btn" onClick={() => refetch()}>Try again</button>
      </div>
    );
  }
  return <Layout />;
}

const page = (element: JSX.Element) => <Suspense fallback={loading}>{element}</Suspense>;

export const router = createBrowserRouter([
  { path: '/login', element: page(<LoginPage />) },
  { path: '/register', element: page(<RegisterPage />) },
  {
    element: <RequireAuth />,
    children: [
      { path: '/', element: <DashboardPage /> },
      { path: '/tutor', element: <TutorPage /> },
      { path: '/quiz', element: <QuizPage /> },
      { path: '*', element: <NotFoundPage /> },
    ],
  },
]);
