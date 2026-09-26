import { useCallback, useEffect, useRef, useState } from 'react';
import { BackHandler, Pressable, StyleSheet, Text, View } from 'react-native';
import { useFocusEffect } from '@react-navigation/native';
import { Avatar, Button, EmptyState, ErrorState, LoadingState } from '../components/ui';
import { TextAction } from '../components/AuthLayout';
import { useTeams } from '../teams/TeamContext';
import { theme } from '../theme';
import * as api from './api';

const tabs = ['Geral', 'Artilharia', 'Assistências', 'Cartões'] as const;
type Tab = typeof tabs[number];
const dateLabel = (date: string) => date.split('-').reverse().join('/');

function Totals({ value, individual = false }: { value: api.Totals; individual?: boolean }) {
  return <View style={s.totals}>{([
    [individual ? 'Partidas disputadas' : 'Partidas realizadas', value.matches], ['Gols identificados', value.goals], ['Assistências', value.assists],
    ['Cartões amarelos', value.yellow_cards], ['Cartões vermelhos', value.red_cards],
  ] as const).map(([label, count]) => <View key={label} style={s.total}><Text style={s.number}>{count}</Text><Text style={s.muted}>{label}</Text></View>)}</View>;
}

function Identity({ person }: { person: api.Person }) {
  return <View style={s.identity}><Avatar name={person.name} photoUrl={person.photo_url} size={40} /><View style={s.nameBlock}>
    <Text style={s.name}>{person.name}</Text>
    {person.kind === 'guest' && <Text style={s.muted}>Convidado · {person.event_date ? dateLabel(person.event_date) : ''}</Text>}
    {person.inactive && <Text style={s.muted}>Inativo</Text>}
  </View></View>;
}

function People({ title, people, metric, open }: { title: string; people: api.Person[]; metric?: Tab; open: (person: api.Person) => void }) {
  return <View style={s.stack}><Text accessibilityRole="header" style={s.heading}>{title}</Text>
    {!people.length && <Text style={s.muted}>Nenhum registro neste período.</Text>}
    {people.map(person => <Pressable key={`${person.kind}:${person.id}`} accessibilityRole="button" accessibilityLabel={`Ver estatísticas de ${person.name}`} onPress={() => open(person)} style={({ pressed }) => [s.person, pressed && s.pressed]}>
      {metric === 'Artilharia' || metric === 'Assistências' ? <Text style={s.position}>{metric === 'Artilharia' ? person.goals_position : person.assists_position}º</Text> : null}
      <Identity person={person} />
      <Text style={s.metric}>{metric === 'Artilharia' ? `${person.totals.goals} ${person.totals.goals === 1 ? 'gol' : 'gols'}` : metric === 'Assistências' ? `${person.totals.assists} assist.` : metric === 'Cartões' ? `${person.totals.yellow_cards} amar.\n${person.totals.red_cards} verm.` : `${person.totals.matches} ${person.totals.matches === 1 ? 'jogo' : 'jogos'}`}</Text>
    </Pressable>)}
  </View>;
}

export function StatisticsPanel({ teamId, onGames, onNavigate }: { teamId: string; onGames: () => void; onNavigate: () => void }) {
  const { options } = useTeams();
  const [period, setPeriod] = useState<api.Period>('all');
  const [modality, setModality] = useState('');
  const [tab, setTab] = useState<Tab>('Geral');
  const [page, setPage] = useState<api.Page | null>(null);
  const [person, setPerson] = useState<api.Person | null>(null);
  const [profile, setProfile] = useState<api.Profile | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [moreLoading, setMoreLoading] = useState(false);
  const [moreError, setMoreError] = useState(false);
  const [retry, setRetry] = useState(0);
  const revision = useRef(0);
  useEffect(() => {
    const current = ++revision.current;
    setLoading(true); setError(false); setMoreError(false); setMoreLoading(false);
    const load = async () => {
      try {
        if (person) {
          const result = await api.profile(teamId, person, period, modality);
          if (current === revision.current) setProfile(result);
        } else {
          const result = await api.overview(teamId, period, modality);
          if (current === revision.current) setPage(result);
        }
      } catch { if (current === revision.current) setError(true); }
      finally { if (current === revision.current) setLoading(false); }
    };
    void load();
    return () => { revision.current = current + 1; };
  }, [teamId, period, modality, person, retry]);
  const back = useCallback(() => { setPerson(null); setProfile(null); onNavigate(); }, [onNavigate]);
  useFocusEffect(useCallback(() => {
    if (!person) return;
    const subscription = BackHandler.addEventListener('hardwareBackPress', () => { back(); return true; });
    return () => subscription.remove();
  }, [person, back]));
  const open = (value: api.Person) => { setLoading(true); setProfile(null); setPerson(value); onNavigate(); };
  const more = async () => {
    if (!person || !profile || moreLoading) return;
    const current = revision.current;
    setMoreLoading(true); setMoreError(false);
    try {
      const next = await api.profile(teamId, person, period, modality, profile.history.length);
      if (current === revision.current) setProfile({ ...next, history: [...profile.history, ...next.history] });
    } catch { if (current === revision.current) setMoreError(true); }
    finally { if (current === revision.current) setMoreLoading(false); }
  };
  return <View style={s.stack}>
    {person && <TextAction label="Voltar para estatísticas" onPress={back} />}
    <Text accessibilityRole="header" style={s.title}>{person ? 'Perfil estatístico' : 'Estatísticas'}</Text>
    <Text style={s.muted}>Somente partidas finalizadas. Gols identificados podem diferir do placar oficial.</Text>
    <Text style={s.label}>Período</Text><View style={s.wrap}>{api.periods.map(item => <Choice key={item.value} label={item.label} selected={period === item.value} onPress={() => { setLoading(true); setPeriod(item.value); }} />)}</View>
    <Text style={s.label}>Modalidade</Text><View style={s.wrap}>
      <Choice label="Todas" selected={!modality} onPress={() => { if (modality) { setLoading(true); setModality(''); } }} />
      {(page?.modalities ?? []).map(value => <Choice key={value} label={options.modalities.find(m => m.value === value)?.label ?? value} selected={modality === value} onPress={() => { if (modality !== value) { setLoading(true); setModality(value); } }} />)}
    </View>
    {!person && <View style={s.wrap}>{tabs.map(value => <Choice key={value} label={value} selected={tab === value} onPress={() => setTab(value)} />)}</View>}
    {loading ? <LoadingState /> : error ? <ErrorState onRetry={() => setRetry(v => v + 1)} /> : person && profile ? <>
      <Identity person={profile.person} />
      {person.kind === 'guest' && <Text style={s.muted}>Convidado desta pelada. Seu histórico é restrito a esta ocorrência.</Text>}
      <Totals value={profile.person.totals} individual />
      <Text accessibilityRole="header" style={s.heading}>Médias por partida</Text>
      <Text style={s.body}>Gols: {profile.goals_per_match.toFixed(2).replace('.', ',')} · Assistências: {profile.assists_per_match.toFixed(2).replace('.', ',')}</Text>
      <Text accessibilityRole="header" style={s.heading}>Histórico recente</Text>
      {!profile.history.length && <Text style={s.muted}>Nenhuma partida finalizada neste período.</Text>}
      {profile.history.map(item => <View key={item.match_id} style={s.history}>
        <Text style={s.name}>{dateLabel(item.date)} · {item.title}</Text>
        <Text style={s.body}>Time {item.home_number} {item.home_score} × {item.away_score} Time {item.away_number}</Text>
        <Text style={s.muted}>{item.goals} gols · {item.assists} assistências</Text>
        <Text style={s.muted}>{item.yellow_cards} amarelos · {item.red_cards} vermelhos</Text>
      </View>)}
      {moreError && <Text style={s.error}>Não foi possível carregar mais partidas. Tente novamente.</Text>}
      {profile.has_more && <Button label={moreLoading ? 'Carregando…' : 'Carregar mais partidas'} disabled={moreLoading} onPress={() => void more()} />}
    </> : page ? <>
      {!page.summary.matches && <EmptyState title="Ainda não há estatísticas." description="Finalize partidas e registre gols, assistências e cartões para começar. Confira também os filtros selecionados."><Button label="Ir para Jogos" onPress={onGames} /></EmptyState>}
      {tab === 'Geral' ? <>
        {!!page.summary.matches && <><Totals value={page.summary} /><People title="Artilheiros" people={page.scorers.slice(0, 5)} metric="Artilharia" open={open} /><People title="Assistências" people={page.assistants.slice(0, 5)} metric="Assistências" open={open} /><People title="Disciplina" people={page.discipline} metric="Cartões" open={open} /></>}
        <People title="Jogadores e convidados" people={page.players} open={open} />
      </> : <People title={tab === 'Cartões' ? 'Disciplina' : tab} people={tab === 'Artilharia' ? page.scorers : tab === 'Assistências' ? page.assistants : page.discipline} metric={tab} open={open} />}
    </> : null}
  </View>;
}

function Choice({ label, selected, onPress }: { label: string; selected: boolean; onPress: () => void }) {
  return <Pressable accessibilityRole="button" accessibilityState={{ selected }} onPress={selected ? undefined : onPress} style={[s.choice, selected && s.selected]}><Text style={[s.choiceText, selected && s.selectedText]}>{label}</Text></Pressable>;
}

const s = StyleSheet.create({
  stack: { gap: 16 }, wrap: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  title: { fontFamily: theme.fontFamily, color: theme.colors.graphite, fontSize: 28, fontWeight: '800' },
  heading: { fontFamily: theme.fontFamily, color: theme.colors.graphite, fontSize: 20, fontWeight: '700' },
  body: { fontFamily: theme.fontFamily, color: theme.colors.graphite, fontSize: 15 },
  muted: { fontFamily: theme.fontFamily, color: theme.colors.muted, fontSize: 13, lineHeight: 19 },
  label: { fontFamily: theme.fontFamily, color: theme.colors.graphite, fontSize: 14, fontWeight: '600' },
  choice: { minHeight: 44, paddingHorizontal: 12, paddingVertical: 12, borderRadius: 12, borderWidth: 1, borderColor: theme.colors.border, backgroundColor: theme.colors.white, justifyContent: 'center' },
  selected: { backgroundColor: theme.colors.green, borderColor: theme.colors.green },
  choiceText: { fontFamily: theme.fontFamily, fontSize: 13, color: theme.colors.graphite }, selectedText: { color: theme.colors.white },
  totals: { flexDirection: 'row', flexWrap: 'wrap', gap: 12 },
  total: { flexGrow: 1, flexBasis: 115, padding: 12, backgroundColor: theme.colors.white, borderRadius: 12 },
  number: { fontFamily: theme.fontFamily, fontSize: 26, fontWeight: '800', color: theme.colors.green },
  person: { flexDirection: 'row', alignItems: 'center', gap: 8, paddingVertical: 12, borderBottomWidth: 1, borderColor: theme.colors.border, minHeight: 64 },
  identity: { flexDirection: 'row', alignItems: 'center', gap: 8, flex: 1, minWidth: 0 },
  nameBlock: { flex: 1, minWidth: 0 }, name: { fontFamily: theme.fontFamily, fontSize: 15, fontWeight: '600', color: theme.colors.graphite, flexShrink: 1 },
  position: { fontFamily: theme.fontFamily, color: theme.colors.green, fontWeight: '700', width: 26 },
  metric: { fontFamily: theme.fontFamily, color: theme.colors.graphite, fontSize: 13, fontWeight: '600', textAlign: 'right', width: 60 },
  pressed: { opacity: 0.65 }, history: { gap: 6, paddingVertical: 12, borderBottomWidth: 1, borderColor: theme.colors.border },
  error: { color: theme.colors.error, fontFamily: theme.fontFamily },
});
