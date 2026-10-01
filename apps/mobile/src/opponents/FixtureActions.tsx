import { useRef, useState } from 'react';
import { Text, View } from 'react-native';
import { Field, FormError, TextAction } from '../components/AuthLayout';
import { Button, Card } from '../components/ui';
import { isoDate } from '../events/EventForm';
import { styles } from '../events/styles';
import { decideChange, proposeChange, when, type FixtureDetail, type ProposalInput } from './api';

export function FixtureActions({ teamId, item, busy, run }: { teamId: string; item: FixtureDetail; busy: boolean; run: (action: () => Promise<FixtureDetail>, done: string) => Promise<void> }) {
  const [kind, setKind] = useState<ProposalInput['kind'] | null>(null);
  const [day, setDay] = useState(''), [hour, setHour] = useState(''), [location, setLocation] = useState(''), [reason, setReason] = useState('');
  const [error, setError] = useState<string | null>(null);
  const command = useRef(item.command_id);
  const pending = item.proposals.find(p => p.status === 'PENDING');
  function start(value: ProposalInput['kind']) {
    command.current = item.command_id; setKind(value); setError(null); setReason('');
    setDay(item.date.split('-').reverse().join('/')); setHour(item.time.slice(0, 5)); setLocation(item.location);
  }
  function send() {
    if (!kind) return;
    const data: ProposalInput = { command_id: command.current, expected_version: item.version, kind, reason: reason.trim() || null, confirm: kind === 'WITHDRAW' };
    if (kind === 'CHANGE') {
      const date = isoDate(day);
      if (!date || !/^([01]\d|2[0-3]):[0-5]\d$/.test(hour) || !location.trim()) { setError('Informe data, horário e local válidos.'); return; }
      Object.assign(data, { date, time: hour, location: location.trim() });
    }
    void run(async () => { const saved = await proposeChange(teamId, item.id, data); setKind(null); return saved; }, kind === 'WITHDRAW' ? 'Desistência registrada. Os envolvidos foram avisados.' : 'Proposta enviada ao adversário.');
  }
  return <View style={styles.stack}>
    {item.can_change && <>
      {pending ? <Text style={styles.note}>Existe uma proposta aguardando decisão do adversário.</Text> : <>
        <Button variant="secondary" label="Propor alteração" disabled={busy} onPress={() => start('CHANGE')} />
        <TextAction label="Solicitar cancelamento" disabled={busy} onPress={() => start('CANCEL')} />
      </>}
      <TextAction label="Desistir do confronto" disabled={busy} onPress={() => start('WITHDRAW')} />
      {kind && <Card><View style={styles.stack}>
        <Text style={styles.heading}>{kind === 'CHANGE' ? 'Proposta de alteração' : kind === 'CANCEL' ? 'Solicitar cancelamento por acordo' : 'Confirmar desistência?'}</Text>
        <Text style={styles.note}>{kind === 'WITHDRAW' ? 'A desistência é definitiva. O confronto e seu histórico serão preservados. Os dois times serão avisados.' : 'Os dados atuais permanecem até o adversário aceitar.'}</Text>
        {kind === 'CHANGE' && <><Field mask="date" label="Nova data (DD/MM/AAAA)" value={day} onChangeText={setDay} maxLength={10} editable={!busy} /><Field mask="time" label="Novo horário (HH:MM)" value={hour} onChangeText={setHour} maxLength={5} editable={!busy} /><Field label="Novo local" value={location} onChangeText={setLocation} maxLength={200} editable={!busy} /></>}
        <Field label="Motivo (opcional)" value={reason} onChangeText={setReason} maxLength={500} editable={!busy} />
        <FormError message={error} />
        <Button label={kind === 'WITHDRAW' ? 'Confirmar desistência' : 'Enviar proposta'} disabled={busy} onPress={send} />
        <TextAction label="Voltar sem enviar" disabled={busy} onPress={() => setKind(null)} />
      </View></Card>}
    </>}
    {!!item.proposals.length && <Text style={styles.heading}>Histórico do confronto</Text>}
    {item.proposals.map(p => <Card key={p.id}><View style={styles.stack}>
      <Text style={styles.heading}>{p.kind === 'CHANGE' ? 'Alteração' : p.kind === 'CANCEL' ? 'Cancelamento por acordo' : 'Desistência'} • {p.team_id === teamId ? 'Seu time' : 'Adversário'}</Text>
      <Text style={styles.note}>{({ PENDING: 'Pendente', ACCEPTED: 'Efetivada', REJECTED: 'Recusada', SUPERSEDED: 'Encerrada por desistência' })[p.status]} • {new Date(p.created_at).toLocaleString('pt-BR')}</Text>
      <Text style={styles.text}>{when(p.before.date, p.before.time)} • {p.before.location}</Text>
      {p.kind === 'CHANGE' && <Text style={styles.text}>Proposta: {when(p.proposed.date!, p.proposed.time!)} • {p.proposed.location}</Text>}
      {p.reason && <Text style={styles.note}>{p.reason}</Text>}
      {item.can_change && p.status === 'PENDING' && p.team_id !== teamId && <>
        <Button label={p.kind === 'CANCEL' ? 'Aceitar cancelamento' : 'Aceitar alteração'} disabled={busy} onPress={() => void run(() => decideChange(teamId, item.id, p.id, 'ACCEPTED'), 'Proposta aceita.')} />
        <TextAction label={p.kind === 'CANCEL' ? 'Manter confronto' : 'Recusar alteração'} disabled={busy} onPress={() => void run(() => decideChange(teamId, item.id, p.id, 'REJECTED'), 'Proposta recusada.')} />
      </>}
    </View></Card>)}
  </View>;
}
