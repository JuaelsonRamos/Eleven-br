import { useCallback, useEffect, useRef, useState } from 'react';
import { BackHandler, Pressable, Text, View } from 'react-native';
import { useFocusEffect } from '@react-navigation/native';
import { Avatar, Button, Card, EmptyState, LoadingState } from '../components/ui';
import { FormError, TextAction } from '../components/AuthLayout';
import { ApiError } from '../auth/api';
import * as api from './api';
import { styles as s } from './styles';

export function JoinAdminPanel({ teamId, onBack }: { teamId: string; onBack: () => void }) {
  const [items, setItems] = useState<api.AdminRequest[]>([]);
  const [detail, setDetail] = useState<api.Detail | null>(null);
  const [choice, setChoice] = useState<string | null | undefined>(undefined);
  const [confirm, setConfirm] = useState<'approve' | 'reject' | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const generation = useRef(0);
  const sending = useRef(false);
  const load = useCallback(async () => {
    const current = ++generation.current;
    setLoading(true); setError(null); setDetail(null); setConfirm(null); setChoice(undefined);
    try { const value = await api.pending(teamId); if (current === generation.current) setItems(value); }
    catch (cause) { if (current === generation.current) { setItems([]); setError(cause instanceof Error ? cause.message : 'Não foi possível carregar as solicitações.'); } }
    finally { if (current === generation.current) setLoading(false); }
  }, [teamId]);
  useEffect(() => { const counter = generation; void load(); return () => { counter.current++; }; }, [load]);
  useFocusEffect(useCallback(() => {
    const handler = BackHandler.addEventListener('hardwareBackPress', () => {
      if (sending.current) return true;
      if (confirm) setConfirm(null); else if (detail) void load(); else onBack();
      return true;
    });
    return () => handler.remove();
  }, [confirm, detail, load, onBack]));
  async function open(id: string) {
    const current = ++generation.current; setLoading(true); setError(null); setSuccess(null);
    try { const value = await api.detail(teamId, id); if (current === generation.current) { setDetail(value); setChoice(undefined); setConfirm(null); } }
    catch (cause) { if (current === generation.current) setError(cause instanceof Error ? cause.message : 'Não foi possível abrir o pedido.'); }
    finally { if (current === generation.current) setLoading(false); }
  }
  async function resolve() {
    if (!detail || !confirm || sending.current || (confirm === 'approve' && choice === undefined)) return;
    const current = generation.current; sending.current = true; setBusy(true); setError(null);
    try {
      if (confirm === 'approve') await api.approve(teamId, detail.request.id, choice ?? null);
      else await api.reject(teamId, detail.request.id);
      if (current === generation.current) { setBusy(false); setSuccess(confirm === 'approve' ? 'Solicitação aprovada. Histórico preservado.' : 'Solicitação recusada.'); await load(); }
    } catch (cause) {
      if (current === generation.current) {
        setError(cause instanceof Error ? cause.message : 'Não foi possível concluir.'); setConfirm(null);
        if (cause instanceof ApiError && [403, 404].includes(cause.status)) { setDetail(null); setItems([]); }
      }
    } finally { sending.current = false; if (current === generation.current) setBusy(false); }
  }
  const candidate = detail?.candidates.find(item => item.membership_id === choice);
  return <View style={s.stack}>
    <Text accessibilityRole="header" style={s.heading}>Solicitações de entrada</Text>
    <FormError message={error} />
    {success && <Text accessibilityLiveRegion="polite" style={s.success}>{success}</Text>}
    {loading ? <LoadingState /> : detail ? <>
      <Text style={s.heading}>{detail.request.name}</Text><Text style={s.note}>{detail.request.masked_contact}</Text>
      {confirm ? <Card><View style={s.stack}>
        <Text style={s.heading}>{confirm === 'reject' ? `Recusar solicitação de ${detail.request.name}?` : choice ? `Vincular esta conta a ${candidate?.name}?` : `Adicionar ${detail.request.name} ao elenco?`}</Text>
        {confirm === 'approve' && <Text style={s.note}>{choice ? 'O jogador e seu histórico serão preservados. A conta terá acesso de jogador.' : 'Será usada a identidade esportiva da conta, respeitando o limite do plano.'}</Text>}
        <Button label={busy ? 'Salvando…' : confirm === 'approve' ? 'Confirmar aprovação' : 'Confirmar recusa'} disabled={busy} onPress={() => void resolve()} />
        <TextAction label="Voltar à análise" disabled={busy} onPress={() => setConfirm(null)} />
      </View></Card> : <>
        <Text style={s.text}>Vincular ao elenco</Text>
        {detail.identity_conflict && <Text style={s.note}>{detail.identity_conflict}</Text>}
        {(['active', 'inactive', 'removed'] as const).map(status => <View key={status} style={s.stack}>
          {detail.candidates.some(item => item.status === status) && <Text style={s.note}>{status === 'active' ? 'Jogadores sem conta' : status === 'inactive' ? 'Jogadores inativos' : 'Jogadores removidos · aprovar retorno'}</Text>}
          {detail.candidates.filter(item => item.status === status).map(item => <Pressable key={item.membership_id} accessibilityRole="radio" accessibilityLabel={`Vincular a ${item.name}`} accessibilityState={{ checked: choice === item.membership_id, disabled: !!item.unavailable_reason }} disabled={!!item.unavailable_reason} onPress={() => setChoice(item.membership_id)} style={[s.choice, choice === item.membership_id && s.selected]}>
            <View style={s.row}><Avatar name={item.name} photoUrl={item.photo_url} size={36} /><Text style={[s.text, { flex: 1 }]}>{choice === item.membership_id ? '✓ ' : ''}{item.name}</Text></View>
            {item.unavailable_reason && <Text style={s.note}>{item.unavailable_reason}</Text>}
          </Pressable>)}
        </View>)}
        <Pressable accessibilityRole="radio" accessibilityLabel="Nenhum destes — adicionar ao elenco" accessibilityState={{ checked: choice === null }} onPress={() => setChoice(null)} style={[s.choice, choice === null && s.selected]}><Text style={s.text}>{choice === null ? '✓ ' : ''}Nenhum destes — adicionar ao elenco</Text></Pressable>
        <Button label="Aprovar" disabled={choice === undefined || busy} onPress={() => setConfirm('approve')} />
        <TextAction label="Recusar" disabled={busy} onPress={() => setConfirm('reject')} />
      </>}
      <TextAction label="Voltar às solicitações" disabled={busy} onPress={() => void load()} />
    </> : <>
      <Text style={s.note}>{items.length} {items.length === 1 ? 'pendente' : 'pendentes'}</Text>
      <TextAction label="Atualizar solicitações" onPress={() => { setSuccess(null); void load(); }} />
      {!items.length && !error && <EmptyState title="Nenhuma solicitação pendente." description="Os pedidos de entrada neste time aparecerão aqui." />}
      {items.map(item => <Card key={item.id}><View style={s.stack}>
        <Text style={s.heading}>{item.name}</Text><Text style={s.note}>{item.masked_contact}</Text>
        <Text style={s.note}>Solicitado em {new Date(item.created_at).toLocaleDateString('pt-BR')}</Text>
        <Button label={`Analisar ${item.name}`} onPress={() => void open(item.id)} />
      </View></Card>)}
    </>}
    <TextAction label="Voltar ao elenco" disabled={busy} onPress={onBack} />
  </View>;
}
