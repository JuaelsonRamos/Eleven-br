import { useCallback, useEffect, useState } from 'react';
import Ionicons from '@expo/vector-icons/Ionicons';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import type { BottomTabNavigationProp } from '@react-navigation/bottom-tabs';
import { Badge, Button, EmptyState, IconButton, LoadingState, SectionHeader, TeamBadge } from '../components/ui';
import { FormError, TextAction } from '../components/AuthLayout';
import { listEvents, eventWhen, type SportEvent } from '../events/api';
import type { TabParams } from '../navigation';
import { theme } from '../theme';
import type { Team } from './api';
import { useTeams } from './TeamContext';
import { TeamPublicId } from './TeamPublicId';
import { LocationEditor } from './LocationEditor';

const shortcutPalette = {
  green: { icon: theme.colors.green, background: '#DDF2E6' },
  gold: { icon: '#A87500', background: '#FFF0BF' },
  teal: { icon: '#087F8C', background: '#DDF4F3' },
  blue: { icon: theme.colors.blue, background: '#DFEBFA' },
  orange: { icon: '#B85C16', background: '#FFE9D5' },
};

export function TeamDashboard({ team, navigation }: { team: Team; navigation: BottomTabNavigationProp<TabParams> }) {
  return <View style={s.stack}>
    <Pressable accessibilityRole="button" accessibilityLabel={`Perfil do time ${team.name}`} onPress={() => navigation.navigate('Times', { view: 'detail' })}
      style={({ pressed }) => [s.summary, pressed && s.pressed]}>
      <TeamBadge name={team.name} crestUrl={team.crest_url} size={56} />
      <View style={s.grow}><Text style={s.teamName}>{team.name}</Text><Text style={s.note}>{team.active_player_count} jogadores ativos</Text>
        <View style={s.row}><Badge label={team.plan === 'free' ? 'Free' : 'Pro'} /></View>
      </View>
      <Ionicons name="chevron-forward" size={22} color={theme.colors.muted} />
    </Pressable>
    <View style={s.grid}>
      <HomeShortcutCard label="Elenco" icon="people-outline" tone="green" onPress={() => navigation.navigate('Elenco')} />
      <HomeShortcutCard label="Calendário" icon="calendar-outline" tone="gold" onPress={() => navigation.navigate('Jogos')} />
      <HomeShortcutCard label="Escalação" icon="football-outline" tone="green" onPress={() => navigation.navigate('Escalação')} />
      <HomeShortcutCard label="Financeiro" icon="wallet-outline" tone="teal" onPress={() => navigation.navigate('Financeiro')} />
      <HomeShortcutCard label="Estatísticas" icon="stats-chart-outline" tone="blue" onPress={() => navigation.navigate('Estatísticas')} />
      <HomeShortcutCard label="Adversários" icon="shield-outline" tone="gold" onPress={() => navigation.navigate('Adversários')} />
    </View>
    <NextEvent team={team} onAll={() => navigation.navigate('Jogos')} onOpen={event => navigation.navigate('Jogos', { teamId: team.id, eventId: event.id })} />
    {team.my_role === 'president' && !team.location_confirmed && <LocationEditor team={team} />}
    <TeamPublicId code={team.code} />
    <TextAction label="Trocar time" onPress={() => navigation.navigate('Times', { view: 'list' })} />
  </View>;
}

function HomeShortcutCard({ label, icon, tone, onPress, fullWidth = false }: {
  label: string; icon: keyof typeof Ionicons.glyphMap; tone: keyof typeof shortcutPalette; onPress: () => void; fullWidth?: boolean;
}) {
  const palette = shortcutPalette[tone];
  return <Pressable accessibilityRole="button" accessibilityLabel={label} onPress={onPress}
    style={({ pressed }) => [s.shortcut, { borderColor: palette.background }, fullWidth && s.fullWidth, pressed && s.pressed]}>
    <View style={[s.shortcutIcon, { backgroundColor: palette.background }]}>
      <Ionicons name={icon} size={30} color={palette.icon} />
    </View>
    <Text style={s.shortcutTitle}>{label}</Text>
  </Pressable>;
}

function NextEvent({ team, onOpen, onAll }: { team: Team; onOpen: (event: SportEvent) => void; onAll: () => void }) {
  const teamId = team.id;
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
      const next = page.items.filter(item => item.status === 'open' && item.kind === 'JOGO' && (!item.fixture || item.fixture.status === 'SCHEDULED') && new Date(`${item.date}T${item.time}`).getTime() >= now)
        .sort((a, b) => `${a.date}T${a.time}`.localeCompare(`${b.date}T${b.time}`))[0] ?? null;
      if (active) setEvent(next);
    }).catch(cause => { if (active) setError(cause instanceof Error ? cause.message : 'Não foi possível consultar a agenda.'); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [teamId, retry]);
  const opponent = event?.fixture?.opponent;
  const opponentName = opponent?.name || event?.opponent || 'Adversário a definir';
  return <View style={s.stack}><SectionHeader title="Próximo jogo" action={<IconButton label="Atualizar próximo jogo" icon="refresh-outline" onPress={reload} disabled={loading} />} />
    <View style={s.matchCard}>{loading ? <LoadingState label="Consultando a agenda…" /> : error ? <><FormError message={error} /><TextAction label="Tentar novamente" onPress={reload} /></> : event ? <>
      <Text style={s.date}>{eventWhen(event)}</Text>
      <View style={s.match}>
        <View style={s.side}><TeamBadge name={team.name} crestUrl={team.crest_url} size={52} /><Text style={s.matchName}>{team.name}</Text></View>
        <Text style={s.versus}>X</Text>
        <View style={s.side}><TeamBadge name={opponentName} crestUrl={opponent?.crest_url} size={52} /><Text style={s.matchName}>{opponentName}</Text></View>
      </View>
      <Text style={s.location}>{event.location} · {options.modalities.find(item => item.value === event.modality)?.label ?? event.modality}</Text>
      <Button label="Ver jogo" onPress={() => onOpen(event)} />
    </> : <EmptyState title="Nenhum jogo agendado." description="Os próximos jogos do time aparecerão aqui." icon="calendar-outline" />}
      <TextAction label="Ver todos" onPress={onAll} />
    </View>
  </View>;
}
const s = StyleSheet.create({
  stack: { gap: theme.space.xl },
  row: { flexDirection: 'row', flexWrap: 'wrap', gap: theme.space.sm },
  summary: { flexDirection: 'row', alignItems: 'center', gap: theme.space.md, paddingHorizontal: theme.space.lg, paddingVertical: 20, backgroundColor: theme.colors.surface, borderRadius: theme.radii.lg, borderWidth: 1, borderColor: theme.colors.surfaceMuted, shadowColor: theme.colors.graphite, shadowOpacity: 0.05, shadowRadius: 12, shadowOffset: { width: 0, height: 4 }, elevation: 2 },
  grow: { flex: 1, minWidth: 0, gap: 6 },
  teamName: { color: theme.colors.graphite, fontFamily: theme.fontFamily, fontSize: theme.type.heading, lineHeight: 26, fontWeight: '800', flexShrink: 1 },
  note: { fontFamily: theme.fontFamily, fontSize: theme.type.small, color: theme.colors.muted },
  grid: { flexDirection: 'row', flexWrap: 'wrap', gap: theme.space.md },
  shortcut: { flexBasis: '45%', flexGrow: 1, minWidth: 0, minHeight: 128, padding: theme.space.lg, gap: 10, alignItems: 'center', justifyContent: 'center', backgroundColor: theme.colors.surface, borderRadius: 20, borderWidth: 1, shadowColor: theme.colors.graphite, shadowOpacity: 0.04, shadowRadius: 8, shadowOffset: { width: 0, height: 3 }, elevation: 1 },
  fullWidth: { flexBasis: '100%' },
  shortcutIcon: { width: 52, height: 52, borderRadius: theme.radii.md, alignItems: 'center', justifyContent: 'center' },
  shortcutTitle: { color: theme.colors.graphite, fontFamily: theme.fontFamily, fontSize: 15, lineHeight: 21, fontWeight: '700', textAlign: 'center', flexShrink: 1, alignSelf: 'stretch' },
  pressed: { opacity: 0.65 },
  matchCard: { padding: theme.space.lg, gap: theme.space.lg, backgroundColor: theme.colors.surface, borderRadius: theme.radii.lg, borderWidth: 1, borderColor: theme.colors.surfaceMuted },
  date: { color: theme.colors.green, backgroundColor: theme.colors.lightGreen, borderRadius: theme.radii.sm, padding: theme.space.sm, fontFamily: theme.fontFamily, fontSize: theme.type.small, lineHeight: 20, fontWeight: '700', textAlign: 'center' },
  match: { flexDirection: 'row', alignItems: 'flex-start', gap: theme.space.sm, paddingVertical: theme.space.sm },
  side: { flex: 1, minWidth: 0, alignItems: 'center', gap: theme.space.md },
  matchName: { color: theme.colors.graphite, fontFamily: theme.fontFamily, fontSize: theme.type.small, lineHeight: 20, fontWeight: '700', textAlign: 'center', alignSelf: 'stretch' },
  versus: { color: theme.colors.muted, fontFamily: theme.fontFamily, fontSize: 18, lineHeight: 52, fontWeight: '700' },
  location: { color: theme.colors.muted, fontFamily: theme.fontFamily, fontSize: theme.type.small, lineHeight: 20, textAlign: 'center' },
});
