import { useEffect, useRef, useState } from 'react';
import { Text, View } from 'react-native';
import { Button, IconButton, LoadingState } from '../components/ui';
import { Field, FormError, TextAction } from '../components/AuthLayout';
import * as api from '../statistics/api';
import { rosterStyles as s } from './styles';

const fields = [['goals', 'Gols'], ['yellow_cards', 'Cartões amarelos'], ['red_cards', 'Cartões vermelhos']] as const;
export function StatisticAdjustmentForm({ teamId, memberId, name, onCancel, onSaved }: { teamId: string; memberId: string; name: string; onCancel: () => void; onSaved: () => void }) {
  const [snapshot, setSnapshot] = useState<api.Adjustment | null>(null);
  const [values, setValues] = useState({ goals: '', yellow_cards: '', red_cards: '' });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const [revision, setRevision] = useState(0);
  const sending = useRef(false);
  useEffect(() => {
    let alive = true; setSnapshot(null); setError(null); setConfirm(false);
    void api.adjustment(teamId, memberId).then(value => {
      if (alive) { setSnapshot(value); setValues({ goals: String(value.totals.goals), yellow_cards: String(value.totals.yellow_cards), red_cards: String(value.totals.red_cards) }); }
    }).catch(cause => { if (alive) setError(cause instanceof Error ? cause.message : 'Não foi possível consultar as estatísticas.'); });
    return () => { alive = false; };
  }, [teamId, memberId, revision]);
  const valid = fields.every(([key]) => /^\d{1,6}$/.test(values[key]));
  async function save() {
    if (!snapshot || !valid || sending.current) return;
    sending.current = true; setBusy(true); setError(null);
    try { await api.saveAdjustment(teamId, memberId, snapshot, { goals: Number(values.goals), yellow_cards: Number(values.yellow_cards), red_cards: Number(values.red_cards) }); onSaved(); }
    catch (cause) { setError(cause instanceof Error ? cause.message : 'Não foi possível salvar.'); setConfirm(false); }
    finally { sending.current = false; setBusy(false); }
  }
  return <View style={s.stack}>
    <Text accessibilityRole="header" style={s.heading}>Editar estatísticas</Text>
    <Text style={s.label}>{name}</Text>
    <Text style={s.note}>Ajustes valem somente no total histórico. Filtros por período e modalidade continuam usando apenas partidas. O histórico das partidas será preservado.</Text>
    <FormError message={error} />
    {!snapshot ? error ? <Button label="Tentar novamente" onPress={() => setRevision(value => value + 1)} /> : <LoadingState /> : <>
      {snapshot.floor_applied && <Text style={s.note}>Uma correção de partida reduziu a base de um ajuste negativo. O total mínimo exibido é zero. Confira os valores.</Text>}
      {fields.map(([key, label]) => <View key={key} style={s.stack}>
        <Field label={label} value={values[key]} keyboardType="number-pad" maxLength={6} editable={!busy && !confirm} onChangeText={value => setValues(current => ({ ...current, [key]: value }))} />
        <View style={s.row}>
          <IconButton icon="remove-outline" label={`Diminuir ${label}`} disabled={busy || confirm || !valid || Number(values[key]) === 0} onPress={() => setValues(current => ({ ...current, [key]: String(Number(current[key]) - 1) }))} />
          <IconButton icon="add-outline" label={`Aumentar ${label}`} disabled={busy || confirm || !valid || Number(values[key]) >= 999999} onPress={() => setValues(current => ({ ...current, [key]: String(Number(current[key]) + 1) }))} />
        </View>
        <Text style={s.note}>Partidas: {snapshot.base[key]} · Ajuste atual: {snapshot.adjustments[key] >= 0 ? '+' : ''}{snapshot.adjustments[key]}</Text>
      </View>)}
      {confirm ? <>
        <Text style={s.note}>Confirmar os novos totais: {values.goals} gols, {values.yellow_cards} amarelos e {values.red_cards} vermelhos? A alteração ficará registrada com seu usuário.</Text>
        <Button label={busy ? 'Salvando…' : 'Confirmar ajuste'} disabled={busy} onPress={() => void save()} />
        <TextAction label="Revisar valores" disabled={busy} onPress={() => setConfirm(false)} />
      </> : <Button label="Salvar estatísticas" disabled={!valid || busy} onPress={() => setConfirm(true)} />}
      {error && <TextAction label="Atualizar estatísticas" disabled={busy} onPress={() => setRevision(value => value + 1)} />}
    </>}
    <TextAction label="Cancelar" disabled={busy} onPress={onCancel} />
  </View>;
}
