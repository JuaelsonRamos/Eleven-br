import { useCallback, useEffect, useRef, useState } from 'react';
import { Text, View } from 'react-native';
import { Field, FormError, TextAction } from '../components/AuthLayout';
import { Badge, Button, Card, FilterChip, LoadingState, StatusBadge } from '../components/ui';
import { isoDate } from '../events/EventForm';
import { styles } from '../events/styles';
import { challengeLabels, getProfile, message, resultLabels, sendChallenge, when, type Profile } from './api';
import { fixtureTitle, resultTones } from './FixtureList';
import { ReliabilityInfo, TeamLine, useModalityLabel } from './parts';

export function ProfileView({ teamId, otherId, onBack, onOpenFixture, onSent, onPro }: {
  teamId: string; otherId: string; onBack: () => void; onOpenFixture: (fixture: string) => void; onSent: () => Promise<void>; onPro: () => void;
}) {
  const label = useModalityLabel();
  const [profile, setProfile] = useState<Profile | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [modality, setModality] = useState('');
  const [date, setDate] = useState('');
  const [time, setTime] = useState('');
  const [location, setLocation] = useState('');
  const [venue, setVenue] = useState<'HOME' | 'AWAY'>('HOME');
  const [notes, setNotes] = useState('');
  const generation = useRef(0), sending = useRef(false);
  const load = useCallback(async () => {
    const revision = ++generation.current; setError(null);
    try {
      const data = await getProfile(teamId, otherId);
      if (revision !== generation.current) return;
      setProfile(data); setModality(previous => data.compatible_modalities.includes(previous) ? previous : data.compatible_modalities[0] ?? '');
    } catch (cause) { if (revision === generation.current) setError(message(cause, 'Não foi possível carregar o adversário.')); }
  }, [teamId, otherId]);
  useEffect(() => { const stale = generation; void load(); return () => { stale.current++; }; }, [load]);
  async function challenge() {
    if (sending.current || !profile) return;
    const day = isoDate(date.trim());
    if (!day) { setError('Informe uma data válida (DD/MM/AAAA).'); return; }
    if (!/^([01]\d|2[0-3]):[0-5]\d$/.test(time.trim())) { setError('Informe um horário válido (HH:MM).'); return; }
    if (!location.trim()) { setError('Informe o local do jogo.'); return; }
    sending.current = true; setBusy(true); setError(null); setSuccess(null);
    try {
      await sendChallenge(teamId, { command_id: profile.command_id, opponent_team_id: profile.team.id, modality, date: day, time: time.trim(), location: location.trim(), venue, notes: notes.trim() || null });
      setDate(''); setTime(''); setLocation(''); setNotes('');
      setSuccess('Desafio enviado. O adversário foi avisado e responde em Adversários.');
      await Promise.all([load(), onSent()]);
    } catch (cause) { setError(message(cause, 'Não foi possível enviar o desafio.')); }
    finally { sending.current = false; setBusy(false); }
  }
  if (!profile) return <View style={styles.stack}><FormError message={error} />{error ? <Button label="Tentar novamente" onPress={() => void load()} /> : <LoadingState />}<TextAction label="Voltar" onPress={onBack} /></View>;
  const { history } = profile;
  return <View style={styles.stack}>
    <Card><View style={styles.stack}>
      <TeamLine team={profile.team} />
      <Text style={styles.note}>ID público: {profile.team.code}</Text>
      <Text accessibilityRole="header" style={styles.heading}>Confiabilidade</Text>
      <ReliabilityInfo data={profile.reliability} />
    </View></Card>
    <FormError message={error} />
    {success && <Text accessibilityLiveRegion="polite" style={styles.success}>{success}</Text>}
    {!profile.accepts_challenges && <Text style={styles.note}>Este time não está aceitando desafios no momento.</Text>}
    {profile.accepts_challenges && !profile.compatible_modalities.length && <Text style={styles.note}>Os dois times não têm modalidade em comum.</Text>}
    {profile.pending_challenge && <Badge label="Há desafio pendente entre os times" tone="warning" />}
    {profile.credits.remaining === 0 && <>
      <Text style={styles.note}>O desafio gratuito deste mês já foi usado. No ELEVEN BR PRO os desafios são ilimitados.</Text>
      <Button variant="secondary" label="CONHECER O ELEVEN BR PRO" onPress={onPro} />
    </>}
    {profile.can_challenge && <Card><View style={styles.stack}>
      <Text accessibilityRole="header" style={styles.heading}>Enviar desafio</Text>
      <View accessibilityRole="radiogroup" accessibilityLabel="Modalidade do desafio" style={styles.row}>
        {profile.compatible_modalities.map(value => <FilterChip key={value} role="radio" label={label(value)} selected={modality === value} disabled={busy} onPress={() => setModality(value)} />)}
      </View>
      <Field mask="date" label="Data (DD/MM/AAAA)" value={date} onChangeText={setDate} placeholder="10/10/2026" maxLength={10} editable={!busy} />
      <Field mask="time" label="Horário (HH:MM)" value={time} onChangeText={setTime} placeholder="16:00" maxLength={5} editable={!busy} />
      <Field label="Local" value={location} onChangeText={setLocation} maxLength={200} editable={!busy} />
      <Text style={styles.text}>Mando</Text>
      <View accessibilityRole="radiogroup" accessibilityLabel="Mando" style={styles.row}>
        {(['HOME', 'AWAY'] as const).map(value => <FilterChip key={value} role="radio" label={value === 'HOME' ? 'Em casa' : 'Fora'} selected={venue === value} disabled={busy} onPress={() => setVenue(value)} />)}
      </View>
      <Field label="Observação (opcional)" value={notes} onChangeText={setNotes} maxLength={500} multiline editable={!busy} />
      <Text style={styles.note}>Use a data e o horário locais do jogo. Se o adversário aceitar, o confronto aparece em Jogos dos dois times; data, horário e local não mudam depois.</Text>
      {profile.credits.limit !== null && <Text style={styles.note}>Plano Free: este envio usa o desafio gratuito do mês. Receber e responder desafios é livre.</Text>}
      <Button label={busy ? 'Enviando…' : 'Enviar desafio'} disabled={busy} onPress={() => void challenge()} />
    </View></Card>}
    <Text accessibilityRole="header" style={styles.heading}>Histórico entre os times</Text>
    {!history.challenges.length && !history.fixtures.length && <Text style={styles.note}>Ainda não há desafios nem confrontos entre os times.</Text>}
    {history.fixtures.map(item => <View key={item.id} style={{ gap: 6 }}>
      <Text style={styles.text}>{fixtureTitle(item)} • {when(item.date, item.time)}</Text>
      <StatusBadge label={resultLabels[item.result_status]} tone={resultTones[item.result_status]} />
      {item.reviews.theirs && <Text style={styles.note}>Avaliação do adversário sobre seu time: compareceu {item.reviews.theirs.attended ? 'Sim' : 'Não'} • horário {item.reviews.theirs.punctual ? 'Sim' : 'Não'} • combinado {item.reviews.theirs.kept_agreement ? 'Sim' : 'Não'}</Text>}
      {item.reviews.mine && <Text style={styles.note}>Avaliação do seu time: compareceu {item.reviews.mine.attended ? 'Sim' : 'Não'} • horário {item.reviews.mine.punctual ? 'Sim' : 'Não'} • combinado {item.reviews.mine.kept_agreement ? 'Sim' : 'Não'}</Text>}
      <TextAction label="Abrir confronto" onPress={() => onOpenFixture(item.id)} />
    </View>)}
    {history.challenges.map(item => <Text key={item.id} style={styles.note}>Desafio {item.direction === 'sent' ? 'enviado' : 'recebido'} • {when(item.date, item.time)} • {challengeLabels[item.status]}</Text>)}
    <TextAction label="Voltar aos adversários" disabled={busy} onPress={onBack} />
  </View>;
}
