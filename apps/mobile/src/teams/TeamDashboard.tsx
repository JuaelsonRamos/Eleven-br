import { useCallback, useEffect, useState } from 'react';
import { StyleSheet, Text, View } from 'react-native';
import type { BottomTabNavigationProp } from '@react-navigation/bottom-tabs';
import { Badge, Button, Card, EmptyState, IconButton, LoadingState, QuickAction, SectionHeader, TeamBadge } from '../components/ui';
import { FormError, TextAction } from '../components/AuthLayout';
import { listEvents, eventWhen, type SportEvent } from '../events/api';
import type { TabParams } from '../navigation';
import { theme } from '../theme';
import { modalityLabels, roles, type Team } from './api';
import { useTeams } from './TeamContext';
import { TeamPublicId } from './TeamPublicId';
import { LocationEditor } from './LocationEditor';

export function TeamDashboard({ team, navigation }: { team: Team; navigation: BottomTabNavigationProp<TabParams> }) {
  const { options } = useTeams();
  return <View style={s.stack}>
    <View style={s.hero}>
      <View style={s.heroTop}><Text style={s.eyebrow}>SEU TIME. SEU JOGO.</Text><IconButton label="Trocar time" icon="swap-horizontal-outline" onPress={() => navigation.navigate('Times', { view: 'list' })} /></View>
      <View style={s.identity}><TeamBadge name={team.name} crestUrl={team.crest_url} size={64} /><View style={s.grow}><Text accessibilityRole="header" style={s.teamName}>{team.name}</Text><Text style={s.heroNote}>{team.city} · {team.state}</Text></View></View>
      <Text style={s.heroNote}>{modalityLabels(team.modalities, options.modalities)}</Text>
      <View style={s.row}><Badge label={roles[team.my_role]} /><Badge label={team.plan === 'free' ? 'Free' : 'Pro'} /><Text style={s.heroNote}>{team.active_player_count} jogadores ativos</Text></View>
      <Button variant="secondary" label="Perfil do time" onPress={() => navigation.navigate('Times', { view: 'detail' })} />
    </View>
    {team.my_role === 'president' && !team.location_confirmed && <LocationEditor team={team} />}
    <TeamPublicId code={team.code} />
    <SectionHeader title="Ações rápidas" subtitle="Tudo para o próximo jogo." />
    <View style={s.row}>
      <QuickAction label="Jogos" description="Agenda e presença" icon="football-outline" onPress={() => navigation.navigate('Jogos')} />
      <QuickAction label="Elenco" description="Quem joga com você" icon="people-outline" onPress={() => navigation.navigate('Elenco')} />
      <QuickAction label="Estatísticas" description="Números do time" icon="stats-chart-outline" onPress={() => navigation.navigate('Estatísticas')} />
      <QuickAction label="Financeiro" description="Mensalidades e caixa" icon="wallet-outline" onPress={() => navigation.navigate('Financeiro')} />
      <QuickAction label="Escalação" description="Seu time em campo · Pro" icon="football-outline" onPress={() => navigation.navigate('Escalação')} />
      <QuickAction label="Mais" description="Sua conta e seus times" icon="grid-outline" onPress={() => navigation.navigate('Mais')} />
    </View>
    <NextEvent teamId={team.id} onOpen={event => navigation.navigate('Jogos', { teamId: team.id, eventId: event.id })} />
  </View>;
}

function NextEvent({ teamId, onOpen }: { teamId: string; onOpen: (event: SportEvent) => void }) {
  const [event, setEvent] = useState<SportEvent | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [retry, setRetry] = useState(0);
  const { options } = useTeams();
  const reload = useCallback(() => setRetry(value => value + 1), []);
  useEffect(() => {
    let active = true; setLoading(true); setError(null); setEvent(null);
    void listEvents(teamId).then(page => {
      const now = Date.now();
      const next = page.items.filter(item => item.status === 'open' && new Date(`${item.date}T${item.time}`).getTime() >= now)
        .sort((a, b) => `${a.date}T${a.time}`.localeCompare(`${b.date}T${b.time}`))[0] ?? null;
      if (active) setEvent(next);
    }).catch(cause => { if (active) setError(cause instanceof Error ? cause.message : 'Não foi possível consultar a agenda.'); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [teamId, retry]);
  return <View style={s.stack}><SectionHeader title="Próximo evento" action={<IconButton label="Atualizar próximo evento" icon="refresh-outline" onPress={reload} disabled={loading} />} />
    <Card>{loading ? <LoadingState label="Consultando a agenda…" /> : error ? <><FormError message={error} /><TextAction label="Tentar novamente" onPress={reload} /></> : event ? <>
      <Badge label={event.kind === 'PELADA' ? 'PELADA' : 'JOGO'} /><Text style={s.heading}>{event.title}</Text>
      <Text style={s.text}>{eventWhen(event)}</Text><Text style={s.note}>{event.location} · {options.modalities.find(item => item.value === event.modality)?.label ?? event.modality}</Text>
      <View style={s.row}><Badge label={`${event.going} confirmados`} /><Badge label={`${event.pending} pendentes`} tone="warning" /><Badge label={`${event.not_going} não vão`} tone="neutral" /></View>
      <Button label="Ver evento" onPress={() => onOpen(event)} />
    </> : <EmptyState title="Agenda livre por enquanto" description="Quando houver um próximo evento, ele aparecerá aqui." icon="calendar-outline" />}</Card>
  </View>;
}
const s = StyleSheet.create({
  stack: { gap: theme.space.lg }, row: { flexDirection: 'row', flexWrap: 'wrap', gap: theme.space.md, alignItems: 'center' },
  hero: { backgroundColor: theme.colors.primaryDark, borderRadius: theme.radii.lg, padding: theme.space.xl, gap: theme.space.lg },
  heroTop: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: theme.space.sm },
  eyebrow: { color: theme.colors.onDarkMuted, fontFamily: theme.fontFamily, fontSize: theme.type.caption, letterSpacing: 1, fontWeight: '700', flex: 1 },
  identity: { flexDirection: 'row', alignItems: 'center', gap: theme.space.lg }, grow: { flex: 1, minWidth: 0, gap: theme.space.sm },
  teamName: { color: theme.colors.white, fontFamily: theme.fontFamily, fontSize: theme.type.title, fontWeight: '800' },
  heroNote: { color: theme.colors.onDarkMuted, fontFamily: theme.fontFamily, fontSize: theme.type.small, lineHeight: 21 },
  heading: { fontFamily: theme.fontFamily, fontSize: theme.type.heading, fontWeight: '700', color: theme.colors.graphite },
  text: { fontFamily: theme.fontFamily, fontSize: theme.type.body, color: theme.colors.graphite }, note: { fontFamily: theme.fontFamily, fontSize: theme.type.small, color: theme.colors.muted },
});
