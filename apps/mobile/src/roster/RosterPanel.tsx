import { useCallback, useEffect, useRef, useState } from 'react';
import { BackHandler, Pressable, Text, View } from 'react-native';
import { useFocusEffect } from '@react-navigation/native';
import { Avatar, Badge, Button, Card, EmptyState, LoadingState } from '../components/ui';
import { FormError, TextAction } from '../components/AuthLayout';
import { ApiError } from '../auth/api';
import type { Team } from '../teams/api';
import { changeStatus, getPerson, listRoster, type RosterFilter, type RosterPage, type RosterPerson } from './api';
import { PlayerForm } from './PlayerForm';
import { rosterStyles as styles } from './styles';

export function RosterPanel({ team, onBack }: { team: Team; onBack: () => void }) {
  const [filter, setFilter] = useState<RosterFilter>('active');
  const [page, setPage] = useState<RosterPage | null>(null);
  const [player, setPlayer] = useState<RosterPerson | null>(null);
  const [mode, setMode] = useState<'list' | 'detail' | 'add' | 'edit'>('list');
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const generation = useRef(0);
  const mutation = useRef(false);
  const reload = useCallback(async () => {
    const current = ++generation.current;
    setLoading(true); setError(null);
    try { const value = await listRoster(team.id, filter); if (current === generation.current) setPage(value); }
    catch (cause) { if (current === generation.current) { setPage(null); setPlayer(null); setMode('list'); setError(cause instanceof Error ? cause.message : 'Não foi possível carregar o elenco.'); } }
    finally { if (current === generation.current) setLoading(false); }
  }, [filter, team.id]);
  useEffect(() => { const counter = generation; void reload(); return () => { counter.current++; }; }, [reload]);
  useFocusEffect(useCallback(() => {
    const handler = BackHandler.addEventListener('hardwareBackPress', () => {
      if (busy) return true;
      if (confirm) setConfirm(false);
      else if (mode !== 'list') { setMode('list'); setPlayer(null); }
      else onBack();
      return true;
    });
    return () => handler.remove();
  }, [busy, confirm, mode, onBack]));

  async function open(id: string) {
    const current = ++generation.current;
    setLoading(true); setError(null); setSuccess(null); setPlayer(null);
    try { const value = await getPerson(team.id, id); if (current === generation.current) { setPlayer(value); setMode('detail'); } }
    catch (cause) { if (current === generation.current) setError(cause instanceof Error ? cause.message : 'Não foi possível abrir o jogador.'); }
    finally { if (current === generation.current) setLoading(false); }
  }
  function denied() { setPlayer(null); setMode('list'); setConfirm(false); void reload(); }
  async function toggle() {
    if (!player || mutation.current) return;
    mutation.current = true; setBusy(true); setError(null);
    try {
      const updated = await changeStatus(team.id, player.membership_id, player.status === 'inactive');
      setPlayer(updated); setConfirm(false); setSuccess(updated.status === 'active' ? 'Jogador reativado.' : 'Jogador inativado. Histórico preservado.');
      await reload();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Não foi possível alterar o status.');
      if (cause instanceof ApiError && (cause.status === 403 || cause.status === 404)) denied();
    } finally { mutation.current = false; setBusy(false); }
  }
  const full = page ? page.active_count >= page.active_limit : false;
  return <View style={styles.stack}>
    <Text accessibilityRole="header" style={styles.heading}>Elenco</Text>
    {loading ? <LoadingState /> : <>
      <FormError message={error} />
      {success && <Text accessibilityLiveRegion="polite" style={styles.success}>{success}</Text>}
      {!page ? <Button label="Tentar novamente" onPress={() => void reload()} /> : <>
        <Text style={styles.note}>{page.active_count} de {page.active_limit} jogadores ativos · {page.inactive_count} inativos</Text>
        {full && <Text accessibilityRole="alert" style={styles.note}>Seu time atingiu o limite de {page.active_limit} jogadores ativos do plano {page.plan === 'free' ? 'Free' : 'Pro'}. Inative um jogador para liberar uma vaga.</Text>}
        {(mode === 'add' || mode === 'edit') && page.can_manage ? <PlayerForm teamId={team.id}
          player={mode === 'edit' ? player ?? undefined : undefined} onCancel={() => setMode('list')} onDenied={denied}
          onSaved={person => { setPlayer(person); setMode('detail'); setSuccess(mode === 'add' ? 'Jogador adicionado.' : 'Jogador atualizado.'); void reload(); }} /> :
          mode === 'detail' && player ? <>
            <Card><PersonSummary player={player} />
              {player.nickname && <Text style={styles.note}>Apelido: {player.nickname}</Text>}
              {player.phone && <Text style={styles.note}>Telefone: {player.phone}</Text>}
              {player.email && <Text style={styles.note}>E-mail: {player.email}</Text>}
            </Card>
            {page.can_manage && <>
              <Button label="Editar jogador" disabled={busy} onPress={() => { setError(null); setSuccess(null); setMode('edit'); }} />
              {player.is_president ? <Text style={styles.note}>Transfira a presidência antes de inativar este jogador.</Text> : confirm ? <Card><View style={styles.stack}>
                <Text accessibilityRole="header" style={styles.label}>Inativar {player.name}?</Text>
                <Text style={styles.note}>Ele sairá do elenco ativo, mas seu histórico será preservado.</Text>
                <Button label={busy ? 'Salvando…' : 'Inativar'} disabled={busy} onPress={() => void toggle()} />
                <TextAction label="Cancelar" disabled={busy} onPress={() => setConfirm(false)} />
              </View></Card> : <Button label={busy ? 'Salvando…' : player.status === 'active' ? 'Inativar jogador' : 'Reativar jogador'}
                disabled={busy || (player.status === 'inactive' && full)} onPress={() => { setSuccess(null); if (player.status === 'active') setConfirm(true); else void toggle(); }} />}
            </>}
            <TextAction label="Voltar ao elenco" disabled={busy} onPress={() => { setMode('list'); setPlayer(null); setConfirm(false); setError(null); setSuccess(null); }} />
          </> : <>
            <View style={styles.row}>{(['active', 'inactive', 'all'] as RosterFilter[]).map((value, index) => <Pressable key={value}
              accessibilityRole="button" accessibilityLabel={['Ativos', 'Inativos', 'Todos'][index]} aria-pressed={filter === value}
              accessibilityState={{ selected: filter === value }} style={[styles.filter, filter === value && styles.selected]}
              onPress={() => { setFilter(value); setSuccess(null); setError(null); }}>
              <Text style={styles.label}>{['Ativos', 'Inativos', 'Todos'][index]}</Text>
            </Pressable>)}</View>
            {page.can_manage && <Button label="Adicionar jogador" disabled={full} onPress={() => { setPlayer(null); setSuccess(null); setMode('add'); }} />}
            {!page.items.length && <EmptyState title="Nenhum jogador neste filtro" description="Os jogadores deste time aparecerão aqui." icon="people-outline" />}
            {page.items.map(item => <Pressable key={item.membership_id} accessibilityRole="button" accessibilityLabel={`Ver jogador ${item.name}`} onPress={() => void open(item.membership_id)}>
              <Card><PersonSummary player={item} /></Card>
            </Pressable>)}
          </>}
      </>}
    </>}
    <TextAction label="Voltar ao time" disabled={busy} onPress={onBack} />
  </View>;
}

function PersonSummary({ player }: { player: RosterPerson }) {
  return <View style={styles.stack}>
    <View style={styles.row}>
      <Avatar name={player.name} photoUrl={player.photo_url} />
      <Text style={styles.label}>{player.name}</Text>
    </View>
    <View style={styles.row}><Badge label={player.status === 'active' ? 'Ativo' : 'Inativo'} />{player.is_president && <Badge label="Presidente" />}</View>
    <Text style={styles.note}>{player.account_linked ? 'Conta vinculada' : 'Ainda não possui conta'}</Text>
  </View>;
}
