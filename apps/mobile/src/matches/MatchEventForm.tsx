import { useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { Field, TextAction } from '../components/AuthLayout';
import { Button } from '../components/ui';
import { styles } from '../events/styles';
import { theme } from '../theme';
import { incidentLabels, participantLabel, type IncidentDraft, type IncidentType, type MatchIncident, type MatchParticipant } from './eventsApi';

export function MatchEventForm({ people, kind, item, busy, onSave, onCancel }: {
  people: MatchParticipant[]; kind: 'goal' | 'card'; item?: MatchIncident; busy: boolean;
  onSave: (draft: IncidentDraft) => void; onCancel: () => void;
}) {
  const [type, setType] = useState<IncidentType>(item?.type ?? (kind === 'goal' ? 'GOAL' : 'YELLOW_CARD'));
  const [participant, setParticipant] = useState(item?.participant_id ?? '');
  const [assist, setAssist] = useState<string | null>(item?.assist_participant_id ?? null);
  const [search, setSearch] = useState('');
  const selected = people.find(p => p.id === participant);
  const assistants = people.filter(p => p.squad_id === selected?.squad_id && p.id !== participant);
  const squads = [...new Map(people.map(p => [p.squad_id, p.squad_name])).entries()];
  const filtered = people.filter(p => participantLabel(p).toLocaleLowerCase('pt-BR').includes(search.trim().toLocaleLowerCase('pt-BR')));
  return <View testID="match-event-form" style={styles.stack}>
    <Text accessibilityRole="header" style={styles.heading}>{item ? 'Editar registro' : kind === 'goal' ? 'Registrar gol' : 'Registrar cartão'}</Text>
    {kind === 'card' && <View style={styles.row}>
      {(['YELLOW_CARD', 'RED_CARD'] as const).map(value => <Choice key={value} label={incidentLabels[value]} checked={type === value} disabled={busy} onPress={() => setType(value)} />)}
    </View>}
    {people.length > 8 && <Field label="Buscar participante da partida" value={search} onChangeText={setSearch} editable={!busy} />}
    <Text style={styles.note}>Selecione quem participou desta partida.</Text>
    {squads.map(([id, name]) => <View key={id} style={styles.stack}>
      <Text style={styles.heading}>{name}</Text>
      {filtered.filter(p => p.squad_id === id).map(p => <Choice key={p.id} label={participantLabel(p)} accessibilityLabel={`Participante: ${participantLabel(p)}`}
        checked={participant === p.id} disabled={busy} onPress={() => { setParticipant(p.id); setAssist(null); }} />)}
    </View>)}
    {!filtered.length && <Text style={styles.note}>Nenhum participante encontrado.</Text>}
    {selected && <Text style={styles.note}>Selecionado: {participantLabel(selected)} · {selected.squad_name}</Text>}
    {kind === 'goal' && selected && <View style={styles.stack}>
      <Text style={styles.heading}>Assistência (opcional)</Text>
      <Choice label="Sem assistência" checked={assist === null} disabled={busy} onPress={() => setAssist(null)} />
      {assistants.map(p => <Choice key={p.id} label={participantLabel(p)} accessibilityLabel={`Assistência: ${participantLabel(p)}`} checked={assist === p.id} disabled={busy} onPress={() => setAssist(p.id)} />)}
    </View>}
    <Button label={busy ? 'Salvando registro…' : 'Salvar registro'} disabled={busy || !selected}
      onPress={() => onSave({ type, participant_id: participant, assist_participant_id: type === 'GOAL' ? assist : null })} />
    <TextAction label="Voltar sem salvar registro" disabled={busy} onPress={onCancel} />
  </View>;
}

function Choice({ label, accessibilityLabel = label, checked, disabled, onPress }: {
  label: string; accessibilityLabel?: string; checked: boolean; disabled: boolean; onPress: () => void;
}) {
  return <Pressable accessibilityRole="radio" accessibilityLabel={accessibilityLabel} accessibilityState={{ checked, disabled }}
    disabled={disabled} onPress={onPress} style={[visual.option, checked && visual.selected, disabled && visual.disabled]}>
    <Text style={visual.text}>{checked ? '✓ ' : ''}{label}</Text>
  </Pressable>;
}
const visual = StyleSheet.create({
  option: { minHeight: 48, maxWidth: '100%', padding: 12, borderWidth: 1, borderColor: theme.colors.border, borderRadius: 12, justifyContent: 'center' },
  selected: { borderColor: theme.colors.green, backgroundColor: theme.colors.lightGreen },
  disabled: { opacity: 0.5 },
  text: { fontFamily: theme.fontFamily, fontSize: 15, color: theme.colors.graphite, flexShrink: 1 },
});
