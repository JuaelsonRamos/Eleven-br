import { FixtureHeading } from './FixtureHeading';
import { FixtureActions } from './FixtureActions';
import { fixtureStatus } from './api';
import { useCallback, useEffect, useRef, useState } from 'react';
import { Text, View } from 'react-native';
import { Field, FormError, TextAction } from '../components/AuthLayout';
import { Button, Card, LoadingState, StatusBadge } from '../components/ui';
import { styles } from '../events/styles';
import { getFixture, message, resultLabels, scoreLine, sendReview, submitScore, when, type FixtureDetail, type Review, type ScoreInput } from './api';
import { fixtureTitle, resultTones } from './FixtureList';
import { useModalityLabel, YesNo } from './parts';

function goals(value: string): number | null {
  return /^\d{1,3}$/.test(value.trim()) ? Number(value.trim()) : null;
}
const yes = (value: boolean) => value ? 'Sim' : 'Não';
function ReviewText({ title, review }: { title: string; review: Review }) {
  return <Text style={styles.note}>{title}: compareceu {yes(review.attended)} • cumpriu o horário {yes(review.punctual)} • cumpriu o combinado {yes(review.kept_agreement)}</Text>;
}

export function FixtureView({ teamId, fixtureId, onBack, onOpenGame, onOpenTeam }: {
  teamId: string; fixtureId: string; onBack: () => void; onOpenGame: (event: string) => void; onOpenTeam: (team: string) => void;
}) {
  const label = useModalityLabel();
  const [item, setItem] = useState<FixtureDetail | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [contest, setContest] = useState(false);
  const [home, setHome] = useState('');
  const [away, setAway] = useState('');
  const [answers, setAnswers] = useState<{ attended: boolean | null; punctual: boolean | null; kept_agreement: boolean | null }>({ attended: null, punctual: null, kept_agreement: null });
  const generation = useRef(0), sending = useRef(false);
  const load = useCallback(async () => {
    const revision = ++generation.current; setError(null);
    try { const data = await getFixture(teamId, fixtureId); if (revision === generation.current) setItem(data); }
    catch (cause) { if (revision === generation.current) setError(message(cause, 'Não foi possível carregar o confronto.')); }
  }, [teamId, fixtureId]);
  useEffect(() => { const stale = generation; void load(); return () => { stale.current++; }; }, [load]);
  async function run(action: () => Promise<FixtureDetail>, done: string) {
    if (sending.current) return;
    sending.current = true; setBusy(true); setError(null); setSuccess(null);
    try { setItem(await action()); setContest(false); setSuccess(done); }
    catch (cause) { setError(message(cause, 'Não foi possível concluir.')); void load(); }
    finally { sending.current = false; setBusy(false); }
  }
  function report(action: 'score' | 'confirm', score?: ScoreInput) {
    const data = score ?? { home_score: goals(home), away_score: goals(away) };
    if (data.home_score === null || data.away_score === null) { setError('Informe os gols de cada time (0 a 999).'); return; }
    void run(() => submitScore(teamId, fixtureId, action, data as ScoreInput), action === 'confirm' ? 'Placar confirmado. Resultado validado.' : 'Placar enviado ao adversário.');
  }
  function review() {
    const { attended, punctual, kept_agreement } = answers;
    if (attended === null || punctual === null || kept_agreement === null) { setError('Responda as três perguntas da avaliação.'); return; }
    void run(() => sendReview(teamId, fixtureId, { attended, punctual, kept_agreement }), 'Avaliação enviada.');
  }
  if (!item) return <View style={styles.stack}><FormError message={error} />{error ? <Button label="Tentar novamente" onPress={() => void load()} /> : <LoadingState />}<TextAction label="Voltar" onPress={onBack} /></View>;
  const theirs = item.scores.theirs, mine = item.scores.mine;
  return <View style={styles.stack}>
    <Text accessibilityRole="header" style={styles.title}>{fixtureTitle(item)}</Text>
    <FixtureHeading item={item} />
    {item.status !== 'SCHEDULED' && <StatusBadge label={fixtureStatus[item.status]} tone="warning" />}
    <StatusBadge label={resultLabels[item.result_status]} tone={resultTones[item.result_status]} />
    <Card><View style={styles.stack}>
      <Text style={styles.heading}>{when(item.date, item.time)}</Text>
      <Text style={styles.text}>{item.location}</Text>
      <Text style={styles.note}>{label(item.modality)} • Mandante: {item.home_team.name} • {item.side === 'HOME' ? 'Seu time joga em casa' : 'Seu time joga fora'}</Text>
      {item.notes && <Text style={styles.note}>{item.notes}</Text>}
      {item.event_id && <Button variant="secondary" label="Ver em Jogos" onPress={() => onOpenGame(item.event_id!)} />}
      <TextAction label={`Ver perfil de ${item.opponent.name}`} onPress={() => onOpenTeam(item.opponent.id)} />
    </View></Card>
    <FormError message={error} />
    {success && <Text accessibilityLiveRegion="polite" style={styles.success}>{success}</Text>}
    <FixtureActions teamId={teamId} item={item} busy={busy} run={run} />
    <Text accessibilityRole="header" style={styles.heading}>Placar</Text>
    {item.result_status === 'NONE' && <Text style={styles.note}>{item.started ? 'Nenhum placar informado ainda.' : 'O placar pode ser informado a partir do horário do jogo.'}</Text>}
    {mine && <Text style={styles.text}>Informado pelo seu time: {scoreLine(item, mine)}</Text>}
    {theirs && <Text style={styles.text}>Informado pelo adversário: {scoreLine(item, theirs)}</Text>}
    {item.result_status === 'PENDING' && <Text style={styles.note}>Aguardando confirmação: ainda não é resultado oficial. O silêncio não confirma o placar.</Text>}
    {item.result_status === 'DISPUTED' && <Text style={styles.note}>Os placares informados são diferentes. Resultado em divergência não é oficial e não há resolução automática.</Text>}
    {item.result_status === 'VALIDATED' && <Text style={styles.note}>Resultado confirmado pelos dois times. Não pode ser alterado.</Text>}
    {item.can_confirm && theirs && !contest && <>
      <Button label={`Confirmar placar ${theirs.home_score} x ${theirs.away_score}`} disabled={busy} onPress={() => report('confirm', { home_score: theirs.home_score, away_score: theirs.away_score })} />
      <TextAction label="Contestar placar" disabled={busy} onPress={() => { setContest(true); setSuccess(null); }} />
    </>}
    {item.can_report && (!item.can_confirm || contest) && <>
      <Text style={styles.note}>{contest ? 'Informe o placar correto. O resultado ficará em divergência e não será oficial.' : 'Informe o placar final. O adversário confirma ou contesta.'}</Text>
      <Field label={`Gols de ${item.home_team.name}`} value={home} onChangeText={setHome} keyboardType="number-pad" maxLength={3} editable={!busy} />
      <Field label={`Gols de ${item.away_team.name}`} value={away} onChangeText={setAway} keyboardType="number-pad" maxLength={3} editable={!busy} />
      <Button label={busy ? 'Enviando…' : contest ? 'Enviar placar contestado' : 'Informar placar'} disabled={busy} onPress={() => report('score')} />
      {contest && <TextAction label="Voltar" disabled={busy} onPress={() => setContest(false)} />}
    </>}
    {!item.can_manage && item.result_status !== 'VALIDATED' && <Text style={styles.note}>Somente o Presidente e administradores com a área Jogos, peladas e escalações informam e confirmam o placar.</Text>}
    <Text accessibilityRole="header" style={styles.heading}>Avaliação de confiabilidade</Text>
    {item.result_status !== 'VALIDATED' && <Text style={styles.note}>A avaliação é liberada depois do resultado validado pelos dois times.</Text>}
    {item.can_review && <StatusBadge label="AVALIAÇÃO DISPONÍVEL" tone="info" />}
    {item.reviews.mine && <StatusBadge label="AVALIAÇÃO CONCLUÍDA" tone="success" />}
    {item.reviews.mine && <ReviewText title="Avaliação do seu time" review={item.reviews.mine} />}
    {item.reviews.theirs && <ReviewText title="Avaliação recebida do adversário" review={item.reviews.theirs} />}
    {item.can_review && <>
      <YesNo label="Compareceu ao jogo?" value={answers.attended} disabled={busy} onChange={value => setAnswers(previous => ({ ...previous, attended: value }))} />
      <YesNo label="Cumpriu o horário combinado?" value={answers.punctual} disabled={busy} onChange={value => setAnswers(previous => ({ ...previous, punctual: value }))} />
      <YesNo label="Cumpriu o que foi combinado?" value={answers.kept_agreement} disabled={busy} onChange={value => setAnswers(previous => ({ ...previous, kept_agreement: value }))} />
      <Text style={styles.note}>A avaliação é sobre confiabilidade, não sobre o resultado. Cada time avalia uma vez por confronto.</Text>
      <Button label={busy ? 'Enviando…' : 'Enviar avaliação'} disabled={busy} onPress={review} />
    </>}
    <TextAction label="Voltar aos adversários" disabled={busy} onPress={onBack} />
  </View>;
}
