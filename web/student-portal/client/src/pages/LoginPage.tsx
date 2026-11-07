import { useState, type FormEvent } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import AuthShell from '../components/AuthShell';
import { useAppDispatch } from '../store';
import { api, useLoginMutation } from '../store/api';
import { errorDetail } from '../types/api';

const EMAIL_PATTERN = /^\S+@\S+\.\S+$/;

export default function LoginPage() {
  const dispatch = useAppDispatch();
  const navigate = useNavigate();
  const from = (useLocation().state as { from?: string } | null)?.from ?? '/';
  const [login, { isLoading, error }] = useLoginMutation();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [touched, setTouched] = useState(false);

  const emailError = touched && !EMAIL_PATTERN.test(email) ? 'Enter a valid e-mail address' : '';
  const passwordError = touched && !password ? 'Enter your password' : '';

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setTouched(true);
    if (!EMAIL_PATTERN.test(email) || !password) return;
    const result = await login({ email, password });
    if ('error' in result) return;
    await dispatch(api.endpoints.me.initiate(undefined, { forceRefetch: true }));
    navigate(from, { replace: true });
  };

  return (
    <AuthShell title="Student login" subtitle="Welcome back. Log in to your courses.">
      <form onSubmit={onSubmit} noValidate className="space-y-5">
        <div>
          <label htmlFor="email" className="mb-1.5 block text-sm font-semibold">E-mail</label>
          <input id="email" className="field" type="email" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} />
          {emailError && <p className="mt-1.5 text-sm text-coral-700">{emailError}</p>}
        </div>
        <div>
          <label htmlFor="password" className="mb-1.5 block text-sm font-semibold">Password</label>
          <input id="password" className="field" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} />
          {passwordError && <p className="mt-1.5 text-sm text-coral-700">{passwordError}</p>}
        </div>
        {error && <p role="alert" className="rounded-xl bg-coral-50 px-4 py-2.5 text-sm text-coral-700">{errorDetail(error, 'Cannot reach the server. Try again.')}</p>}
        <button className="btn w-full" disabled={isLoading}>{isLoading ? 'Logging in…' : 'Log in'}</button>
        <p className="text-center text-sm text-ink-500">No account? <Link className="link" to="/register">Register</Link></p>
      </form>
    </AuthShell>
  );
}
