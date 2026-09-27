import { createContext, useCallback, useContext, useEffect, useRef, useState, type PropsWithChildren } from 'react';
import { AppState } from 'react-native';
import * as api from './api';

const Context = createContext<{ count: number | null; refresh: () => Promise<void> } | null>(null);
export function NotificationProvider({ children }: PropsWithChildren) {
  const [count, setCount] = useState<number | null>(null);
  const revision = useRef(0);
  const refresh = useCallback(async () => {
    const current = ++revision.current;
    try { const data = await api.unread(); if (current === revision.current) setCount(data.count); }
    catch { if (current === revision.current) setCount(null); }
  }, []);
  useEffect(() => {
    const counter = revision;
    void refresh();
    const subscription = AppState.addEventListener('change', state => { if (state === 'active') void refresh(); });
    return () => { counter.current++; subscription.remove(); };
  }, [refresh]);
  return <Context.Provider value={{ count, refresh }}>{children}</Context.Provider>;
}
export function useNotifications() {
  const value = useContext(Context);
  if (!value) throw new Error('NotificationProvider is required');
  return value;
}
