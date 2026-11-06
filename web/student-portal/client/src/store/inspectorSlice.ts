import { createSlice, type PayloadAction } from '@reduxjs/toolkit';

export interface RequestEntry {
  id: number;
  method: string;
  path: string;
  status: number | string;
  latency_ms: number;
  request_id?: string;
  level?: number;
  source?: string;
  body: unknown;
}

export interface LiveEvent {
  id: number;
  at: string;
  name: string;
  data: unknown;
}

const MAX_ENTRIES = 20;

const inspectorSlice = createSlice({
  name: 'inspector',
  initialState: { requests: [] as RequestEntry[], events: [] as LiveEvent[], nextId: 1 },
  reducers: {
    requestLogged(state, action: PayloadAction<Omit<RequestEntry, 'id'>>) {
      state.requests = [{ ...action.payload, id: state.nextId++ }, ...state.requests].slice(0, MAX_ENTRIES);
    },
    eventLogged(state, action: PayloadAction<Omit<LiveEvent, 'id' | 'at'>>) {
      const entry = { ...action.payload, id: state.nextId++, at: new Date().toISOString() };
      state.events = [entry, ...state.events].slice(0, MAX_ENTRIES);
    },
  },
});

export const { requestLogged, eventLogged } = inspectorSlice.actions;
export default inspectorSlice.reducer;
