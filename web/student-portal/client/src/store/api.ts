import { createApi, fetchBaseQuery, type BaseQueryFn, type FetchArgs, type FetchBaseQueryError } from '@reduxjs/toolkit/query/react';
import type {
  AnswerList, AskRequest, AskResponse, Course, Me, PracticeResult, Profile, QueuedResponse, Quiz, Status,
  SubmitRequest, SubmitResponse,
} from '../types/api';
import { requestLogged } from './inspectorSlice';

const rawQuery = fetchBaseQuery({ credentials: 'same-origin' });

/** Records each call for the network inspector. Only responses are kept, so passwords never enter the log. */
const loggedQuery: BaseQueryFn<string | FetchArgs, unknown, FetchBaseQueryError> = async (args, baseApi, extra) => {
  const t0 = performance.now();
  const result = await rawQuery(args, baseApi, extra);
  const body = (result.data ?? result.error?.data) as Record<string, unknown> | undefined;
  const path = typeof args === 'string' ? args : args.url;
  baseApi.dispatch(requestLogged({
    method: typeof args === 'string' ? 'GET' : args.method ?? 'GET',
    path,
    status: result.meta?.response?.status ?? 'network error',
    latency_ms: Math.round(performance.now() - t0),
    request_id: body?.request_id as string | undefined,
    level: body?.level as number | undefined,
    source: body?.source as string | undefined,
    body,
  }));
  // Session expired mid-use: clearing the cache makes RequireAuth re-check and redirect.
  if (result.error?.status === 401 && !path.startsWith('/auth/')) baseApi.dispatch(api.util.resetApiState());
  return result;
};

export const api = createApi({
  reducerPath: 'api',
  baseQuery: loggedQuery,
  tagTypes: ['Profile'],
  endpoints: (b) => ({
    me: b.query<Me, void>({ query: () => '/auth/me' }),
    login: b.mutation<unknown, { email: string; password: string }>({
      query: (body) => ({ url: '/auth/login', method: 'POST', body }),
    }),
    register: b.mutation<unknown, { name: string; email: string; password: string; course: Course }>({
      query: (body) => ({ url: '/auth/register', method: 'POST', body }),
    }),
    logout: b.mutation<unknown, void>({ query: () => ({ url: '/auth/logout', method: 'POST' }) }),
    ask: b.mutation<AskResponse, AskRequest>({
      query: (body) => ({ url: '/api/tutor/ask', method: 'POST', body }),
    }),
    queued: b.query<QueuedResponse, string>({ query: (id) => `/api/tutor/queued/${encodeURIComponent(id)}` }),
    quiz: b.query<Quiz, Course>({ query: (course) => `/api/quizzes/${course}` }),
    practice: b.mutation<PracticeResult, { course: Course; answers: AnswerList }>({
      query: ({ course, answers }) => ({ url: `/api/quizzes/${course}/practice`, method: 'POST', body: { answers } }),
    }),
    submit: b.mutation<SubmitResponse, SubmitRequest>({
      query: (body) => ({ url: '/api/quiz/submit', method: 'POST', body }),
    }),
    profile: b.query<Profile, void>({ query: () => '/api/profile' }),
    status: b.query<Status, void>({ query: () => '/api/status' }),
  }),
});

export const {
  useMeQuery, useLoginMutation, useRegisterMutation, useLogoutMutation, useAskMutation, useQueuedQuery,
  useQuizQuery, usePracticeMutation, useSubmitMutation, useProfileQuery,
} = api;
