import { useState, type FormEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import AuthShell from '../components/AuthShell';
import { useAppDispatch } from '../store';
import { api, useRegisterMutation } from '../store/api';
import { COURSES, errorDetail, type Course } from '../types/api';

const EMAIL_PATTERN = /^\S+@\S+\.\S+$/;

export default function RegisterPage() {
  const dispatch = useAppDispatch();
  const navigate = useNavigate();
  const [registerUser, { isLoading, error }] = useRegisterMutation();
  const [form, setForm] = useState({ name: '', email: '', password: '', course: COURSES[0] as Course });
  const [touched, setTouched] = useState(false);

  const errors = {
    name: form.name.trim() ? '' : 'Enter your name',
    email: EMAIL_PATTERN.test(form.email) ? '' : 'Enter a valid e-mail address',
    password: form.password.length >= 8 ? '' : 'Password must be at least 8 characters',
  };
  const set = (field: keyof typeof form) => (e: { target: { value: string } }) => setForm({ ...form, [field]: e.target.value });

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setTouched(true);
    if (Object.values(errors).some(Boolean)) return;
    const result = await registerUser(form);
    if ('error' in result) return;
    await dispatch(api.endpoints.me.initiate(undefined, { forceRefetch: true }));
    navigate('/', { replace: true });
  };

  const fieldError = (text: string) => touched && text && <p className="mt-1.5 text-sm text-coral-700">{text}</p>;

  return (
    <AuthShell title="Create an account" subtitle="Join your course in under a minute.">
      <form onSubmit={onSubmit} noValidate className="space-y-5">
        <div>
          <label htmlFor="name" className="mb-1.5 block text-sm font-semibold">Name</label>
          <input id="name" className="field" autoComplete="name" value={form.name} onChange={set('name')} />
          {fieldError(errors.name)}
        </div>
        <div>
          <label htmlFor="email" className="mb-1.5 block text-sm font-semibold">E-mail</label>
          <input id="email" className="field" type="email" autoComplete="username" value={form.email} onChange={set('email')} />
          {fieldError(errors.email)}
        </div>
        <div>
          <label htmlFor="password" className="mb-1.5 block text-sm font-semibold">Password</label>
          <input id="password" className="field" type="password" autoComplete="new-password" value={form.password} onChange={set('password')} />
          {fieldError(errors.password)}
        </div>
        <div>
          <label htmlFor="course" className="mb-1.5 block text-sm font-semibold">Course</label>
          <select id="course" className="field" value={form.course} onChange={set('course')}>
            {COURSES.map((c) => <option key={c}>{c}</option>)}
          </select>
        </div>
        {error && <p role="alert" className="rounded-xl bg-coral-50 px-4 py-2.5 text-sm text-coral-700">{errorDetail(error, 'Cannot reach the server. Try again.')}</p>}
        <button className="btn w-full" disabled={isLoading}>{isLoading ? 'Creating account…' : 'Register'}</button>
        <p className="text-center text-sm text-ink-500">Already registered? <Link className="link" to="/login">Log in</Link></p>
      </form>
    </AuthShell>
  );
}
