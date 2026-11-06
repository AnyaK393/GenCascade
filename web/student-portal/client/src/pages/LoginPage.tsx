import { useState, type FormEvent } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
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
    <div className="flex min-h-screen items-center justify-center bg-slate-50 p-4 text-slate-900">
      <form onSubmit={onSubmit} noValidate className="w-full max-w-sm space-y-4 rounded-2xl bg-white p-6 shadow">
        <h1 className="text-2xl font-bold">Student login</h1>
        <div>
          <label htmlFor="email" className="mb-1 block text-sm font-medium">E-mail</label>
          <input id="email" className="field" type="email" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} />
          {emailError && <p className="mt-1 text-sm text-red-700">{emailError}</p>}
        </div>
        <div>
          <label htmlFor="password" className="mb-1 block text-sm font-medium">Password</label>
          <input id="password" className="field" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} />
          {passwordError && <p className="mt-1 text-sm text-red-700">{passwordError}</p>}
        </div>
        {error && <p role="alert" className="text-sm text-red-700">{errorDetail(error, 'Cannot reach the server. Try again.')}</p>}
        <button className="btn w-full" disabled={isLoading}>{isLoading ? 'Logging in…' : 'Log in'}</button>
        <p className="text-center text-sm">No account? <Link className="text-indigo-700 underline" to="/register">Register</Link></p>
      </form>
    </div>
  );
}
