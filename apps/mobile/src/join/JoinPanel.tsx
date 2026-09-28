import { useCallback, useEffect, useRef, useState } from 'react';
import { Platform, Text, View } from 'react-native';
import { FilterChip, FormSurface, Button, Card, EmptyState, LoadingState, TeamBadge } from '../components/ui';
import { Field, FormError, TextAction } from '../components/AuthLayout';
import { getProfile } from '../auth/api';
import { useAuth } from '../auth/AuthContext';
import { useTeams } from '../teams/TeamContext';
import { categories, modalityLabels } from '../teams/api';
import * as api from './api';
import { styles as s } from './styles';

export function JoinPanel({ onBack, onTeams }: { onBack: () => void; onTeams: () => void }) {
  const { options } = useTeams();
  const { updateProfile } = useAuth();
  const [code, setCode] = useState(() => Platform.OS === 'web' ? new URLSearchParams(window.location.search).get('team_code') ?? '' : '');
  const [searchMode, setSearchMode] = useState(false);
  const [results, setResults] = useState<api.Lookup[] | null>(null);
  const [searchMore, setSearchMore] = useState(false);
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
    <View style={s.stack}>{[false, true].map(value => <FilterChip key={String(value)} label={value ? 'Encontrar um time' : 'Usar código/link'} selected={searchMode === value} onPress={() => { if (busy) return; setSearchMode(value); setCode(''); setFound(null); setResults(null); setError(null); }} />)}</View>
    <Text style={s.note}>Encontre seu time pelo nome, ID ou convite. A entrada depende de aprovação.</Text>
    <Field label={searchMode ? 'Busque pelo nome ou ID do time' : 'Código do time'} value={code} autoCapitalize="none" maxLength={searchMode ? 100 : 512} editable={!busy} onChangeText={value => { setCode(value); setFound(null); setResults(null); setSuccess(null); setError(null); }} />
    <Button label={busy ? 'Aguarde…' : 'Buscar time'} disabled={busy || code.trim().length < (searchMode ? 2 : 1)} onPress={() => void run(async () => {
      setFound(null); setResults(null);
      if (searchMode) { const value = await api.search(code); if (alive.current) { setResults(value.items); setSearchMore(value.has_more); } }
      else { const value = await api.lookup(code); if (alive.current) setFound(value); }
    })} />
    <FormError message={error} />
    {error && !searchMode && <TextAction label="Buscar um time" disabled={busy} onPress={() => { setSearchMode(true); setCode(''); setError(null); }} />}
    {success && <Text accessibilityLiveRegion="polite" style={s.success}>{success}</Text>}
    {results?.length === 0 && <EmptyState title="Nenhum time encontrado." description="Revise o nome/ID ou use o código de convite." />}
    {(results ?? (found ? [found] : [])).map(found => <Card key={found.team.id}><View style={s.stack}>
      <TeamBadge name={found.team.name} crestUrl={found.team.crest_url} />
      <Text style={s.heading}>{found.team.name}</Text><Text style={s.note}>{found.team.city} · {found.team.state}</Text>
      <Text style={s.note}>{modalityLabels(found.team.modalities, options.modalities)}</Text>
      <Text style={s.note}>{found.team.category ? categories[found.team.category] : 'Categoria não informada'}</Text>
      <Text selectable style={s.note}>ID: {found.team.code}</Text>
      {!found.pending && !found.membership_status && found.request_status === 'REJECTED' && <Text style={s.note}>Sua solicitação anterior não foi aprovada.</Text>}
      {found.membership_status ? <Text style={s.note}>{found.membership_status === 'active' ? 'Você já faz parte deste time.' : 'Seu vínculo está inativo. Peça ao responsável para reativá-lo no elenco.'}</Text> : found.pending ? <Text style={s.note}>Sua solicitação para este time já está aguardando aprovação.</Text> : <Button label="Solicitar entrada" disabled={busy} onPress={() => void run(async () => { await api.requestEntry(found.team); if (alive.current) { setFound({ ...found, pending: true }); setResults(current => current?.map(item => item.team.id === found.team.id ? { ...item, pending: true } : item) ?? null); setSuccess('Solicitação enviada. Aguardando aprovação do responsável pelo time.'); await load(); } })} />}
    </View></Card>)}
    {!!results?.length && searchMore && <Button label="Carregar mais times" disabled={busy} onPress={() => void run(async () => { const next = await api.search(code, results.length); if (alive.current) { setResults([...results, ...next.items]); setSearchMore(next.has_more); } })} />}
    <Text accessibilityRole="header" style={s.heading}>Meus pedidos</Text>
    <TextAction label="Atualizar pedidos" disabled={busy || loading} onPress={() => { setFound(null); setResults(null); void load(); }} />
    <FormError message={listError} />
    {loading ? <LoadingState /> : !listError && !items.length ? <EmptyState title="Você ainda não solicitou entrada em nenhum time." description="Use o código compartilhado pelo responsável para começar." /> : items.map(item => <Card key={item.id}><View style={s.stack}>
      <Text style={s.heading}>{item.team.name}</Text><Text style={s.note}>{api.statusLabels[item.status]}</Text>
      {item.status === 'PENDING' && <Button label={`Cancelar solicitação para ${item.team.name}`} disabled={busy} onPress={() => void run(async () => { await api.cancel(item.id); if (alive.current) { setFound(null); setResults(current => current?.map(found => found.team.id === item.team.id ? { ...found, pending: false, request_status: 'CANCELLED' } : found) ?? null); await load(); } })} />}
      {item.status === 'APPROVED' && <Button label="Ver meus times" disabled={busy} onPress={onTeams} />}
    </View></Card>)}
    {more && !loading && !listError && <Button label="Carregar pedidos anteriores" disabled={busy} onPress={() => void run(async () => { const next = await api.mine(items.length); if (alive.current) { setItems([...items, ...next]); setMore(next.length === 50); } })} />}
    <TextAction label="Voltar para meus times" disabled={busy} onPress={onBack} />
  </FormSurface>;
}
