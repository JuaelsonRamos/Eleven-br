import { useRef, useState } from 'react';
import { Pressable, Switch, Text, View } from 'react-native';
import { Field, FormError, TextAction } from '../components/AuthLayout';
import { Button } from '../components/ui';
import { ApiError } from '../auth/api';
import { useTeams } from '../teams/TeamContext';
import type { Team } from '../teams/api';
import { saveEvent, type SportEvent } from './api';
import { styles } from './styles';

function isoDate(input: string): string | null {
  const match = /^(\d{2})\/(\d{2})\/(\d{4})$/.exec(input);
  if (!match) return null;
  const iso = `${match[3]}-${match[2]}-${match[1]}`;
  const parsed = new Date(`${iso}T12:00:00Z`);
  return !Number.isNaN(parsed.getTime()) && parsed.toISOString().slice(0, 10) === iso ? iso : null;
}
const displayDate = (iso: string) => iso.split('-').reverse().join('/');

export function EventForm({ team, event, onDone, onCancel, onDenied }: {
  team: Team; event?: SportEvent; onDone: (event: SportEvent) => void; onCancel: () => void; onDenied: () => void;
}) {
  const { options } = useTeams();
  const modalities = options.modalities.filter(item => team.modalities.includes(item.value));
  const [kind, setKind] = useState<'PELADA' | 'JOGO'>(event?.kind || 'PELADA');
  const [title, setTitle] = useState(event?.title || '');
  const [modality, setModality] = useState(event?.modality ?? modalities[0]?.value ?? '');
  const selectedModality = modalities.some(item => item.value === modality) ? modality : '';
  const [date, setDate] = useState(event ? displayDate(event.date) : '');
  const [time, setTime] = useState(event?.time.slice(0, 5) || '');
  const [location, setLocation] = useState(event?.location || '');
  const [notes, setNotes] = useState(event?.notes || '');
  const [opponent, setOpponent] = useState(event?.opponent || '');
  const [weekly, setWeekly] = useState(false);
  const [until, setUntil] = useState('');
  const [busy, setBusy] = useState(false);
  const sending = useRef(false);
  const [error, setError] = useState<string | null>(null);
  async function save() {
    if (sending.current) return;
    if (!title.trim()) { setError('Informe o título.'); return; }
    if (!selectedModality) { setError('Selecione uma modalidade.'); return; }
    if (!date.trim()) { setError('Informe a data.'); return; }
    const start = isoDate(date.trim()), end = isoDate(until);
    if (!start) { setError('Informe uma data válida (DD/MM/AAAA).'); return; }
    if (!time.trim()) { setError('Informe o horário.'); return; }
    if (!/^([01]\d|2[0-3]):[0-5]\d$/.test(time.trim())) { setError('Informe um horário válido (HH:MM).'); return; }
    if (!location.trim()) { setError('Informe o local.'); return; }
    if (weekly && kind === 'PELADA' && !event && until.trim()) {
      const days = end ? (Date.parse(end) - Date.parse(start)) / 86400000 : 0;
      if (days < 7) { setError('Confira o término: pelo menos 7 dias após a primeira pelada.'); return; }
    }
    sending.current = true; setBusy(true); setError(null);
    try {
      onDone(await saveEvent(team.id, { title: title.trim(), kind, modality: selectedModality, date: start, time: time.trim(),
        location: location.trim(), notes: notes.trim() || null, opponent: kind === 'JOGO' ? opponent.trim() || null : null,
        ...(!event ? { recurring_weekly: weekly && kind === 'PELADA', recurring_until: weekly && kind === 'PELADA' ? end : null } : {}),
      }, event?.id));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Não foi possível salvar.');
      if (err instanceof ApiError && [403, 404].includes(err.status)) onDenied();
    } finally { sending.current = false; setBusy(false); }
  }
  return <View style={styles.stack}>
    <Text accessibilityRole="header" style={styles.title}>{event ? 'Editar evento' : 'Criar evento'}</Text>
    {event?.series_id && <Text style={styles.note}>Esta edição vale somente para esta ocorrência. As demais datas permanecem iguais.</Text>}
    {!event?.series_id && <View style={styles.row}>{(['PELADA', 'JOGO'] as const).map(value => <Pressable key={value} disabled={busy} accessibilityRole="radio" accessibilityState={{ checked: kind === value }} aria-checked={kind === value}
      onPress={() => setKind(value)} style={[styles.chip, kind === value && styles.selected]}><Text style={styles.text}>{value === 'PELADA' ? 'Pelada' : 'Jogo avulso'}</Text></Pressable>)}</View>}
    <Field label="Título do evento" value={title} onChangeText={setTitle} maxLength={100} editable={!busy} />
    <Text style={styles.text}>Modalidade</Text>
    <View style={styles.row}>{modalities.map(item => <Pressable key={item.value} disabled={busy} accessibilityRole="radio" accessibilityLabel={item.label} accessibilityState={{ checked: selectedModality === item.value }} aria-checked={selectedModality === item.value}
      onPress={() => setModality(item.value)} style={[styles.chip, selectedModality === item.value && styles.selected]}><Text style={styles.text}>{item.label}</Text></Pressable>)}</View>
    <Field label="Data (DD/MM/AAAA)" value={date} onChangeText={setDate} placeholder="27/09/2026" maxLength={10} editable={!busy} />
    <Field label="Horário (HH:MM)" value={time} onChangeText={setTime} placeholder="08:00" maxLength={5} editable={!busy} />
    <Text style={styles.note}>Use a data e o horário locais da partida.</Text>
    {!event && kind === 'PELADA' && <><View style={styles.row}><Switch accessibilityLabel="Repetir semanalmente" value={weekly} onValueChange={setWeekly} disabled={busy} /><Text style={styles.text}>Repetir semanalmente</Text></View>
      {weekly && <><Field label="Repetir até (DD/MM/AAAA) — opcional" value={until} onChangeText={setUntil} maxLength={10} editable={!busy} /><Text style={styles.note}>Deixe o término vazio para repetir toda semana até cancelar. Cada data tem sua própria lista de presença. As próximas oito semanas aparecem na agenda.</Text></>}</>}
    <Field label="Local" value={location} onChangeText={setLocation} maxLength={200} editable={!busy} />
    {kind === 'JOGO' && <Field label="Adversário (opcional)" value={opponent} onChangeText={setOpponent} maxLength={100} editable={!busy} />}
    <Field label="Observações (opcional)" value={notes} onChangeText={setNotes} maxLength={2000} multiline editable={!busy} />
    <FormError message={error} />
    <Button label={busy ? 'Salvando…' : 'Salvar evento'} onPress={() => void save()} disabled={busy} />
    <TextAction label="Voltar aos jogos" onPress={onCancel} disabled={busy} />
  </View>;
}
