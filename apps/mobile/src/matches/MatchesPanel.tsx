import { useCallback, useEffect, useRef, useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { ApiError } from '../auth/api';
import { FormError, TextAction } from '../components/AuthLayout';
import { Badge, Button, LoadingState } from '../components/ui';
import { styles } from '../events/styles';
import type { SportEvent } from '../events/api';
import { getFormation, type Formation } from '../formations/api';
import { theme } from '../theme';
import { changeMatch, createMatch, getMatches, type Match } from './api';

const labels = { SCHEDULED: 'AGENDADA', IN_PROGRESS: 'EM ANDAMENTO', FINISHED: 'FINALIZADA', CANCELLED: 'CANCELADA' };
type Confirmation = { match: Match; action: 'finish' | 'cancel' | 'score'; home: number; away: number };

export function MatchesPanel({ teamId, event }: { teamId: string; event: SportEvent }) {
  const [items, setItems] = useState<Match[]>([]);
  const [formation, setFormation] = useState<Formation | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [blocked, setBlocked] = useState(false);
  const [creating, setCreating] = useState(false);
  const [home, setHome] = useState('');
  const [away, setAway] = useState('');
  const [confirmation, setConfirmation] = useState<Confirmation | null>(null);
  const sending = useRef(false);
  const generation = useRef(0);
  const load = useCallback(async () => {
    const revision = ++generation.current; setLoading(true); setError(null); setConfirmation(null); setCreating(false);
    try {
      const [matches, page] = await Promise.all([getMatches(teamId, event.id), getFormation(teamId, event.id)]);
      if (revision !== generation.current) return;
      setItems(matches); setFormation(page.formation); setBlocked(false);
      setHome(page.formation?.squads[0]?.id ?? ''); setAway(page.formation?.squads[1]?.id ?? '');
    } catch (cause) { if (revision === generation.current) { setBlocked(true); setError(cause instanceof Error ? cause.message : 'Não foi possível carregar as partidas.'); } }
    finally { if (revision === generation.current) setLoading(false); }
  }, [teamId, event.id]);
  useEffect(() => { const counter = generation; void load(); return () => { counter.current++; }; }, [load]);
  async function run(action: () => Promise<Match>) {
    if (sending.current || blocked) return;
    const revision = generation.current; sending.current = true; setBusy(true); setError(null);
    try {
      const result = await action(); if (revision !== generation.current) return;
      setItems(old => old.some(m => m.id === result.id) ? old.map(m => m.id === result.id ? result : m) : [...old, result]);
      setCreating(false); setConfirmation(null);
    } catch (cause) {
      if (revision !== generation.current) return;
      setError(cause instanceof Error ? cause.message : 'Não foi possível salvar a partida.');
      if (cause instanceof ApiError && [403, 404, 409].includes(cause.status)) { setBlocked(true); setConfirmation(null); }
    } finally { sending.current = false; if (revision === generation.current) setBusy(false); }
  }
  const name = (id: string) => formation?.squads.find(s => s.id === id)?.name ?? 'Equipe';
  const canManage = event.can_manage && event.status === 'open' && !blocked;
  const disabled = busy || !!confirmation;
  return <View style={styles.stack}>
    <Text accessibilityRole="header" style={styles.heading}>Partidas</Text>
    <FormError message={error} />
    {loading ? <LoadingState /> : blocked ? <Button label="Recarregar partidas" disabled={busy} onPress={() => void load()} /> : <>
      {!formation && <Text style={styles.note}>Monte os times da pelada para criar uma partida.</Text>}
      {formation && !items.length && <Text style={styles.note}>Nenhuma partida registrada nesta pelada.</Text>}
      {items.map((match, index) => <View key={match.id} testID={`match-${index + 1}`} style={visual.match}>
        <Text style={styles.note}>Partida {index + 1}</Text><Badge label={labels[match.status]} />
        <View style={visual.scoreboard}>
          {(['home', 'away'] as const).map(side => {
            const score = side === 'home' ? match.home_score : match.away_score;
            const label = name(side === 'home' ? match.home_formation_team_id : match.away_formation_team_id);
            return <View key={side} style={visual.side}><Text style={visual.name}>{label}</Text>
              <Text accessibilityLabel={`Placar ${label}: ${score}`} style={visual.score}>{score}</Text>
              {canManage && match.status === 'IN_PROGRESS' && <View style={visual.controls}>
                {([-1, 1] as const).map(delta => <Pressable key={delta} accessibilityRole="button" accessibilityLabel={`${delta > 0 ? 'Aumentar' : 'Diminuir'} placar ${label}`}
                  disabled={disabled || score + delta < 0 || score + delta > 999} accessibilityState={{ disabled: disabled || score + delta < 0 || score + delta > 999 }}
                  style={[visual.step, (disabled || score + delta < 0 || score + delta > 999) && visual.disabled]}
                  onPress={() => void run(() => changeMatch(teamId, event.id, match, 'score', false, side === 'home' ? score + delta : match.home_score, side === 'away' ? score + delta : match.away_score))}>
                  <Text style={visual.stepText}>{delta > 0 ? '+' : '−'}</Text></Pressable>)}
              </View>}
            </View>;
          })}
        </View>
        {match.corrected_at && <Text style={styles.note}>Resultado corrigido em {new Date(match.corrected_at).toLocaleString('pt-BR')}.</Text>}
        {canManage && <>
          {match.status === 'SCHEDULED' && <Button label="Iniciar partida" disabled={disabled} onPress={() => void run(() => changeMatch(teamId, event.id, match, 'start'))} />}
          {match.status === 'IN_PROGRESS' && <Button label="Finalizar partida" disabled={disabled} onPress={() => setConfirmation({ match, action: 'finish', home: match.home_score, away: match.away_score })} />}
          {match.status === 'FINISHED' && <Button label="Corrigir resultado" disabled={disabled} onPress={() => setConfirmation({ match, action: 'score', home: match.home_score, away: match.away_score })} />}
          {match.status !== 'CANCELLED' && <TextAction label="Cancelar partida" disabled={disabled} onPress={() => setConfirmation({ match, action: 'cancel', home: match.home_score, away: match.away_score })} />}
        </>}
        {confirmation?.match.id === match.id && <View style={styles.stack}>
          <Text accessibilityRole="alert" style={styles.heading}>{confirmation.action === 'score' ? 'Corrigir resultado?' : confirmation.action === 'finish' ? 'Finalizar partida?' : 'Cancelar partida?'}</Text>
          <Text style={styles.text}>{name(match.home_formation_team_id)} {confirmation.home} × {confirmation.away} {name(match.away_formation_team_id)}</Text>
          {confirmation.action === 'score' && (['home', 'away'] as const).map(side => <View key={side} style={styles.row}>
            <Text style={styles.text}>{name(side === 'home' ? match.home_formation_team_id : match.away_formation_team_id)}</Text>
            {([-1, 1] as const).map(delta => <Pressable key={delta} accessibilityRole="button" accessibilityLabel={`${delta > 0 ? 'Aumentar' : 'Diminuir'} correção ${side === 'home' ? 'Time A' : 'Time B'}`}
              disabled={busy || confirmation[side] + delta < 0 || confirmation[side] + delta > 999} style={visual.step}
              onPress={() => setConfirmation(old => old && ({ ...old, [side]: old[side] + delta }))}><Text style={visual.stepText}>{delta > 0 ? '+' : '−'}</Text></Pressable>)}
          </View>)}
          <Button label={confirmation.action === 'score' ? 'Confirmar correção' : confirmation.action === 'finish' ? 'Confirmar finalização' : 'Confirmar cancelamento da partida'} disabled={busy}
            onPress={() => void run(() => changeMatch(teamId, event.id, match, confirmation.action, true, confirmation.home, confirmation.away))} />
          <TextAction label="Voltar sem alterar" disabled={busy} onPress={() => setConfirmation(null)} />
        </View>}
      </View>)}
      {canManage && formation && !creating && <Button label="Nova partida" disabled={disabled} onPress={() => setCreating(true)} />}
      {canManage && formation && creating && <View style={styles.stack}>
        {(['A', 'B'] as const).map(side => <View key={side} style={styles.stack}><Text style={styles.heading}>Time {side}</Text><View style={styles.row}>
          {formation.squads.map(squad => <Pressable key={squad.id} accessibilityRole="radio" accessibilityLabel={`Time ${side}: ${squad.name}`} accessibilityState={{ checked: (side === 'A' ? home : away) === squad.id, disabled: busy || (side === 'B' && squad.id === home) }}
            disabled={busy || (side === 'B' && squad.id === home)} style={[styles.chip, (side === 'A' ? home : away) === squad.id && styles.selected, side === 'B' && squad.id === home && visual.disabled]}
            onPress={() => { if (side === 'A') { setHome(squad.id); if (away === squad.id) setAway(''); } else setAway(squad.id); }}><Text style={styles.text}>{squad.name}</Text></Pressable>)}
        </View></View>)}
        <Button label="Criar partida" disabled={busy || !home || !away || home === away} onPress={() => void run(() => createMatch(teamId, event.id, formation.id, formation.version, home, away))} />
        <TextAction label="Voltar sem criar" disabled={busy} onPress={() => setCreating(false)} />
      </View>}
      <TextAction label="Atualizar partidas" disabled={disabled} onPress={() => void load()} />
    </>}
  </View>;
}
const visual = StyleSheet.create({
  match: { borderTopWidth: 1, borderColor: theme.colors.border, paddingVertical: 20, gap: 14 },
  scoreboard: { flexDirection: 'row', gap: 12, maxWidth: 500, width: '100%', alignSelf: 'center' },
  side: { flex: 1, alignItems: 'center', gap: 8 },
  name: { color: theme.colors.graphite, fontSize: 18, fontWeight: '700' },
  score: { color: theme.colors.green, fontSize: 48, fontWeight: '800' },
  controls: { flexDirection: 'row', gap: 8 },
  step: { minWidth: 48, minHeight: 48, borderRadius: 12, backgroundColor: theme.colors.lightGreen, alignItems: 'center', justifyContent: 'center' },
  stepText: { color: theme.colors.green, fontSize: 26, fontWeight: '700' },
  disabled: { opacity: 0.4 },
});
