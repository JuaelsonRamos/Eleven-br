import { FixtureHeading } from '../opponents/FixtureHeading';
import { CallupEditor } from './CallupEditor';
import { saveCallup, respondGuest , remindPending } from './api';
import { useCallback, useEffect, useRef, useState } from 'react';
import { BackHandler, Text, View } from 'react-native';
import { useFocusEffect } from '@react-navigation/native';
import { ApiError } from '../auth/api';
import { Field, FormError, TextAction } from '../components/AuthLayout';
import { Badge, Button, Card, EmptyState, LoadingState, FilterChip } from '../components/ui';
import { useTeams } from '../teams/TeamContext';
import type { Team } from '../teams/api';
import { addGuest, cancelEvent, cancelSeries, eventWhen, getEvent, listEvents, removeGuest, respond, type Answer, type EventPage, type SportEvent } from './api';
import { EventForm } from './EventForm';
import { styles } from './styles';
import { MatchesPanel } from '../matches/MatchesPanel';
import { FormationPanel } from '../formations/FormationPanel';


export function EventPanel({ team, onNavigate, initialEventId, onInitialConsumed, onOpenFixture }: { team: Team; onNavigate?: () => void; initialEventId?: string; onInitialConsumed?: () => void; onOpenFixture?: (fixtureId: string) => void }) {
  const initial = useRef(initialEventId);
  const consumed = useRef(onInitialConsumed);
  const { options } = useTeams();
  const [page, setPage] = useState<EventPage | null>(null);
  const [event, setEvent] = useState<SportEvent | null>(null);
  const [mode, setMode] = useState<'list' | 'detail' | 'create' | 'edit' | 'formation'>('list');
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const sending = useRef(false);
  const generation = useRef(0);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [guest, setGuest] = useState('');
  const [guestResponse, setGuestResponse] = useState<Answer>('PENDENTE');
  const [cancelConfirm, setCancelConfirm] = useState<'event' | 'series' | null>(null);
  const load = useCallback(async () => {
    const revision = ++generation.current; setLoading(true); setError(null);
    try { const data = await listEvents(team.id); const requested = initial.current; const selected = requested ? await getEvent(team.id, requested) : null; if (revision === generation.current) { setPage(data); setMode(selected ? 'detail' : 'list'); setEvent(selected); initial.current = undefined; if (requested) consumed.current?.(); } }
    catch (err) { if (revision === generation.current) { setPage(null); setError(err instanceof Error ? err.message : 'Não foi possível carregar os jogos.'); } }
    finally { if (revision === generation.current) setLoading(false); }
  }, [team.id]);
  useEffect(() => { const currentGeneration = generation; void load(); return () => { currentGeneration.current++; }; }, [load]);
  useEffect(() => {
    consumed.current = onInitialConsumed;
    if (initialEventId && initialEventId !== initial.current) { initial.current = initialEventId; void load(); }
  }, [initialEventId, onInitialConsumed, load]);
  function back() { setCancelConfirm(null); setGuest(''); setSuccess(null); void load(); }
  useFocusEffect(useCallback(() => {
    const handler = BackHandler.addEventListener('hardwareBackPress', () => {
      if (mode === 'list') return false;
      if (!sending.current) { setCancelConfirm(null); setGuest(''); void load(); }
      return true;
    });
    return () => handler.remove();
  }, [mode, load]));
  async function run(action: () => Promise<SportEvent>, message?: string, open = true) {
    if (sending.current) return false;
    const revision = generation.current; sending.current = true; setBusy(true); setError(null); setSuccess(null);
    try {
      const updated = await action();
      if (revision !== generation.current) return false;
      if (open) { setEvent(updated); setMode('detail'); }
      setPage(previous => previous && ({ ...previous, items: previous.items.map(item => item.id === updated.id ? updated : item) }));
      setGuest(''); setCancelConfirm(null); setSuccess(message || null);
      return true;
    } catch (err) {
      if (revision !== generation.current) return false;
      setError(err instanceof Error ? err.message : 'Não foi possível concluir.');
      if (err instanceof ApiError && [403, 404].includes(err.status)) { setPage(null); setEvent(null); setMode('list'); }
      return false;
    } finally { sending.current = false; if (revision === generation.current) setBusy(false); }
  }
  async function remind(item: SportEvent) {
    if (sending.current) return;
    const revision = generation.current; sending.current = true; setBusy(true); setError(null); setSuccess(null);
    try {
      const result = await remindPending(team.id, item.id);
      if (revision === generation.current) setSuccess(result.count ? `${result.count} jogador${result.count === 1 ? ' foi lembrado' : 'es foram lembrados'}.` : 'Nenhum novo lembrete. Os pendentes já foram lembrados.');
    } catch (cause) { if (revision === generation.current) setError(cause instanceof Error ? cause.message : 'Não foi possível enviar os lembretes.'); }
    finally { sending.current = false; if (revision === generation.current) setBusy(false); }
  }
  const answers = (item: SportEvent, open: boolean) => item.participation_open && item.can_respond && <View style={styles.row}>
    {(['VOU', 'NAO_VOU'] as const).map(value => <FilterChip key={value} disabled={busy} label={value === 'VOU' ? 'VOU' : 'NÃO VOU'} selected={item.my_response === value}
      onPress={() => void run(() => respond(team.id, item.id, value), 'Presença atualizada.', open)} />)}
  </View>;
  if (loading) return <LoadingState />;
  if (mode === 'formation' && event) return <FormationPanel key={event.id} team={team} event={event} onNavigate={onNavigate}
    onBack={() => void run(() => getEvent(team.id, event.id))} />;
  if (mode === 'create' || (mode === 'edit' && event)) return <EventForm team={team} creationKey={page?.creation_key} event={mode === 'edit' ? event! : undefined}
    onCancel={back} onDenied={back} onDone={saved => { setEvent(saved); setMode('detail'); setSuccess('Evento salvo.'); }} />;
  return <View style={styles.stack}>
    <Text accessibilityRole="header" style={styles.title}>{mode === 'detail' && event ? event.title : 'Jogos'}</Text>
    <FormError message={error} />
    {success && <Text accessibilityLiveRegion="polite" style={styles.success}>{success}</Text>}
    {!page && <Button label="Tentar novamente" onPress={() => void load()} />}
    {mode === 'detail' && event ? <>
      <Card><View style={styles.stack}>
        <Badge label={event.status === 'cancelled' ? 'CANCELADO' : event.kind === 'PELADA' ? 'PELADA' : event.fixture_id ? 'CONFRONTO OFICIAL' : 'JOGO AVULSO'} />
        <Text style={styles.heading}>{eventWhen(event)}</Text><Text style={styles.text}>{event.location}</Text>
        <Text style={styles.note}>{options?.modalities.find(item => item.value === event.modality)?.label || event.modality}</Text>
        {event.series_id && <Text style={styles.note}>Pelada semanal • {event.recurrence_status === 'cancelled' ? 'recorrência encerrada' : event.recurring_until ? `até ${displayDay(event.recurring_until)}` : 'sem data final'} • presença por data</Text>}
        {event.fixture && <FixtureHeading item={event.fixture} />}
        {event.opponent && <Text style={styles.text}>Adversário: {event.opponent}</Text>}
        {event.fixture_id && <Text style={styles.note}>Confronto oficial: data, horário e local foram combinados entre os dois times e não mudam por um só time.</Text>}
        {event.fixture_id && onOpenFixture && <Button variant="secondary" label="Ver confronto" disabled={busy} onPress={() => onOpenFixture(event.fixture_id!)} />}
        {event.notes && <Text style={styles.text}>{event.notes}</Text>}
        {answers(event, true)}
        <Text style={styles.note}>{!event.can_respond ? 'Você não está convocado.' : `Sua resposta: ${event.my_response === 'VOU' ? 'Vou' : event.my_response === 'NAO_VOU' ? 'Não vou' : 'Pendente'}`}</Text>
      </View></Card>
      {([{ value: 'VOU', label: 'Confirmados', count: event.going }, { value: 'NAO_VOU', label: 'Não vão', count: event.not_going }, { value: 'PENDENTE', label: 'Pendentes', count: event.pending }] as { value: Answer; label: string; count: number }[]).map(group => <View key={group.value} style={styles.stack}>
        <Text accessibilityRole="header" style={styles.heading}>{group.label}: {group.count}</Text>
        {event.participants.filter(person => person.response === group.value).map(person => <Text key={person.membership_id} style={styles.text}>{person.name}</Text>)}
      </View>)}
      <Text style={styles.note}>{event.fixture_id ? `Convocados: ${event.participants.length}. Somente convocados ativos entram na presença.` : 'A lista considera jogadores ativos do elenco.'} Convidados aparecem separadamente.</Text>
      {event.fixture_id && event.can_manage && event.participation_open && <CallupEditor key={event.callup_version} event={event} busy={busy} onSave={ids => run(() => saveCallup(team.id, event, ids), 'Convocação salva.')} />}
      {event.can_manage && event.participation_open && <Button variant="secondary" label="Lembrar pendentes" disabled={busy} onPress={() => void remind(event)} />}
      {event.kind === 'PELADA' && <Button label={event.can_manage && event.participation_open ? 'Montar times' : 'Ver times da pelada'} disabled={busy}
        onPress={() => { setError(null); setSuccess(null); setMode('formation'); onNavigate?.(); }} />}
      {event.kind === 'PELADA' && <MatchesPanel key={event.id} teamId={team.id} event={event} />}
      <Text accessibilityRole="header" style={styles.heading}>Convidados: {event.guests.length}</Text>
      {event.guests.map(person => <View key={person.id} style={styles.row}><Text style={styles.text}>{person.name} • {person.response === 'VOU' ? 'Confirmado' : person.response === 'NAO_VOU' ? 'Não vai' : 'Pendente'}</Text>{event.fixture_id && event.can_manage && event.participation_open && (['VOU', 'NAO_VOU', 'PENDENTE'] as Answer[]).map(answer => <FilterChip key={answer} label={answer === 'VOU' ? 'Confirmado' : answer === 'NAO_VOU' ? 'Não vai' : 'Pendente'} selected={person.response === answer} disabled={busy} onPress={() => void run(() => respondGuest(team.id, event.id, person.id, answer))} />)}{event.can_manage && event.participation_open && <TextAction label={`Remover ${person.name}`} disabled={busy} onPress={() => void run(() => removeGuest(team.id, event.id, person.id), 'Convidado removido.')} />}</View>)}
      {event.can_manage && event.participation_open && <>
        <Field label="Nome/apelido do convidado" value={guest} onChangeText={setGuest} maxLength={80} editable={!busy} />
        {event.fixture_id && <View style={styles.row}>{(['PENDENTE', 'VOU', 'NAO_VOU'] as Answer[]).map(answer => <FilterChip key={answer} label={answer === 'VOU' ? 'Confirmado' : answer === 'NAO_VOU' ? 'Não vai' : 'Pendente'} selected={guestResponse === answer} disabled={busy} onPress={() => setGuestResponse(answer)} />)}</View>}
        <Button label="Adicionar convidado" disabled={busy || !guest.trim()} onPress={() => void run(() => addGuest(team.id, event.id, guest.trim(), event.guest_creation_key, event.fixture_id ? guestResponse : 'VOU'), 'Convidado adicionado.')} />
        {!event.fixture_id && <><Button label="Editar evento" disabled={busy} onPress={() => { setError(null); setMode('edit'); }} />
        {cancelConfirm === 'event' ? <><Text style={styles.text}>Cancelar {event.series_id ? 'somente esta ocorrência' : 'este evento'}? As respostas serão preservadas.</Text>
          <Button label="Confirmar cancelamento" disabled={busy} onPress={() => void run(() => cancelEvent(team.id, event.id), 'Evento cancelado.')} />
          <TextAction label="Manter evento" disabled={busy} onPress={() => setCancelConfirm(null)} /></> : <TextAction label="Cancelar evento" disabled={busy} onPress={() => setCancelConfirm('event')} />}</>}
      </>}
      {event.can_manage && event.series_id && event.recurrence_status === 'active' && (cancelConfirm === 'series' ? <>
        <Text style={styles.text}>Encerrar a recorrência? As ocorrências de hoje em diante serão canceladas. Histórico, respostas e convidados serão preservados.</Text>
        <Button label="Confirmar fim da recorrência" disabled={busy} onPress={() => void run(() => cancelSeries(team.id, event.id), 'Recorrência encerrada.')} />
        <TextAction label="Manter recorrência" disabled={busy} onPress={() => setCancelConfirm(null)} />
      </> : <TextAction label="Encerrar recorrência" disabled={busy} onPress={() => setCancelConfirm('series')} />)}
      <TextAction label="Voltar aos jogos" disabled={busy} onPress={back} />
    </> : <>
      {page?.can_manage && <Button label="Criar evento" disabled={busy} onPress={() => { setSuccess(null); setMode('create'); }} />}
      {page && !page.items.length && <EmptyState title="O próximo encontro começa aqui" description="Os eventos do time aparecerão nesta lista." icon="football-outline" />}
      {page?.items.map(item => <Card key={item.id}><View style={styles.stack}>
        {item.fixture && <FixtureHeading item={item.fixture} />}
        <Badge label={item.kind === 'PELADA' ? 'PELADA' : item.fixture_id ? 'CONFRONTO OFICIAL' : 'JOGO'} tone="info" /><Text style={styles.heading}>{item.title}</Text><Text style={styles.text}>{eventWhen(item)}</Text><Text style={styles.note}>{item.location}</Text>
        {item.status === 'cancelled' ? <Badge label="CANCELADO" tone="neutral" /> : <Badge label={`${item.going} confirmados`} />}
        {answers(item, false)}
        <Button variant="secondary" label="Ver detalhes" accessibilityLabel={`Abrir ${item.title} • ${displayDay(item.date)}`} disabled={busy} onPress={() => void run(() => getEvent(team.id, item.id))} />
      </View></Card>)}
    </>}
  </View>;
}
const displayDay = (date: string) => date.split('-').reverse().join('/');
