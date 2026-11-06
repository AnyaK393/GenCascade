import { useEffect } from 'react';
import { io } from 'socket.io-client';
import { useAppDispatch } from '../store';
import { api } from '../store/api';
import { eventLogged } from '../store/inspectorSlice';
import { socketChanged, statusReceived } from '../store/statusSlice';
import type { Status } from '../types/api';

const POLL_MS = 3000;
const PORTAL_DOWN: Status = {
  level: null,
  banner: 'Student portal unreachable. Your quiz answers are kept in this browser.',
  color: 'red',
  exam: { active: false },
};

export function useLiveStatus() {
  const dispatch = useAppDispatch();

  useEffect(() => {
    let timer: number | undefined;

    const pollOnce = async () => {
      const result = await dispatch(api.endpoints.status.initiate(undefined, { forceRefetch: true, subscribe: false }));
      dispatch(statusReceived(result.data ?? PORTAL_DOWN));
    };
    const startPolling = () => {
      dispatch(socketChanged('polling'));
      if (timer === undefined) {
        void pollOnce();
        timer = window.setInterval(pollOnce, POLL_MS);
      }
    };
    const stopPolling = () => {
      window.clearInterval(timer);
      timer = undefined;
    };

    const socket = io({ withCredentials: true });
    socket.on('connect', () => {
      stopPolling();
      dispatch(socketChanged('connected'));
      dispatch(eventLogged({ name: 'connect', data: { transport: socket.io.engine.transport.name } }));
    });
    socket.on('status', (status: Status) => {
      dispatch(statusReceived(status));
      dispatch(eventLogged({ name: 'status', data: status }));
    });
    socket.on('connect_error', (error) => {
      dispatch(eventLogged({ name: 'connect_error', data: { message: error.message } }));
      startPolling();
    });
    socket.on('disconnect', (reason) => {
      dispatch(eventLogged({ name: 'disconnect', data: { reason } }));
      startPolling();
    });

    return () => {
      stopPolling();
      socket.disconnect();
    };
  }, [dispatch]);
}
