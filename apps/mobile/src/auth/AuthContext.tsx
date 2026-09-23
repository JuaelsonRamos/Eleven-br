import { createContext, useCallback, useContext, useEffect, useState, type PropsWithChildren } from 'react';
import * as api from './api';

type AuthState = {
  profile: api.Profile | null; ticket: api.Verification | null; booting: boolean; bootError: string | null;
  startAtLogin: boolean;
  restore: () => Promise<void>; finish: (result: api.AuthResult) => Promise<void>;
  setTicket: (ticket: api.Verification | null) => void; signOut: () => Promise<void>;
  complete: (name: string) => Promise<void>;
  updateProfile: (updated: api.Profile) => void;
};
const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: PropsWithChildren) {
  const [profile, setProfile] = useState<api.Profile | null>(null);
  const [ticket, setTicket] = useState<api.Verification | null>(null);
  const [booting, setBooting] = useState(true);
  const [bootError, setBootError] = useState<string | null>(null);
  const [startAtLogin, setStartAtLogin] = useState(false);

  const restore = useCallback(async () => {
    setBooting(true); setBootError(null);
    try { setProfile(await api.refresh() ? await api.getProfile() : null); }
    catch (error) { setBootError(error instanceof Error ? error.message : 'Não foi possível restaurar sua sessão.'); }
    finally { setBooting(false); }
  }, []);

  useEffect(() => {
    api.setExpiryHandler(() => { setProfile(null); setTicket(null); setStartAtLogin(true); });
    void restore();
    return () => api.setExpiryHandler(() => {});
  }, [restore]);

  async function finish(result: api.AuthResult) {
    if (result.status === 'verification_required') { setTicket(result); return; }
    await api.acceptTokens(result);
    setTicket(null);
    // Keep bootstrap retry available if profile loading fails after a successful login.
    setBooting(true);
    try { setProfile(await api.getProfile()); }
    catch (error) { setBootError(error instanceof Error ? error.message : 'Não foi possível carregar seu perfil.'); }
    finally { setBooting(false); }
  }
  async function signOut() {
    await api.logout();
    setStartAtLogin(true); setProfile(null); setTicket(null); setBootError(null);
  }
  async function complete(name: string) { setProfile(await api.saveProfile(name)); }
  function updateProfile(updated: api.Profile) { setProfile(current => current?.user_id === updated.user_id ? updated : current); }

  return <AuthContext.Provider value={{ profile, ticket, booting, bootError, startAtLogin, restore, finish, setTicket, signOut, complete, updateProfile }}>
    {children}
  </AuthContext.Provider>;
}

export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) throw new Error('AuthProvider is required');
  return value;
}
