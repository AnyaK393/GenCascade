import { GATEWAY_URL } from './config.js';

const POLL_MS = 2000;
const UNREACHABLE = {
  level: null,
  banner: 'Tutor service unreachable. Your quiz answers are kept in this browser.',
  color: 'red',
  exam: { active: false },
};

let latest = null;
export const getStatus = () => latest ?? UNREACHABLE;

const changed = (a, b) => !a || a.level !== b.level || a.banner !== b.banner || a.exam?.active !== b.exam?.active;

async function poll(io) {
  let next;
  try {
    const r = await fetch(`${GATEWAY_URL}/api/status`, { signal: AbortSignal.timeout(1500) });
    next = r.ok ? await r.json() : UNREACHABLE;
  } catch {
    next = UNREACHABLE;
  }
  const emit = changed(latest, next);
  latest = next;
  if (emit) io.emit('status', next);
}

export function startLiveStatus(io) {
  io.on('connection', (socket) => socket.emit('status', getStatus()));
  poll(io);
  setInterval(() => poll(io), POLL_MS).unref();
}
