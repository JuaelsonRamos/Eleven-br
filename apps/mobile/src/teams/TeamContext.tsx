import { createContext, useCallback, useContext, useEffect, useRef, useState, type PropsWithChildren } from 'react';
import { AppState } from 'react-native';
import * as api from './api';
import { readSelection, storeSelection } from './selection';

type State = {
  teams: api.Team[]; selected: api.Team | null; options: api.Options;
  loading: boolean; error: string | null; warning: string | null;
  reload: () => Promise<void>; select: (id: string) => Promise<void>;
  saved: (team: api.Team) => Promise<void>;
};
const Context = createContext<State | null>(null);

export function TeamProvider({ userId, children }: PropsWithChildren<{ userId: string }>) {
  const [teams, setTeams] = useState<api.Team[]>([]);
  const [selected, setSelected] = useState<api.Team | null>(null);
  const [options, setOptions] = useState<api.Options>({ modalities: [], states: [] });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [warning, setWarning] = useState<string | null>(null);
  const selection = useRef<string | null | undefined>(undefined);
  const revision = useRef(0);
  const writes = useRef(Promise.resolve());

  const persist = useCallback((id: string | null) => {
    // Keep native asynchronous writes ordered when the user switches quickly.
    writes.current = writes.current.then(() => storeSelection(userId, id)).catch(() => {
      setWarning('Não foi possível lembrar o time neste dispositivo.');
    });
    return writes.current;
  }, [userId]);

  const reload = useCallback(async () => {
    const current = ++revision.current;
    setLoading(true); setError(null); setSelected(null);
    try {
      let preferred = selection.current;
      if (preferred === undefined) {
        try { preferred = await readSelection(userId); }
        catch { preferred = null; setWarning('Não foi possível recuperar o time salvo.'); }
      }
      const [list, vocabulary] = await Promise.all([api.listTeams(), api.getOptions()]);
      if (current !== revision.current) return;
      // An authenticated membership list validates the stored ID before exposing data.
      const active = list.find(team => team.id === preferred) ?? list[0] ?? null;
      selection.current = active?.id ?? null;
      setTeams(list); setOptions(vocabulary); setSelected(active);
      await persist(selection.current);
    } catch (cause) {
      if (current === revision.current) {
        setTeams([]); setError(cause instanceof Error ? cause.message : 'Não foi possível carregar os times.');
      }
    } finally { if (current === revision.current) setLoading(false); }
  }, [persist, userId]);

  useEffect(() => {
    const counter = revision;
    void reload();
    const subscription = AppState.addEventListener('change', state => { if (state === 'active') void reload(); });
    return () => { counter.current++; subscription.remove(); };
  }, [reload]);

  async function select(id: string) {
    const current = ++revision.current;
    setLoading(true); setError(null); setSelected(null);
    try {
      const team = await api.getTeam(id);
      if (current !== revision.current) return;
      selection.current = team.id; setSelected(team);
      setTeams(list => list.map(item => item.id === team.id ? team : item));
      await persist(team.id);
    } catch (cause) {
      if (current !== revision.current) return;
      selection.current = null; await persist(null);
      setError(cause instanceof Error ? cause.message : 'Não foi possível selecionar o time.');
    } finally { if (current === revision.current) setLoading(false); }
  }

  async function saved(team: api.Team) {
    revision.current++;
    selection.current = team.id;
    setTeams(list => [...list.filter(item => item.id !== team.id), team].sort((a, b) => a.name.localeCompare(b.name)));
    setSelected(team); setError(null); setLoading(false);
    await persist(team.id);
  }

  return <Context.Provider value={{ teams, selected, options, loading, error, warning, reload, select, saved }}>
    {children}
  </Context.Provider>;
}

export function useTeams() {
  const context = useContext(Context);
  if (!context) throw new Error('TeamProvider is required');
  return context;
}
