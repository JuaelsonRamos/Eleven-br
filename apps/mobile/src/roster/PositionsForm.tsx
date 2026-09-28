import { useEffect, useRef, useState } from 'react';
import { Text, View } from 'react-native';
import { Button, FilterChip, LoadingState } from '../components/ui';
import { FormError, TextAction } from '../components/AuthLayout';
import { positionOptions, savePositions, type RosterPerson } from './api';
import { rosterStyles as s } from './styles';

export function PositionsForm({ teamId, player, onSaved, onCancel }: { teamId: string; player: RosterPerson; onSaved: (value: RosterPerson) => void; onCancel: () => void }) {
  const [options, setOptions] = useState<{ value: string; label: string }[] | null>(null);
  const [positions, setPositions] = useState(player.positions), [primary, setPrimary] = useState(player.primary_position);
  const [error, setError] = useState<string | null>(null), [busy, setBusy] = useState(false), lock = useRef(false);
  useEffect(() => { let active = true; void positionOptions(teamId).then(value => { if (active) setOptions(value); }).catch(cause => { if (active) setError(cause.message); }); return () => { active = false; }; }, [teamId]);
  async function save() {
    if (lock.current) return; lock.current = true; setBusy(true); setError(null);
    try { onSaved(await savePositions(teamId, player, positions, primary)); }
    catch (cause) { setError(cause instanceof Error ? cause.message : 'Não foi possível salvar.'); }
    finally { lock.current = false; setBusy(false); }
  }
  return <View style={s.stack}>
    <Text accessibilityRole="header" style={s.heading}>Posições de {player.name}</Text>
    <Text style={s.note}>Selecione onde joga neste time. Escolha uma posição principal.</Text>
    {!options && !error && <LoadingState />}
    <View style={s.row}>{options?.map(item => <FilterChip key={item.value} label={`${item.value} · ${item.label}`} selected={positions.includes(item.value)} onPress={() => {
      if (busy) return;
      const next = positions.includes(item.value) ? positions.filter(value => value !== item.value) : [...positions, item.value];
      setPositions(next); if (!primary || !next.includes(primary)) setPrimary(next[0] ?? null);
    }} />)}</View>
    {!!positions.length && <><Text style={s.label}>Posição principal</Text><View style={s.row}>{positions.map(value => <FilterChip key={value} label={`Principal: ${value}`} selected={primary === value} onPress={() => { if (!busy) setPrimary(value); }} />)}</View></>}
    <FormError message={error} />
    <Button label={busy ? 'Salvando…' : 'Salvar posições'} disabled={busy || !options} onPress={() => void save()} />
    <TextAction label="Cancelar" disabled={busy} onPress={onCancel} />
  </View>;
}
