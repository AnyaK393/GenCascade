import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useAppSelector } from '../store';

type Tab = 'Requests' | 'Live events' | 'Session';
const TABS: Tab[] = ['Requests', 'Live events', 'Session'];

function Requests() {
  const requests = useAppSelector((s) => s.inspector.requests);
  const [openId, setOpenId] = useState<number | null>(null);
  const open = requests.find((r) => r.id === openId);
  if (!requests.length) return <p className="text-slate-400">No requests yet.</p>;
  return (
    <>
      <table className="w-full text-left text-xs">
        <thead className="text-slate-400">
          <tr><th>Method</th><th>Path</th><th>Status</th><th>ms</th><th>Level</th><th>Source</th><th>Request id</th></tr>
        </thead>
        <tbody>
          {requests.map((r) => (
            <tr key={r.id} tabIndex={0} className="cursor-pointer hover:bg-slate-800"
              onClick={() => setOpenId(r.id)} onKeyDown={(e) => e.key === 'Enter' && setOpenId(r.id)}>
              <td>{r.method}</td><td className="break-all">{r.path}</td><td>{r.status}</td><td>{r.latency_ms}</td>
              <td>{r.level ?? '-'}</td><td>{r.source ?? '-'}</td><td>{r.request_id?.slice(0, 8) ?? '-'}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {open && <pre className="mt-2 overflow-x-auto rounded bg-slate-800 p-2 text-xs">{JSON.stringify(open.body, null, 2)}</pre>}
    </>
  );
}

function Events() {
  const events = useAppSelector((s) => s.inspector.events);
  if (!events.length) return <p className="text-slate-400">No events yet.</p>;
  return (
    <ul className="space-y-1 text-xs">
      {events.map((e) => (
        <li key={e.id} className="break-all">
          <span className="text-slate-400">{new Date(e.at).toLocaleTimeString()}</span> <b>{e.name}</b> {JSON.stringify(e.data)}
        </li>
      ))}
    </ul>
  );
}

function Session() {
  const user = useAppSelector((s) => s.auth.user);
  const socket = useAppSelector((s) => s.status.socket);
  return <pre className="text-xs">{JSON.stringify({ claims: user, socket }, null, 2)}</pre>;
}

export default function NetworkInspector() {
  const [params] = useSearchParams();
  const [open, setOpen] = useState(params.get('debug') === '1');
  const [tab, setTab] = useState<Tab>('Requests');

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.ctrlKey && e.shiftKey && e.key.toLowerCase() === 'd') {
        e.preventDefault();
        setOpen((v) => !v);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  if (!open) return null;
  return (
    <aside aria-label="Network inspector" className="fixed inset-x-0 bottom-0 z-40 h-72 overflow-y-auto border-t border-slate-700 bg-slate-900 p-3 text-slate-100">
      <div className="mb-2 flex items-center gap-2">
        {TABS.map((t) => (
          <button key={t} onClick={() => setTab(t)} className={`rounded px-2 py-1 text-sm ${tab === t ? 'bg-indigo-600' : 'bg-slate-700'}`}>{t}</button>
        ))}
        <button onClick={() => setOpen(false)} className="ml-auto rounded bg-slate-700 px-2 py-1 text-sm">Close</button>
      </div>
      {tab === 'Requests' && <Requests />}
      {tab === 'Live events' && <Events />}
      {tab === 'Session' && <Session />}
    </aside>
  );
}
