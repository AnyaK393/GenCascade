import { createSlice, type PayloadAction } from '@reduxjs/toolkit';
import type { Status } from '../types/api';

export type SocketState = 'connecting' | 'connected' | 'polling';

const statusSlice = createSlice({
  name: 'status',
  initialState: { current: null as Status | null, socket: 'connecting' as SocketState },
  reducers: {
    statusReceived(state, action: PayloadAction<Status>) {
      state.current = action.payload;
    },
    socketChanged(state, action: PayloadAction<SocketState>) {
      state.socket = action.payload;
    },
  },
});

export const { statusReceived, socketChanged } = statusSlice.actions;
export default statusSlice.reducer;
