import { useCallback, useEffect, useRef, useState } from 'react';
import { Text, View } from 'react-native';
import { FormSurface, Button, Card, EmptyState, LoadingState, TeamBadge } from '../components/ui';
import { Field, FormError, TextAction } from '../components/AuthLayout';
import { getProfile } from '../auth/api';
import { useAuth } from '../auth/AuthContext';
import { useTeams } from '../teams/TeamContext';
import { modalityLabels } from '../teams/api';
import * as api from './api';
import { styles as s } from './styles';

export function JoinPanel({ onBack, onTeams }: { onBack: () => void; onTeams: () => void }) {
  const { options } = useTeams();
  const { updateProfile } = useAuth();
  const [code, setCode] = useState('');
  const [found, setFound] = useState<api.Lookup | null>(null);
  const [items, setItems] = useState<api.JoinRequest[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [more, setMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [listError, setListError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const alive = useRef(true);
  const sending = useRef(false);
  const load = useCallback(async () => {
    setLoading(true); setListError(null);
    try {
      const [requests, profile] = await Promise.all([api.mine(), getProfile()]);
      if (alive.current) { setItems(requests); setMore(requests.length === 50); updateProfile(profile); }
    } catch (cause) { if (alive.current) { setItems([]); setListError(cause instanceof Error ? cause.message : 'Não foi possível carregar seus pedidos.'); } }
    finally { if (alive.current) setLoading(false); }
  }, [updateProfile]);
  // AuthContext's update function changes with its value. Load on mount, refresh explicitly thereafter.
  const initialLoad = useRef(load);
  useEffect(() => { alive.current = true; void initialLoad.current(); return () => { alive.current = false; }; }, []);
  async function run(action: () => Promise<void>) {
    if (sending.current) return;
    sending.current = true; setBusy(true); setError(null); setSuccess(null);
    try { await action(); }
    catch (cause) { if (alive.current) setError(cause instanceof Error ? cause.message : 'Não foi possível concluir.'); }
    finally { sending.current = false; if (alive.current) setBusy(false); }
  }
  return <FormSurface>
    <Text style={s.note}>Digite o código compartilhado pelo responsável. A entrada depende de aprovação.</Text>
    <Field label="Código do time" value={code} autoCapitalize="characters" maxLength={64} editable={!busy} onChangeText={value => { setCode(value); setFound(null); setSuccess(null); setError(null); }} />
    <Button label={busy ? 'Aguarde…' : 'Buscar time'} disabled={busy || !code.trim()} onPress={() => void run(async () => { setFound(null); const value = await api.lookup(code); if (alive.current) setFound(value); })} />
    <FormError message={error} />
    {success && <Text accessibilityLiveRegion="polite" style={s.success}>{success}</Text>}
    {found && <Card><View style={s.stack}>
      <TeamBadge name={found.team.name} crestUrl={found.team.crest_url} />
      <Text style={s.heading}>{found.team.name}</Text><Text style={s.note}>{found.team.city} · {found.team.state}</Text>
      <Text style={s.note}>{modalityLabels(found.team.modalities, options.modalities)}</Text>
      {found.membership_status ? <Text style={s.note}>{found.membership_status === 'active' ? 'Você já faz parte deste time.' : 'Seu vínculo está inativo. Peça ao responsável para reativá-lo no elenco.'}</Text> : found.pending ? <Text style={s.note}>Sua solicitação para este time já está aguardando aprovação.</Text> : <Button label="Solicitar entrada" disabled={busy} onPress={() => void run(async () => { await api.requestEntry(found.team); if (alive.current) { setFound({ ...found, pending: true }); setSuccess('Solicitação enviada. Aguardando aprovação do responsável pelo time.'); await load(); } })} />}
    </View></Card>}
    <Text accessibilityRole="header" style={s.heading}>Meus pedidos</Text>
    <TextAction label="Atualizar pedidos" disabled={busy || loading} onPress={() => { setFound(null); void load(); }} />
    <FormError message={listError} />
    {loading ? <LoadingState /> : !listError && !items.length ? <EmptyState title="Você ainda não solicitou entrada em nenhum time." description="Use o código compartilhado pelo responsável para começar." /> : items.map(item => <Card key={item.id}><View style={s.stack}>
      <Text style={s.heading}>{item.team.name}</Text><Text style={s.note}>{api.statusLabels[item.status]}</Text>
      {item.status === 'PENDING' && <Button label={`Cancelar solicitação para ${item.team.name}`} disabled={busy} onPress={() => void run(async () => { await api.cancel(item.id); if (alive.current) { setFound(null); await load(); } })} />}
      {item.status === 'APPROVED' && <Button label="Ver meus times" disabled={busy} onPress={onTeams} />}
    </View></Card>)}
    {more && !loading && !listError && <Button label="Carregar pedidos anteriores" disabled={busy} onPress={() => void run(async () => { const next = await api.mine(items.length); if (alive.current) { setItems([...items, ...next]); setMore(next.length === 50); } })} />}
    <TextAction label="Voltar para meus times" disabled={busy} onPress={onBack} />
  </FormSurface>;
}
