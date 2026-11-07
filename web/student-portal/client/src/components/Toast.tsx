import { createContext, useCallback, useContext, useMemo, useRef, useState, type ReactNode } from 'react';

const TOAST_MS = 5000;
const ToastContext = createContext<(text: string) => void>(() => {});

export const useToast = () => useContext(ToastContext);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<{ id: number; text: string }[]>([]);
  const nextId = useRef(1);

  const show = useCallback((text: string) => {
    const id = nextId.current++;
    setToasts((all) => [...all, { id, text }]);
    setTimeout(() => setToasts((all) => all.filter((t) => t.id !== id)), TOAST_MS);
  }, []);
  const value = useMemo(() => show, [show]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div aria-live="polite" className="fixed bottom-4 right-4 z-50 flex max-w-xs flex-col gap-2">
        {toasts.map((t) => (
          <div key={t.id} className="animate-pop rounded-xl bg-ink-900 px-4 py-3 text-sm font-medium text-white shadow-lift">{t.text}</div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}
