import { useCallback, useEffect, useRef, useState } from 'react';
import { Text, View } from 'react-native';
import { FormError, TextAction } from '../components/AuthLayout';
import { Badge, Button, Card, EmptyState, LoadingState } from '../components/ui';
import { styles } from '../events/styles';
import { challengeLabels, decide, listChallenges, message, when, type Challenge } from './api';
import { TeamLine, useModalityLabel } from './parts';

const tones = { PENDING: 'warning', ACCEPTED: 'success', REJECTED: 'neutral', CANCELLED: 'neutral', EXPIRED: 'neutral' } as const;

export function ChallengeList({ teamId, direction, onOpenTeam, onOpenFixture, onChanged }: {
  teamId: string; direction: 'received' | 'sent'; onOpenTeam: (team: string) => void; onOpenFixture: (fixture: string) => void; onChanged: () => Promise<void>;
}) {
  const label = useModalityLabel();
  const [items, setItems] = useState<Challenge[] | null>(null);
  const [more, setMore] = useState(false);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [confirm, setConfirm] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const generation = useRef(0), sending = useRef(false);
  const load = useCallback(async (offset = 0) => {
    const revision = ++generation.current; setLoading(true); setError(null);
    try {
      const page = await listChallenges(teamId, direction, offset);
      if (revision !== generation.current) return;
      setItems(previous => offset && previous ? [...previous, ...page.items] : page.items); setMore(page.has_more);
    } catch (cause) { if (revision === generation.current) setError(message(cause, 'Não foi possível carregar os desafios.')); }
    finally { if (revision === generation.current) setLoading(false); }
  }, [teamId, direction]);
  useEffect(() => { const stale = generation; void load(); return () => { stale.current++; }; }, [load]);
  async function act(item: Challenge, decision: 'accept' | 'reject' | 'cancel') {
    if (sending.current) return;
    sending.current = true; setBusy(true); setError(null); setSuccess(null);
    try {
      const updated = await decide(teamId, item.id, decision);
      setItems(previous => previous?.map(row => row.id === updated.id ? updated : row) ?? null);
      setConfirm(null);
      setSuccess(decision === 'accept' ? 'Desafio aceito. O confronto já está em Jogos para os dois times.' : decision === 'reject' ? 'Desafio recusado.' : 'Desafio cancelado.');
      await onChanged();
    } catch (cause) { setError(message(cause, 'Não foi possível concluir.')); void load(); }
    finally { sending.current = false; setBusy(false); }
  }
  if (loading && !items) return <LoadingState />;
  return <View style={styles.stack}>
    <FormError message={error} />
    {success && <Text accessibilityLiveRegion="polite" style={styles.success}>{success}</Text>}
    {items && !items.length && <EmptyState title={direction === 'received' ? 'Nenhum desafio recebido' : 'Nenhum desafio enviado'} description={direction === 'received' ? 'Quando outro time desafiar o seu, o convite aparece aqui.' : 'Busque um adversário e envie um desafio pelo perfil do time.'} icon="shield-half-outline" />}
    {items?.map(item => <Card key={item.id}><View style={styles.stack}>
      <Badge label={challengeLabels[item.status]} tone={tones[item.status]} />
      <TeamLine team={item.opponent} />
      <Text style={styles.text}>{when(item.date, item.time)} • {label(item.modality)}</Text>
      <Text style={styles.note}>{item.location} • {item.venue === 'HOME' ? 'Seu time joga em casa' : 'Seu time joga fora'}</Text>
      {item.notes && <Text style={styles.note}>{item.notes}</Text>}
      {item.status === 'EXPIRED' && <Text style={styles.note}>O horário proposto passou sem resposta.</Text>}
      {item.can_respond && (confirm === item.id ? <>
        <Text style={styles.text}>Recusar este desafio? Para outra data ou local, o outro time pode enviar um novo desafio.</Text>
        <Button variant="secondary" label="Confirmar recusa" disabled={busy} onPress={() => void act(item, 'reject')} />
        <TextAction label="Voltar" disabled={busy} onPress={() => setConfirm(null)} />
      </> : <>
        <Button label="Aceitar desafio" disabled={busy} onPress={() => void act(item, 'accept')} />
        <TextAction label="Recusar" disabled={busy} onPress={() => setConfirm(item.id)} />
      </>)}
      {item.can_cancel && (confirm === item.id ? <>
        <Text style={styles.text}>Cancelar este desafio? O outro time será avisado.</Text>
        <Button variant="secondary" label="Confirmar cancelamento" disabled={busy} onPress={() => void act(item, 'cancel')} />
        <TextAction label="Manter desafio" disabled={busy} onPress={() => setConfirm(null)} />
      </> : <TextAction label="Cancelar desafio" disabled={busy} onPress={() => setConfirm(item.id)} />)}
      {item.fixture_id && <Button variant="secondary" label="Ver confronto" disabled={busy} onPress={() => onOpenFixture(item.fixture_id!)} />}
      <TextAction label={`Ver perfil de ${item.opponent.name}`} disabled={busy} onPress={() => onOpenTeam(item.opponent.id)} />
    </View></Card>)}
    {more && <Button variant="secondary" label={loading ? 'Carregando…' : 'Carregar mais'} disabled={loading || busy} onPress={() => void load(items?.length ?? 0)} />}
  </View>;
}
