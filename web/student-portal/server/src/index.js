import fs from 'node:fs';
import http from 'node:http';
import { fileURLToPath } from 'node:url';
import cookieParser from 'cookie-parser';
import cors from 'cors';
import express from 'express';
import helmet from 'helmet';
import morgan from 'morgan';
import { Server } from 'socket.io';
import { COOKIE, verifyToken } from './auth.js';
import { IS_PROD, PORT } from './config.js';
import { startLiveStatus } from './liveStatus.js';
import apiRoutes from './routes/api.js';
import authRoutes from './routes/auth.js';

const DIST = fileURLToPath(new URL('../../client/dist/', import.meta.url));
const LOGS = fileURLToPath(new URL('../logs/', import.meta.url));
fs.mkdirSync(LOGS, { recursive: true });

const app = express();
app.use(helmet({
  contentSecurityPolicy: {
    directives: {
      defaultSrc: ["'self'"],
      scriptSrc: ["'self'"],
      styleSrc: ["'self'", "'unsafe-inline'"],
      connectSrc: ["'self'", 'ws:', 'wss:'],
      imgSrc: ["'self'", 'data:'],
      upgradeInsecureRequests: null, // served over plain HTTP on the LAN; upgrading would break every asset
    },
  },
  strictTransportSecurity: false,
  crossOriginOpenerPolicy: false, // ignored on plain HTTP origins and logs a browser warning
}));
app.use(morgan('combined', { stream: fs.createWriteStream(`${LOGS}access.log`, { flags: 'a' }) }));
app.use(express.json({ limit: '100kb' }));
app.use(cookieParser());
if (!IS_PROD) app.use(cors({ origin: 'http://localhost:5173', credentials: true }));

app.get('/health', (req, res) => res.json({ ok: true }));
app.use('/auth', authRoutes);
app.use('/api', apiRoutes);

app.use(express.static(DIST));
app.use((req, res, next) => {
  const isApi = /^\/(api|auth|socket\.io)(\/|$)/.test(req.path);
  if (req.method !== 'GET' || isApi) return res.status(404).json({ detail: 'Not found' });
  res.sendFile('index.html', { root: DIST }, (err) => err && next(err));
});

app.use((err, req, res, next) => {
  const status = err.status || err.statusCode || 500;
  if (status >= 500) console.error(err);
  if (res.headersSent) return next(err);
  res.status(status).json({ detail: status < 500 ? err.message : 'Server error' });
});

const server = http.createServer(app);
const io = new Server(server);
io.use((socket, next) => {
  cookieParser()(socket.request, {}, () => {
    next(verifyToken(socket.request.cookies?.[COOKIE]) ? undefined : new Error('unauthorized'));
  });
});
startLiveStatus(io);

server.listen(PORT, () => console.log(`student portal on :${PORT}`));
