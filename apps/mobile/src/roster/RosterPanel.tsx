import { useCallback, useEffect, useRef, useState } from 'react';
import { BackHandler, Text, View } from 'react-native';
import { useFocusEffect } from '@react-navigation/native';
import { Avatar, Badge, Button, Card, EmptyState, LoadingState, FilterChip, ListItem } from '../components/ui';
import { FormError, TextAction } from '../components/AuthLayout';
import { ApiError } from '../auth/api';
import type { Team } from '../teams/api';
import { changeStatus, getPerson, listRoster, type RosterFilter, type RosterPage, type RosterPerson } from './api';
import { PlayerForm } from './PlayerForm';
import { rosterStyles as styles } from './styles';
import { JoinAdminPanel } from '../join/JoinAdminPanel';
import { InviteCode } from '../join/InviteCode';
import * as statistics from '../statistics/api';
import { StatisticAdjustmentForm } from './StatisticAdjustmentForm';

export function RosterPanel({ team, onBack, initialRequests, onInitialConsumed }: { team: Team; onBack: () => void; initialRequests?: boolean; onInitialConsumed?: () => void }) {
  const initial = useRef(initialRequests), consumed = useRef(onInitialConsumed);
  const [filter, setFilter] = useState<RosterFilter>('active');
  const [page, setPage] = useState<RosterPage | null>(null);
  const [player, setPlayer] = useState<RosterPerson | null>(null);
  const [mode, setMode] = useState<'list' | 'detail' | 'add' | 'edit' | 'requests' | 'invite' | 'statistics'>('list');
  const [stats, setStats] = useState<statistics.Page | null>(null);
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
    try { const [value, totals] = await Promise.all([listRoster(team.id, filter), statistics.overview(team.id, 'all', '')]); if (current === generation.current) { setPage(value); setStats(totals); if (initial.current) { initial.current = false; if (value.can_manage) setMode('requests'); else setError('Você não possui permissão para tratar solicitações.'); consumed.current?.(); } } }
    catch (cause) { if (current === generation.current) { setPage(null); setPlayer(null); setMode('list'); setError(cause instanceof Error ? cause.message : 'Não foi possível carregar o elenco.'); } }
    finally { if (current === generation.current) setLoading(false); }
  }, [filter, team.id]);
  useEffect(() => { const counter = generation; void reload(); return () => { counter.current++; }; }, [reload]);
  useFocusEffect(useCallback(() => {
    if (mode === 'requests') return;
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
  const numbers = (id: string) => { const value = stats?.players.find(item => item.kind === 'member' && item.id === id)?.totals; return `${value?.goals ?? 0} gols · ${value?.yellow_cards ?? 0} amarelos · ${value?.red_cards ?? 0} vermelhos`; };
  return <View style={styles.stack}>
    <Text accessibilityRole="header" style={styles.heading}>Elenco</Text>
    {loading ? <LoadingState /> : <>
      <FormError message={error} />
      {success && <Text accessibilityLiveRegion="polite" style={styles.success}>{success}</Text>}
      {!page ? <Button label="Tentar novamente" onPress={() => void reload()} /> : <>
        <Text style={styles.note}>{page.active_count} de {page.active_limit} jogadores ativos · {page.inactive_count} inativos</Text>
        {full && <Text accessibilityRole="alert" style={styles.note}>Seu time atingiu o limite de {page.active_limit} jogadores ativos do plano {page.plan === 'free' ? 'Free' : 'Pro'}. Inative um jogador para liberar uma vaga.</Text>}
        {page.can_manage && <>
          <Button label="Adicionar jogador" disabled={full || busy || mode === 'add'} onPress={() => { setPlayer(null); setSuccess(null); setConfirm(false); setMode('add'); }} />
          <Button variant="secondary" label="Convidar jogadores" disabled={busy} onPress={() => setMode('invite')} />
          <Button variant="secondary" label="Solicitações de entrada" disabled={busy} onPress={() => { setSuccess(null); setMode('requests'); }} />
        </>}
        {mode === 'requests' && page.can_manage ? <JoinAdminPanel teamId={team.id} onBack={() => { setMode('list'); void reload(); }} /> : mode === 'invite' && page.can_manage ? <><InviteCode code={team.code} name={team.name} /><TextAction label="Voltar ao elenco" onPress={() => setMode('list')} /></> : mode === 'statistics' && player && stats?.can_manage_statistics ? <StatisticAdjustmentForm teamId={team.id} memberId={player.membership_id} name={player.name} onCancel={() => setMode('detail')} onSaved={() => { setMode('detail'); setSuccess('Estatísticas atualizadas. Histórico das partidas preservado.'); void reload(); }} /> : <>
        {(mode === 'add' || mode === 'edit') && page.can_manage ? <PlayerForm teamId={team.id}
          player={mode === 'edit' ? player ?? undefined : undefined} onCancel={() => setMode('list')} onDenied={denied}
          onSaved={person => { setPlayer(person); setMode('detail'); setSuccess(mode === 'add' ? 'Jogador adicionado.' : 'Jogador atualizado.'); void reload(); }} /> :
          mode === 'detail' && player ? <>
            <Card><PersonSummary player={player} />
              <Text style={styles.note}>{numbers(player.membership_id)}</Text>
              {player.nickname && <Text style={styles.note}>Apelido: {player.nickname}</Text>}
              {player.phone && <Text style={styles.note}>Telefone: {player.phone}</Text>}
              {player.email && <Text style={styles.note}>E-mail: {player.email}</Text>}
            </Card>
            {stats?.can_manage_statistics && <Button label="Editar estatísticas" onPress={() => { setSuccess(null); setMode('statistics'); }} />}
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
            <View style={styles.row}>{(['active', 'inactive', 'all'] as RosterFilter[]).map((value, index) => <FilterChip key={value} label={['Ativos', 'Inativos', 'Todos'][index]!} selected={filter === value}
              onPress={() => { setFilter(value); setSuccess(null); setError(null); }} />)}</View>
            {!page.items.length && <EmptyState title="Nenhum jogador neste filtro" description="Os jogadores deste time aparecerão aqui." icon="people-outline" />}
            {page.items.map(item => <ListItem key={item.membership_id} title={item.name} subtitle={`${item.account_linked ? 'Conta vinculada' : 'Ainda não possui conta'}\n${numbers(item.membership_id)}`}
              leading={<Avatar name={item.name} photoUrl={item.photo_url} />} accessibilityLabel={`Ver jogador ${item.name}`} onPress={() => void open(item.membership_id)}
              trailing={<><Badge label={item.status === 'active' ? 'Ativo' : 'Inativo'} tone={item.status === 'active' ? 'success' : 'neutral'} />{item.is_president && <Badge label="Presidente" tone="info" />}</>} />)}
          </>}</>}
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
