import { createSlice, nanoid, type PayloadAction } from '@reduxjs/toolkit';
import type { AskResponse, Course } from '../types/api';

export interface Message {
  id: string;
  role: 'user' | 'bot' | 'error';
  text: string;
  pending?: boolean;
  level?: number;
  source?: string;
  latency_ms?: number;
  queue_id?: string;
  position?: number | null;
}

const chatSlice = createSlice({
  name: 'chat',
  initialState: { byCourse: {} as Partial<Record<Course, Message[]>> },
  reducers: {
    questionSent: {
      reducer(state, action: PayloadAction<{ course: Course; question: string; userId: string; botId: string }>) {
        const { course, question, userId, botId } = action.payload;
        (state.byCourse[course] ??= []).push(
          { id: userId, role: 'user', text: question },
          { id: botId, role: 'bot', text: '', pending: true },
        );
      },
      prepare(course: Course, question: string, botId: string) {
        return { payload: { course, question, botId, userId: nanoid() } };
      },
    },
    answerReceived(state, action: PayloadAction<{ course: Course; botId: string; response: AskResponse }>) {
      const { course, botId, response: r } = action.payload;
      const message = state.byCourse[course]?.find((m) => m.id === botId);
      if (message) {
        Object.assign(message, {
          pending: false, text: r.answer, level: r.level, source: r.source, latency_ms: r.latency_ms,
          queue_id: r.queue_id, position: r.position,
        });
      }
    },
    askFailed(state, action: PayloadAction<{ course: Course; botId: string; text: string }>) {
      const { course, botId, text } = action.payload;
      const message = state.byCourse[course]?.find((m) => m.id === botId);
      if (message) Object.assign(message, { pending: false, role: 'error', text });
    },
    queueUpdated(state, action: PayloadAction<{ queueId: string; position?: number | null; answer?: string; level?: number; source?: string }>) {
      const { queueId, position, answer, level, source } = action.payload;
      for (const messages of Object.values(state.byCourse)) {
        const message = messages?.find((m) => m.queue_id === queueId);
        if (!message) continue;
        message.position = position;
        if (answer !== undefined) Object.assign(message, { text: answer, level, source, queue_id: undefined });
      }
    },
    chatCleared(state) {
      state.byCourse = {};
    },
  },
});

export const { questionSent, answerReceived, askFailed, queueUpdated, chatCleared } = chatSlice.actions;
export default chatSlice.reducer;
