import { Suspense, useState } from 'react';
import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import { useLiveStatus } from '../hooks/useLiveStatus';
import { useAppDispatch, useAppSelector } from '../store';
import { api, useLogoutMutation } from '../store/api';
import { chatCleared } from '../store/chatSlice';
import ErrorBoundary from './ErrorBoundary';
import NetworkInspector from './NetworkInspector';
import StatusBanner from './StatusBanner';

const LINKS = [
  { to: '/', label: 'Dashboard' },
  { to: '/tutor', label: 'Tutor' },
  { to: '/quiz', label: 'Quiz' },
];
const STATUS_URL = import.meta.env.VITE_STATUS_URL;

export default function Layout() {
  useLiveStatus();
  const dispatch = useAppDispatch();
  const navigate = useNavigate();
  const user = useAppSelector((s) => s.auth.user);
  const [logout] = useLogoutMutation();
  const [menuOpen, setMenuOpen] = useState(false);

  const onLogout = async () => {
    await logout();
    dispatch(chatCleared());
    dispatch(api.util.resetApiState());
    navigate('/login');
  };

  const linkClass = ({ isActive }: { isActive: boolean }) =>
    `block rounded-lg px-3 py-2 ${isActive ? 'bg-indigo-100 text-indigo-800' : 'text-slate-700 hover:bg-slate-100'}`;

  return (
    <div className="flex min-h-screen flex-col bg-slate-50 text-slate-900">
      <header className="bg-white shadow-sm">
        <nav aria-label="Main" className="mx-auto flex max-w-4xl flex-wrap items-center gap-2 px-4 py-2">
          <span className="font-bold text-indigo-700">CascadeShield</span>
          <button className="btn-secondary ml-auto sm:hidden" aria-expanded={menuOpen} aria-label="Menu" onClick={() => setMenuOpen((v) => !v)}>☰</button>
          <div className={`${menuOpen ? 'block' : 'hidden'} w-full sm:ml-4 sm:flex sm:w-auto sm:flex-1 sm:items-center sm:gap-1`}>
            {LINKS.map((l) => (
              <NavLink key={l.to} to={l.to} end={l.to === '/'} className={linkClass} onClick={() => setMenuOpen(false)}>{l.label}</NavLink>
            ))}
            <span className="flex items-center gap-3 px-3 py-2 sm:ml-auto sm:px-0 sm:py-0">
              <span className="text-sm text-slate-600">{user?.name}</span>
              <button className="btn-secondary" onClick={onLogout}>Log out</button>
            </span>
          </div>
        </nav>
      </header>
      <StatusBanner />
      <main className="mx-auto w-full max-w-4xl flex-1 p-4">
        <ErrorBoundary>
          <Suspense fallback={<p className="text-slate-500">Loading…</p>}>
            <Outlet />
          </Suspense>
        </ErrorBoundary>
      </main>
      {STATUS_URL && (
        <footer className="p-4 text-center text-sm">
          <a className="text-indigo-700 underline" href={STATUS_URL}>Public system status</a>
        </footer>
      )}
      <NetworkInspector />
    </div>
  );
}
