import { useCallback, useEffect, useRef, useState } from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { FormError, TextAction } from '../components/AuthLayout';
import { Button, LoadingState } from '../components/ui';
import { styles } from '../events/styles';
import { theme } from '../theme';
import type { Match } from './api';
import { MatchEventForm } from './MatchEventForm';
import { getMatchEvents, incidentLabels, participantLabel, removeMatchEvent, saveMatchEvent, type MatchEventsPage, type MatchIncident } from './eventsApi';

export function MatchEventsPanel({ teamId, eventId, match, disabled, onMatchChange, onClose }: {
  teamId: string; eventId: string; match: Match; disabled: boolean;
  onMatchChange: (match: Match) => void; onClose: () => void;
}) {
  const [page, setPage] = useState<MatchEventsPage | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [blocked, setBlocked] = useState(false);
  const [form, setForm] = useState<{ kind: 'goal' | 'card'; item?: MatchIncident } | null>(null);
  const [removing, setRemoving] = useState<MatchIncident | null>(null);
  const sending = useRef(false);
  const generation = useRef(0);
  const acceptedVersion = useRef<number | null>(null);
  const reportMatch = useRef(onMatchChange); reportMatch.current = onMatchChange;
  const accept = useCallback((value: MatchEventsPage) => {
    acceptedVersion.current = value.match.version;
    setPage(value); setForm(null); setRemoving(null); setBlocked(false);
    reportMatch.current(value.match);
  }, []);
  const load = useCallback(async () => {
    const revision = ++generation.current; setLoading(true); setError(null);
    try { const value = await getMatchEvents(teamId, eventId, match.id); if (revision === generation.current) accept(value); }
    catch (cause) { if (revision === generation.current) { setPage(null); setBlocked(true); setError(cause instanceof Error ? cause.message : 'Não foi possível carregar os registros.'); } }
    finally { if (revision === generation.current) setLoading(false); }
  }, [teamId, eventId, match.id, accept]);
  useEffect(() => {
    const counter = generation;
    if (acceptedVersion.current !== match.version) void load();
    return () => { counter.current++; };
  }, [load, match.version]);
  async function run(action: () => Promise<MatchEventsPage>) {
    if (sending.current || disabled || blocked) return;
    const revision = generation.current; sending.current = true; setBusy(true); setError(null);
    try { const value = await action(); if (revision === generation.current) accept(value); }
    catch (cause) {
      if (revision === generation.current) {
        setError(cause instanceof Error ? cause.message : 'Não foi possível salvar. Recarregue para conferir o envio.');
        // A lost response may already have committed: don't retry with a fresh version silently.
        setBlocked(true); setForm(null); setRemoving(null);
      }
    } finally { sending.current = false; setBusy(false); }
  }
  const label = (id: string) => { const person = page?.participants.find(p => p.id === id); return person ? participantLabel(person) : 'Participante'; };
  const unavailable = busy || disabled;
  return <View testID="match-events" style={visual.panel}>
    <Text accessibilityRole="header" style={styles.heading}>Eventos da partida</Text>
    <FormError message={error} />
    {loading ? <LoadingState /> : blocked || !page ? <Button label="Recarregar eventos da partida" disabled={unavailable} onPress={() => void load()} /> : <>
      <View style={styles.stack}>
        {page.goals.map(goal => <View key={goal.squad_id}>
          <Text style={styles.note}>{goal.name}: {goal.identified} de {goal.score} gols identificados.</Text>
          {goal.missing > 0 && <Text style={styles.note}>Falta identificar {goal.missing} {goal.missing === 1 ? 'gol' : 'gols'} do {goal.name}.</Text>}
          {goal.excess > 0 && <Text style={styles.note}>{goal.name}: existem mais gols registrados que o placar da partida.</Text>}
        </View>)}
        <Text style={styles.note}>O placar é o resultado oficial. Estes registros não alteram o placar.</Text>
      </View>
      {page.match.status === 'CANCELLED' && <Text style={styles.note}>Partida cancelada. Registros preservados para histórico.</Text>}
      {page.match.status === 'SCHEDULED' && <Text style={styles.note}>Inicie a partida para registrar gols e cartões.</Text>}
      {form ? <MatchEventForm key={form.item?.id ?? form.kind} people={page.participants} kind={form.kind} item={form.item} busy={unavailable}
        onCancel={() => setForm(null)} onSave={draft => void run(() => saveMatchEvent(teamId, eventId, page.match, draft, form.item?.id))} /> : <>
        {!page.items.length && <Text style={styles.note}>Nenhum gol ou cartão registrado.</Text>}
        {page.items.map((item, index) => <View key={item.id} testID={`match-event-${index + 1}`} style={visual.item}>
          <Text style={styles.text}>{item.type === 'GOAL' ? '⚽' : item.type === 'YELLOW_CARD' ? '🟨' : '🟥'} {incidentLabels[item.type]} · {label(item.participant_id)}</Text>
          <Text style={styles.note}>{page.goals.find(g => g.squad_id === item.squad_id)?.name}</Text>
          {item.assist_participant_id && <Text style={styles.note}>Assistência: {label(item.assist_participant_id)}</Text>}
          {item.updated_at !== item.created_at && <Text style={styles.note}>Registro corrigido em {new Date(item.updated_at).toLocaleString('pt-BR')}.</Text>}
          {page.can_manage && (removing?.id === item.id ? <>
            <Text accessibilityRole="alert" style={styles.text}>Remover {incidentLabels[item.type].toLowerCase()} de {label(item.participant_id)}?</Text>
            <Button label="Confirmar remoção do registro" disabled={unavailable} onPress={() => void run(() => removeMatchEvent(teamId, eventId, page.match, item.id))} />
            <TextAction label="Manter registro" disabled={unavailable} onPress={() => setRemoving(null)} />
          </> : <View style={styles.row}>
            <TextAction label="Editar registro" disabled={unavailable || !!removing} onPress={() => setForm({ kind: item.type === 'GOAL' ? 'goal' : 'card', item })} />
            <TextAction label="Remover registro" disabled={unavailable || !!removing} onPress={() => setRemoving(item)} />
          </View>)}
        </View>)}
        {page.can_manage && !removing && <>
          <Button label="Registrar gol" disabled={unavailable} onPress={() => setForm({ kind: 'goal' })} />
          <Button label="Registrar cartão" disabled={unavailable} onPress={() => setForm({ kind: 'card' })} />
        </>}
        <TextAction label="Atualizar eventos da partida" disabled={unavailable || !!removing} onPress={() => void load()} />
      </>}
    </>}
    <TextAction label="Fechar eventos da partida" disabled={unavailable} onPress={onClose} />
  </View>;
}
const visual = StyleSheet.create({
  panel: { gap: 16, borderTopWidth: 1, borderColor: theme.colors.border, paddingTop: 16, minWidth: 0 },
  item: { gap: 8, borderBottomWidth: 1, borderColor: theme.colors.border, paddingVertical: 12 },
});
