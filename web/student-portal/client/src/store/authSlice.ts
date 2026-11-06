import { createSlice, isAnyOf } from '@reduxjs/toolkit';
import type { Me } from '../types/api';
import { api } from './api';

const authSlice = createSlice({
  name: 'auth',
  initialState: { user: null as Me | null },
  reducers: {},
  extraReducers: (builder) => {
    builder.addMatcher(api.endpoints.me.matchFulfilled, (state, action) => {
      state.user = action.payload;
    });
    builder.addMatcher(isAnyOf(api.endpoints.me.matchRejected, api.endpoints.logout.matchFulfilled), (state) => {
      state.user = null;
    });
  },
});

export default authSlice.reducer;
