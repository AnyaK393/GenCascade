import { Suspense, useState } from 'react';
import { Link, NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom';
import { useLiveStatus } from '../hooks/useLiveStatus';
import { useAppDispatch, useAppSelector } from '../store';
import { api, useLogoutMutation } from '../store/api';
import { chatCleared } from '../store/chatSlice';
import ErrorBoundary from './ErrorBoundary';
import Icon from './Icon';
import { Logo } from './Illustrations';
import NetworkInspector from './NetworkInspector';
import StatusBanner from './StatusBanner';

const LINKS = [
  { to: '/', label: 'Dashboard', icon: 'home' },
  { to: '/tutor', label: 'Tutor', icon: 'chat' },
  { to: '/quiz', label: 'Quiz', icon: 'quiz' },
] as const;
const STATUS_URL = import.meta.env.VITE_STATUS_URL;

export default function Layout() {
  useLiveStatus();
  const dispatch = useAppDispatch();
  const navigate = useNavigate();
  const { pathname } = useLocation();
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
    `flex items-center gap-2 rounded-xl px-3.5 py-2 font-semibold transition duration-200 ${isActive ? 'bg-brand-50 text-brand-700' : 'text-ink-600 hover:bg-ink-50 hover:text-ink-900'}`;

  return (
    <div className="flex min-h-screen flex-col">
      <header className="sticky top-0 z-20 border-b border-ink-100 bg-white/90 backdrop-blur">
        <nav aria-label="Main" className="mx-auto flex max-w-5xl flex-wrap items-center gap-2 px-4 py-2.5 sm:px-6">
          <Link to="/" className="flex items-center gap-2.5 text-lg font-extrabold text-brand-800"><Logo /> CascadeShield</Link>
          <button className="btn-secondary ml-auto !px-3 sm:hidden" aria-expanded={menuOpen} aria-label="Menu" onClick={() => setMenuOpen((v) => !v)}><Icon name="menu" /></button>
          <div className={`${menuOpen ? 'block animate-pop' : 'hidden'} w-full sm:ml-5 sm:flex sm:w-auto sm:flex-1 sm:items-center sm:gap-1`}>
            {LINKS.map((l) => (
              <NavLink key={l.to} to={l.to} end={l.to === '/'} className={linkClass} onClick={() => setMenuOpen(false)}><Icon name={l.icon} />{l.label}</NavLink>
            ))}
            <span className="flex items-center gap-3 px-3 py-2 sm:ml-auto sm:px-0 sm:py-0">
              <span aria-hidden="true" className="flex h-9 w-9 flex-none items-center justify-center rounded-full bg-coral-100 text-sm font-extrabold text-coral-700">{user?.name?.charAt(0).toUpperCase()}</span>
              <span className="text-sm font-semibold text-ink-700">{user?.name}</span>
              <button className="btn-secondary ml-auto !px-3 !py-2 text-sm sm:ml-0" onClick={onLogout}><Icon name="logout" className="h-4 w-4" />Log out</button>
            </span>
          </div>
        </nav>
        <StatusBanner />
      </header>
      <main className="mx-auto w-full max-w-5xl flex-1 px-4 py-6 sm:px-6 sm:py-8">
        <ErrorBoundary>
          <Suspense fallback={<p className="text-ink-500">Loading…</p>}>
            <div key={pathname} className="animate-fade-up"><Outlet /></div>
          </Suspense>
        </ErrorBoundary>
      </main>
      <footer className="border-t border-ink-100 px-4 py-5 text-center text-sm text-ink-500">
        CascadeShield student portal
        {STATUS_URL && <> · <a className="link" href={STATUS_URL}>Public system status</a></>}
      </footer>
      <NetworkInspector />
    </div>
  );
}
