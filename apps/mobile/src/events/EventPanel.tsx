import { useCallback, useEffect, useRef, useState } from 'react';
import { BackHandler, Pressable, Text, View } from 'react-native';
import { useFocusEffect } from '@react-navigation/native';
import { ApiError } from '../auth/api';
import { Field, FormError, TextAction } from '../components/AuthLayout';
import { Badge, Button, Card, EmptyState, LoadingState } from '../components/ui';
import { useTeams } from '../teams/TeamContext';
import type { Team } from '../teams/api';
import { addGuest, cancelEvent, cancelSeries, eventWhen, getEvent, listEvents, removeGuest, respond, type Answer, type EventPage, type SportEvent } from './api';
import { EventForm } from './EventForm';
import { styles } from './styles';

export function EventPanel({ team }: { team: Team }) {
  const { options } = useTeams();
  const [page, setPage] = useState<EventPage | null>(null);
  const [event, setEvent] = useState<SportEvent | null>(null);
  const [mode, setMode] = useState<'list' | 'detail' | 'create' | 'edit'>('list');
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const sending = useRef(false);
  const generation = useRef(0);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [guest, setGuest] = useState('');
  const [cancelConfirm, setCancelConfirm] = useState<'event' | 'series' | null>(null);
  const load = useCallback(async () => {
    const revision = ++generation.current; setLoading(true); setError(null);
    try { const data = await listEvents(team.id); if (revision === generation.current) { setPage(data); setMode('list'); setEvent(null); } }
    catch (err) { if (revision === generation.current) { setPage(null); setError(err instanceof Error ? err.message : 'Não foi possível carregar os jogos.'); } }
    finally { if (revision === generation.current) setLoading(false); }
  }, [team.id]);
  useEffect(() => { const currentGeneration = generation; void load(); return () => { currentGeneration.current++; }; }, [load]);
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
    if (sending.current) return;
    const revision = generation.current; sending.current = true; setBusy(true); setError(null); setSuccess(null);
    try {
      const updated = await action();
      if (revision !== generation.current) return;
      if (open) { setEvent(updated); setMode('detail'); }
      setPage(previous => previous && ({ ...previous, items: previous.items.map(item => item.id === updated.id ? updated : item) }));
      setGuest(''); setCancelConfirm(null); setSuccess(message || null);
    } catch (err) {
      if (revision !== generation.current) return;
      setError(err instanceof Error ? err.message : 'Não foi possível concluir.');
      if (err instanceof ApiError && [403, 404].includes(err.status)) { setPage(null); setEvent(null); setMode('list'); }
    } finally { sending.current = false; if (revision === generation.current) setBusy(false); }
  }
  const answers = (item: SportEvent, open: boolean) => item.status === 'open' && <View style={styles.row}>
    {(['VOU', 'NAO_VOU'] as const).map(value => <Pressable key={value} disabled={busy} accessibilityRole="button" accessibilityLabel={value === 'VOU' ? 'VOU' : 'NÃO VOU'} accessibilityState={{ selected: item.my_response === value, disabled: busy }}
      style={[styles.chip, item.my_response === value && styles.selected]} onPress={() => void run(() => respond(team.id, item.id, value), 'Presença atualizada.', open)}>
      <Text style={styles.text}>{item.my_response === value ? '✓ ' : ''}{value === 'VOU' ? 'VOU' : 'NÃO VOU'}</Text></Pressable>)}
  </View>;
  if (loading) return <LoadingState />;
  if (mode === 'create' || (mode === 'edit' && event)) return <EventForm team={team} event={mode === 'edit' ? event! : undefined}
    onCancel={back} onDenied={back} onDone={saved => { setEvent(saved); setMode('detail'); setSuccess('Evento salvo.'); }} />;
  return <View style={styles.stack}>
    <Text accessibilityRole="header" style={styles.title}>{mode === 'detail' && event ? event.title : 'Jogos'}</Text>
    <FormError message={error} />
    {success && <Text accessibilityLiveRegion="polite" style={styles.success}>{success}</Text>}
    {!page && <Button label="Tentar novamente" onPress={() => void load()} />}
    {mode === 'detail' && event ? <>
      <Card><View style={styles.stack}>
        <Badge label={event.status === 'cancelled' ? 'CANCELADO' : event.kind === 'PELADA' ? 'PELADA' : 'JOGO AVULSO'} />
        <Text style={styles.heading}>{eventWhen(event)}</Text><Text style={styles.text}>{event.location}</Text>
        <Text style={styles.note}>{options?.modalities.find(item => item.value === event.modality)?.label || event.modality}</Text>
        {event.series_id && <Text style={styles.note}>Pelada semanal • {event.recurrence_status === 'cancelled' ? 'recorrência encerrada' : event.recurring_until ? `até ${displayDay(event.recurring_until)}` : 'sem data final'} • presença por data</Text>}
        {event.opponent && <Text style={styles.text}>Adversário: {event.opponent}</Text>}
        {event.notes && <Text style={styles.text}>{event.notes}</Text>}
        {answers(event, true)}
        <Text style={styles.note}>Sua resposta: {event.my_response === 'VOU' ? 'Vou' : event.my_response === 'NAO_VOU' ? 'Não vou' : 'Pendente'}</Text>
      </View></Card>
      {([{ value: 'VOU', label: 'Confirmados', count: event.going }, { value: 'NAO_VOU', label: 'Não vão', count: event.not_going }, { value: 'PENDENTE', label: 'Pendentes', count: event.pending }] as { value: Answer; label: string; count: number }[]).map(group => <View key={group.value} style={styles.stack}>
        <Text accessibilityRole="header" style={styles.heading}>{group.label}: {group.count}</Text>
        {event.participants.filter(person => person.response === group.value).map(person => <Text key={person.membership_id} style={styles.text}>{person.name}</Text>)}
      </View>)}
      <Text style={styles.note}>A lista considera jogadores ativos do elenco. Convidados aparecem separadamente.</Text>
      <Text accessibilityRole="header" style={styles.heading}>Convidados: {event.guests.length}</Text>
      {event.guests.map(person => <View key={person.id} style={styles.row}><Text style={styles.text}>{person.name}</Text>{event.can_manage && event.status === 'open' && <TextAction label={`Remover ${person.name}`} disabled={busy} onPress={() => void run(() => removeGuest(team.id, event.id, person.id), 'Convidado removido.')} />}</View>)}
      {event.can_manage && event.status === 'open' && <>
        <Field label="Nome/apelido do convidado" value={guest} onChangeText={setGuest} maxLength={80} editable={!busy} />
        <Button label="Adicionar convidado" disabled={busy || !guest.trim()} onPress={() => void run(() => addGuest(team.id, event.id, guest.trim()), 'Convidado adicionado.')} />
        <Button label="Editar evento" disabled={busy} onPress={() => { setError(null); setMode('edit'); }} />
        {cancelConfirm === 'event' ? <><Text style={styles.text}>Cancelar {event.series_id ? 'somente esta ocorrência' : 'este evento'}? As respostas serão preservadas.</Text>
          <Button label="Confirmar cancelamento" disabled={busy} onPress={() => void run(() => cancelEvent(team.id, event.id), 'Evento cancelado.')} />
          <TextAction label="Manter evento" disabled={busy} onPress={() => setCancelConfirm(null)} /></> : <TextAction label="Cancelar evento" disabled={busy} onPress={() => setCancelConfirm('event')} />}
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
        <Text style={styles.heading}>{item.title}</Text><Text style={styles.text}>{eventWhen(item)}</Text><Text style={styles.note}>{item.location}</Text>
        {item.status === 'cancelled' ? <Badge label="CANCELADO" /> : <Text style={styles.text}>{item.going} confirmados</Text>}
        {answers(item, false)}
        <Button label={`Abrir ${item.title} • ${displayDay(item.date)}`} disabled={busy} onPress={() => void run(() => getEvent(team.id, item.id))} />
      </View></Card>)}
    </>}
  </View>;
}
const displayDay = (date: string) => date.split('-').reverse().join('/');
