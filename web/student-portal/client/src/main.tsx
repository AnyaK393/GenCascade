import '@fontsource-variable/manrope';
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { Provider } from 'react-redux';
import { RouterProvider } from 'react-router-dom';
import ErrorBoundary from './components/ErrorBoundary';
import { ToastProvider } from './components/Toast';
import './index.css';
import { router } from './routes';
import { store } from './store';

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ErrorBoundary>
      <Provider store={store}>
        <ToastProvider>
          <RouterProvider router={router} />
        </ToastProvider>
      </Provider>
    </ErrorBoundary>
  </StrictMode>,
);
