import { useEffect, useRef, useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { Field, FormError, TextAction } from '../components/AuthLayout';
import { Badge, Button, Card, EmptyState, FilterChip, ListItem, LoadingState } from '../components/ui';
import { listRoster, type RosterPerson } from '../roster/api';
import { listEvents, type SportEvent } from '../events/api';
import { theme } from '../theme';
import * as api from './api';

const modalities: Record<string, string> = { campo: 'Campo', society: 'Society', futsal: 'Futsal' };
export function LineupsPanel({ teamId }: { teamId: string }) {
  const [page, setPage] = useState<api.Page | null>(null), [roster, setRoster] = useState<RosterPerson[]>([]), [events, setEvents] = useState<SportEvent[]>([]);
  const [draft, setDraft] = useState<api.Lineup | null>(null), [slot, setSlot] = useState<number | null>(null);
  const [busy, setBusy] = useState(false), [loading, setLoading] = useState(true), [plans, setPlans] = useState(false);
  const [error, setError] = useState<string | null>(null), [notice, setNotice] = useState<string | null>(null);
  const lock = useRef(false), alive = useRef(true);
  async function load() {
    setLoading(true); setError(null);
    try {
      const value = await api.list(teamId);
      const [people, agenda] = value.enabled ? await Promise.all([listRoster(teamId, 'all'), listEvents(teamId)]) : [null, null];
      if (alive.current) { setPage(value); setRoster(people?.items ?? []); setEvents(agenda?.items ?? []); }
    } catch (cause) { if (alive.current) setError(cause instanceof Error ? cause.message : 'Não foi possível carregar.'); }
    finally { if (alive.current) setLoading(false); }
  }
  const initialLoad = useRef(load);
  useEffect(() => { alive.current = true; void initialLoad.current(); return () => { alive.current = false; }; }, []);
  async function run(action: () => Promise<void>) {
    if (lock.current) return; lock.current = true; setBusy(true); setError(null); setNotice(null);
    try { await action(); } catch (cause) { if (alive.current) setError(cause instanceof Error ? cause.message : 'Não foi possível concluir.'); }
    finally { lock.current = false; if (alive.current) setBusy(false); }
  }
  function create() {
    if (!page) return;
    const modality = Object.keys(page.templates)[0]!;
    setDraft({ title: '', modality, formation: Object.keys(page.templates[modality]!)[0]!, event_id: null, version: 0, positions: [] }); setSlot(null); setNotice(null); setError(null);
  }
  function formation(modality: string, value: string) {
    if (!draft || !page || busy) return;
    const old = page.templates[draft.modality]?.[draft.formation]?.flat() ?? [];
    const next = page.templates[modality]![value]!.flat(), remaining = [...draft.positions], positions: api.Slot[] = [];
    next.forEach((position, index) => { const found = remaining.findIndex(item => old[item.slot] === position); if (found >= 0) { positions.push({ ...remaining[found]!, slot: index }); remaining.splice(found, 1); } });
    setNotice(remaining.length ? `${remaining.length} jogador(es) ficaram sem posição na nova formação. Selecione novamente onde devem jogar.` : null);
    setDraft({ ...draft, modality, formation: value, event_id: modality === draft.modality ? draft.event_id : null, positions }); setSlot(null);
  }
  const rows = draft ? page?.templates[draft.modality]?.[draft.formation] ?? [] : [];
  const labels = rows.flat(), selected = slot === null ? null : labels[slot];
  const editable = page?.can_manage && !busy;
  const rank = (person: RosterPerson) => person.primary_position === selected ? 0 : selected && person.positions.includes(selected) ? 1 : 2;
  const available = roster.filter(person => person.status === 'active' && !draft?.positions.some(item => item.membership_id === person.membership_id && item.slot !== slot)).sort((a, b) => rank(a) - rank(b) || a.name.localeCompare(b.name));
  function assign(id: string | null) { if (!draft || slot === null || !editable) return; setDraft({ ...draft, positions: [...draft.positions.filter(item => item.slot !== slot), ...(id ? [{ slot, membership_id: id }] : [])] }); setSlot(null); }
  return <View style={s.stack}>
    <Text accessibilityRole="header" style={s.heading}>Escalação</Text>
    <FormError message={error} />
    {notice && <Text accessibilityLiveRegion="polite" style={s.note}>{notice}</Text>}
    {loading ? <LoadingState /> : !page ? <Button label="Tentar novamente" onPress={() => void load()} /> : !page.enabled ? <Card>
      <Badge label="ELEVEN BR PRO" /><Text style={s.heading}>Escalação é um recurso ELEVEN BR PRO.</Text>
      <Text style={s.note}>Monte seu time no campo e salve suas formações.</Text>
      <Button label="Conhecer o Pro" onPress={() => setPlans(true)} />
      {plans && <Text style={s.note}>A contratação do Pro estará disponível em breve. Nenhuma cobrança foi realizada.</Text>}
    </Card> : !draft ? <>
      {page.can_manage && <Button label="Nova escalação" onPress={create} disabled={busy} />}
      {!page.items.length && <EmptyState title="Seu campo está livre" description="As escalações salvas do time aparecerão aqui." icon="football-outline" />}
      {page.items.map(item => <ListItem key={item.id} title={item.title} subtitle={`${modalities[item.modality]} · ${item.formation}`} onPress={() => void run(async () => { const value = await api.detail(teamId, item.id); if (alive.current) { setDraft(value); setSlot(null); } })} />)}
      {page.has_more && <Button label="Carregar mais escalações" disabled={busy} onPress={() => void run(async () => { const next = await api.list(teamId, page.items.length); if (alive.current) setPage({ ...page, items: [...page.items, ...next.items], has_more: next.has_more }); })} />}
    </> : <>
      {page.can_manage ? <Field label="Nome da escalação" value={draft.title} maxLength={80} editable={!busy} onChangeText={title => setDraft({ ...draft, title })} /> : <Text style={s.heading}>{draft.title}</Text>}
      <View style={s.row}>{Object.keys(page.templates).map(value => <FilterChip key={value} label={modalities[value] ?? value} selected={draft.modality === value} onPress={() => { if (editable && value !== draft.modality) formation(value, Object.keys(page.templates[value]!)[0]!); }} />)}</View>
      <View style={s.row}>{Object.keys(page.templates[draft.modality] ?? {}).map(value => <FilterChip key={value} label={value} selected={draft.formation === value} onPress={() => { if (editable) formation(draft.modality, value); }} />)}</View>
      <Text style={s.note}>{page.can_manage ? 'Toque numa posição para escolher um jogador.' : 'Escalação do time. Somente a gestão pode editar.'}</Text>
      <View style={[s.pitch, draft.modality === 'futsal' && s.court]} accessibilityLabel={`Campo de ${modalities[draft.modality]}`}>
        <View pointerEvents="none" style={s.half} /><View pointerEvents="none" style={s.circle} /><View pointerEvents="none" style={[s.area, { top: 0 }]} /><View pointerEvents="none" style={[s.area, { bottom: 0 }]} />
        {[...rows.map((row, rowIndex) => ({ row, offset: rows.slice(0, rowIndex).flat().length }))].reverse().map(({ row, offset }) => <View key={offset} style={s.pitchRow}>{row.map((position, index) => {
          const number = offset + index, id = draft.positions.find(item => item.slot === number)?.membership_id, person = roster.find(item => item.membership_id === id);
          const name = person?.nickname || person?.name || (id ? 'Indisponível' : 'Selecionar');
          return <Pressable key={number} disabled={!editable} accessibilityRole="button" accessibilityLabel={`Posição ${number + 1} ${position}: ${name}`} onPress={() => setSlot(number)} style={[s.slot, slot === number && s.selected]}><Text numberOfLines={2} style={s.name}>{name}</Text><Text style={s.position}>{position}</Text></Pressable>;
        })}</View>)}
      </View>
      {slot !== null && page.can_manage && <Card><Text accessibilityRole="header" style={s.heading}>Escolher jogador · {selected}</Text><Text style={s.note}>Posição principal primeiro, depois alternativas. Você pode improvisar.</Text>
        {available.map(person => <ListItem key={person.membership_id} title={person.name} subtitle={`${person.primary_position ?? 'Sem posição'}${rank(person) === 2 ? ' · Outra posição' : ''}`} onPress={() => assign(person.membership_id)} />)}
        {!available.length && <Text style={s.note}>Nenhum jogador ativo disponível.</Text>}
        <TextAction label="Deixar posição vazia" onPress={() => assign(null)} /><TextAction label="Fechar seleção" onPress={() => setSlot(null)} />
      </Card>}
      <Text style={s.heading}>Evento (opcional)</Text>
      {page.can_manage ? <View style={s.stack}><FilterChip label="Sem evento" selected={!draft.event_id} onPress={() => { if (editable) setDraft({ ...draft, event_id: null }); }} />
        {events.filter(event => event.status === 'open' && event.modality === draft.modality).map(event => <FilterChip key={event.id} label={`${event.title} · ${event.date}`} selected={draft.event_id === event.id} onPress={() => { if (editable) setDraft({ ...draft, event_id: event.id }); }} />)}
      </View> : <Text style={s.note}>{events.find(event => event.id === draft.event_id)?.title ?? (draft.event_id ? 'Evento vinculado' : 'Sem evento')}</Text>}
      {page.can_manage && <Button label={busy ? 'Salvando…' : 'Salvar escalação'} disabled={busy || !draft.title.trim()} onPress={() => void run(async () => { const value = await api.save(teamId, draft, page.command_id); if (alive.current) { setDraft(value); setSlot(null); setNotice('Escalação salva.'); setPage({ ...page, items: [{ id: value.id!, title: value.title, modality: value.modality, formation: value.formation }, ...page.items.filter(item => item.id !== value.id)] }); } })} />}
      <TextAction label="Voltar às escalações" disabled={busy} onPress={() => { setDraft(null); setSlot(null); setNotice(null); void load(); }} />
    </>}
  </View>;
}
const s = StyleSheet.create({
  stack: { gap: theme.space.lg }, row: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  heading: { fontFamily: theme.fontFamily, color: theme.colors.graphite, fontSize: theme.type.heading, fontWeight: '700' },
  note: { fontFamily: theme.fontFamily, color: theme.colors.muted, fontSize: theme.type.small, lineHeight: 21 },
  pitch: { backgroundColor: theme.colors.green, borderWidth: 2, borderColor: theme.colors.onDarkMuted, borderRadius: 8, paddingVertical: 20, paddingHorizontal: 4, gap: 26, minHeight: 440, justifyContent: 'space-between', overflow: 'hidden' },
  court: { backgroundColor: theme.colors.blue, minHeight: 380 },
  pitchRow: { flexDirection: 'row', justifyContent: 'space-evenly', gap: 4 },
  slot: { flex: 1, maxWidth: 100, minHeight: 58, alignItems: 'center', justifyContent: 'center', backgroundColor: theme.colors.primaryDark, borderRadius: 8, padding: 3, borderWidth: 1, borderColor: theme.colors.onDarkMuted },
  selected: { borderColor: theme.colors.gold, borderWidth: 2 },
  name: { color: theme.colors.white, fontFamily: theme.fontFamily, fontSize: 12, textAlign: 'center', fontWeight: '600' },
  position: { color: theme.colors.onDarkMuted, fontFamily: theme.fontFamily, fontSize: 12, marginTop: 4 },
  half: { position: 'absolute', left: 0, right: 0, top: '50%', borderTopWidth: 1, borderColor: theme.colors.onDarkMuted },
  circle: { position: 'absolute', width: 80, height: 80, borderRadius: 40, borderWidth: 1, borderColor: theme.colors.onDarkMuted, top: '50%', left: '50%', transform: [{ translateX: -40 }, { translateY: -40 }] },
  area: { position: 'absolute', left: '25%', width: '50%', height: 60, borderWidth: 1, borderColor: theme.colors.onDarkMuted },
});
