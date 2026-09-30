import { Fragment, useCallback, useRef, useState } from 'react';
import { Text, View } from 'react-native';
import { useFocusEffect } from '@react-navigation/native';
import type { BottomTabScreenProps } from '@react-navigation/bottom-tabs';
import Ionicons from '@expo/vector-icons/Ionicons';
import { AuthLayout, FormError } from '../components/AuthLayout';
import { Badge, Button, EmptyState, ListItem, LoadingState, SectionHeader } from '../components/ui';
import { ds, type IconName } from '../components/design';
import { useTeams } from '../teams/TeamContext';
import { useNotifications } from '../notifications/NotificationContext';
import * as api from '../notifications/api';
import type { TabParams } from '../navigation';
import { theme } from '../theme';

function day(value: string) {
  const date = new Date(value), today = new Date(), yesterday = new Date();
  yesterday.setDate(today.getDate() - 1);
  return date.toDateString() === today.toDateString() ? 'Hoje' : date.toDateString() === yesterday.toDateString() ? 'Ontem' : date.toLocaleDateString('pt-BR');
}
function relative(value: string) {
  const minutes = Math.max(0, Math.floor((Date.now() - Date.parse(value)) / 60000));
  return minutes < 1 ? 'Agora' : minutes < 60 ? `${minutes} min` : minutes < 1440 ? `${Math.floor(minutes / 60)}h` : day(value);
}
function icon(type: string): IconName {
  return type.startsWith('FINANCE') ? 'wallet-outline' : type.startsWith('TEAM') ? 'people-outline' : type === 'ATTENDANCE_REMINDER' ? 'calendar-outline'
    : type.startsWith('CHALLENGE') || type.startsWith('FIXTURE') ? 'shield-half-outline' : 'football-outline';
}
export function NotificationsScreen({ navigation }: BottomTabScreenProps<TabParams, 'Notificações'>) {
  const { select } = useTeams();
  const { count, refresh } = useNotifications();
  const [page, setPage] = useState<api.Page | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const generation = useRef(0), sending = useRef(false);
  const load = useCallback(async (cursor?: string) => {
    const current = ++generation.current;
    setLoading(true); setError(null);
    try {
      const result = await api.list(cursor);
      if (current === generation.current) setPage(previous => ({ ...result, items: cursor && previous ? [...previous.items, ...result.items] : result.items }));
      await refresh();
    } catch (cause) { if (current === generation.current) setError(cause instanceof Error ? cause.message : 'Não foi possível carregar as notificações.'); }
    finally { if (current === generation.current) setLoading(false); }
  }, [refresh]);
  useFocusEffect(useCallback(() => { void load(); return () => { generation.current++; }; }, [load]));
  async function open(item: api.Notification) {
    if (sending.current) return;
    sending.current = true; setBusy(true); setError(null);
    const current = generation.current;
    try {
      const updated = await api.read(item.id);
      if (current !== generation.current) return;
      setPage(previous => previous && ({ ...previous, items: previous.items.map(row => row.id === updated.id ? updated : row) }));
      await refresh();
      if (current !== generation.current) return;
      if (!updated.available) throw new Error(updated.message);
      if (!updated.action || !updated.team_id) return;
      const team = await select(updated.team_id);
      if (current !== generation.current) return;
      if (!team) throw new Error('Não foi possível acessar este time. Atualize seus times e tente novamente.');
      switch (updated.action) {
        case 'OPEN_TEAM': navigation.navigate('Início'); break;
        case 'OPEN_JOIN_REQUESTS': navigation.navigate('Elenco', { teamId: team.id, view: 'requests' }); break;
        case 'OPEN_EVENT': if (updated.entity_id) navigation.navigate('Jogos', { teamId: team.id, eventId: updated.entity_id }); break;
        case 'OPEN_FINANCE_CHARGE': if (updated.entity_id) navigation.navigate('Financeiro', { teamId: team.id, duesId: updated.entity_id }); break;
        // Received/cancelled reach the challenged team; accepted/rejected reach the sender.
        case 'OPEN_CHALLENGE': navigation.navigate('Adversários', { teamId: team.id, view: ['CHALLENGE_RECEIVED', 'CHALLENGE_CANCELLED'].includes(updated.type) ? 'received' : 'sent' }); break;
        case 'OPEN_FIXTURE': if (updated.entity_id) navigation.navigate('Adversários', { teamId: team.id, fixtureId: updated.entity_id }); break;
      }
    } catch (cause) { if (current === generation.current) setError(cause instanceof Error ? cause.message : 'Não foi possível abrir a notificação.'); }
    finally { sending.current = false; setBusy(false); }
  }
  async function all() {
    if (sending.current) return;
    sending.current = true; setBusy(true); setError(null);
    try { await api.readAll(); await load(); }
    catch (cause) { setError(cause instanceof Error ? cause.message : 'Não foi possível marcar as notificações.'); }
    finally { sending.current = false; setBusy(false); }
  }
  return <AuthLayout title="Notificações" description="Novidades dos seus times.">
    <FormError message={error} />
    {!!count && <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: theme.space.md, alignItems: 'center', justifyContent: 'space-between' }}><Badge label={`${count} não lida${count === 1 ? '' : 's'}`} /><Button variant="secondary" label="Marcar todas como lidas" disabled={busy || loading} onPress={() => void all()} /></View>}
    {loading && !page ? <LoadingState /> : page && !page.items.length ? <EmptyState title="Você está em dia." description="Quando houver novidades dos seus times, elas aparecerão aqui." icon="notifications-outline" /> : page?.items.map((item, index) => <Fragment key={item.id}>
      {(index === 0 || day(page.items[index - 1]!.created_at) !== day(item.created_at)) && <SectionHeader title={day(item.created_at)} />}
      <ListItem title={item.title} subtitle={item.message} disabled={busy || loading} onPress={() => void open(item)} accessibilityLabel={`${item.title}${item.read_at ? '' : ', não lida'}. ${item.message}`}
        leading={<Ionicons accessible={false} name={icon(item.type)} size={theme.icon.medium} color={item.read_at ? theme.colors.muted : theme.colors.green} />}
        trailing={<View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: theme.space.sm, alignItems: 'center' }}>{item.team_name && <Text style={ds.note}>{item.team_name}</Text>}<Text style={ds.note}>{relative(item.created_at)}</Text>{!item.read_at && <Badge label="Não lida" />}</View>} />
    </Fragment>)}
    {error && <Button label="Tentar novamente" disabled={loading || busy} onPress={() => void load()} />}
    {page?.next_cursor && <Button variant="secondary" label={loading ? 'Carregando…' : 'Carregar mais'} disabled={loading || busy} onPress={() => void load(page.next_cursor!)} />}
  </AuthLayout>;
}
