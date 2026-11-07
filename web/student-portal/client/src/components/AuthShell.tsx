import type { ReactNode } from 'react';
import Icon from './Icon';
import { Logo, ShieldScene } from './Illustrations';

const POINTS = ['An AI tutor for every course', 'Quiz answers that survive heavy load', 'Live status through every exam'];

export default function AuthShell({ title, subtitle, children }: { title: string; subtitle: string; children: ReactNode }) {
  return (
    <div className="grid min-h-screen bg-canvas lg:grid-cols-[1.1fr_1fr]">
      <aside className="relative hidden flex-col justify-between overflow-hidden bg-brand-800 p-12 text-white lg:flex">
        <div className="absolute -right-32 -top-32 h-96 w-96 rounded-full bg-brand-700" aria-hidden="true" />
        <div className="absolute -bottom-40 -left-24 h-96 w-96 rounded-full bg-brand-900" aria-hidden="true" />
        <div className="relative flex items-center gap-3 text-xl font-extrabold"><Logo className="h-10 w-10 rounded-xl bg-white p-1" /> CascadeShield</div>
        <ShieldScene className="relative mx-auto w-full max-w-md animate-fade-up" />
        <div className="relative">
          <h2 className="text-3xl font-extrabold leading-tight">Keep learning, even on exam day.</h2>
          <ul className="mt-5 space-y-2.5 text-brand-100">
            {POINTS.map((p) => (
              <li key={p} className="flex items-center gap-3">
                <span className="flex h-6 w-6 items-center justify-center rounded-full bg-brand-600"><Icon name="check" className="h-3.5 w-3.5" /></span>
                {p}
              </li>
            ))}
          </ul>
        </div>
      </aside>
      <main className="flex items-center justify-center p-5 sm:p-10">
        <div className="w-full max-w-md animate-fade-up">
          <div className="mb-6 flex items-center gap-3 text-xl font-extrabold text-brand-800 lg:hidden"><Logo /> CascadeShield</div>
          <div className="mb-7 rounded-3xl bg-brand-800 p-4 lg:hidden"><ShieldScene className="mx-auto w-full max-w-[17rem]" /></div>
          <h1 className="text-3xl font-extrabold">{title}</h1>
          <p className="mb-7 mt-2 text-ink-500">{subtitle}</p>
          {children}
        </div>
      </main>
    </div>
  );
}
