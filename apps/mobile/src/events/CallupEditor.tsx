import { useState } from 'react';
import { Text, View } from 'react-native';
import { Button, FilterChip } from '../components/ui';
import { TextAction } from '../components/AuthLayout';
import { styles } from './styles';
import type { SportEvent } from './api';

export function CallupEditor({ event, busy, onSave }: { event: SportEvent; busy: boolean; onSave: (ids: string[]) => Promise<boolean> }) {
  const [open, setOpen] = useState(false);
  const [selected, setSelected] = useState<string[]>([]);
  if (!open) return <Button variant="secondary" label="Gerenciar convocação" disabled={busy} onPress={() => { setSelected(event.callup_candidates.filter(p => p.selected).map(p => p.membership_id)); setOpen(true); }} />;
  return <View style={styles.stack}>
    <Text style={styles.heading}>Convocação</Text>
    <Text style={styles.note}>{selected.length} jogadores selecionados</Text>
    <TextAction label="Selecionar todos" disabled={busy} onPress={() => setSelected(event.callup_candidates.map(p => p.membership_id))} />
    {event.callup_candidates.map(p => <FilterChip role="checkbox" key={p.membership_id} label={p.name} selected={selected.includes(p.membership_id)} disabled={busy} onPress={() => setSelected(prev => prev.includes(p.membership_id) ? prev.filter(id => id !== p.membership_id) : [...prev, p.membership_id])} />)}
    <Button label="Salvar convocação" disabled={busy} onPress={() => void onSave(selected).then(saved => { if (saved) setOpen(false); })} />
    <TextAction label="Voltar sem salvar" disabled={busy} onPress={() => setOpen(false)} />
  </View>;
}
