import { useCallback, useRef, useState } from 'react';
import { BackHandler, Pressable, Text, View } from 'react-native';
import { useFocusEffect } from '@react-navigation/native';
import { ApiError } from '../auth/api';
import { FormError, TextAction } from '../components/AuthLayout';
import { Badge, Button, Card, LoadingState } from '../components/ui';
import { eventWhen, type SportEvent } from '../events/api';
import { styles } from '../events/styles';
import type { Team } from '../teams/api';
import { candidateKey, drawFormation, getFormation, moveParticipant, type FormationPage } from './api';

type Selection = Record<string, { included: boolean; goalkeeper: boolean }>;

export function FormationPanel({ team, event, onBack, onNavigate }: { team: Team; event: SportEvent; onBack: () => void; onNavigate?: () => void }) {
  const [page, setPage] = useState<FormationPage | null>(null);
  const [selection, setSelection] = useState<Selection>({});
  const [count, setCount] = useState(2);
  const [editing, setEditing] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const [moving, setMoving] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const sending = useRef(false);
  const generation = useRef(0);
  const accept = useCallback((value: FormationPage) => {
    setPage(value); setCount(value.formation?.team_count ?? 2); setConfirm(false); setMoving(null);
    setEditing(!value.formation);
    const assigned = value.formation?.squads.flatMap(s => s.participants) ?? [];
    const excluded = value.formation?.excluded ?? [];
    setSelection(Object.fromEntries(value.participants.map(p => [candidateKey(p), {
      included: !excluded.some(e => (p.kind === 'member' ? e.membership_id : e.guest_id) === p.source_id),
      goalkeeper: assigned.some(e => (p.kind === 'member' ? e.membership_id : e.guest_id) === p.source_id && e.goalkeeper),
    }])));
  }, []);
  const load = useCallback(async () => {
    const revision = ++generation.current;
    setLoading(true); setError(null);
    try { const value = await getFormation(team.id, event.id); if (revision === generation.current) accept(value); }
    catch (cause) { if (revision === generation.current) { setPage(null); setError(cause instanceof Error ? cause.message : 'Não foi possível carregar a formação.'); } }
    finally { if (revision === generation.current) setLoading(false); }
  }, [team.id, event.id, accept]);
  useFocusEffect(useCallback(() => {
    const counter = generation; void load();
    return () => { counter.current++; };
  }, [load]));
  useFocusEffect(useCallback(() => {
    const handler = BackHandler.addEventListener('hardwareBackPress', () => {
      if (!sending.current) onBack();
      return true;
    });
    return () => handler.remove();
  }, [onBack]));

  async function run(action: () => Promise<FormationPage>, scrollToTop = false) {
    if (sending.current) return;
    const revision = generation.current;
    sending.current = true; setBusy(true); setError(null);
    try { const value = await action(); if (revision === generation.current) { accept(value); if (scrollToTop) onNavigate?.(); } }
    catch (cause) {
      if (revision !== generation.current) return;
      if (cause instanceof ApiError && cause.status === 409) {
        try { const value = await getFormation(team.id, event.id); if (revision === generation.current) accept(value); }
        catch { if (revision === generation.current) setPage(null); }
      } else if (cause instanceof ApiError && [403, 404].includes(cause.status)) setPage(null);
      if (revision === generation.current) setError(cause instanceof Error ? cause.message : 'Não foi possível salvar a formação.');
    } finally { sending.current = false; if (revision === generation.current) setBusy(false); }
  }
  const participants = page?.participants.filter(p => selection[candidateKey(p)]?.included) ?? [];
  const keepers = participants.filter(p => selection[candidateKey(p)]?.goalkeeper).length;
  const valid = participants.length >= count && count >= 2 && count <= 32 && (page?.participants.length ?? 0) <= 256;
  function draw(confirmed = false) {
    if (!page || !valid) return;
    if (page.formation && !confirmed) { setConfirm(true); return; }
    void run(() => drawFormation(team.id, event.id, { team_count: count, expected_fingerprint: page.fingerprint,
      expected_version: page.formation?.version ?? null, confirm_replace: confirmed,
      participants: participants.map(p => ({ kind: p.kind, source_id: p.source_id, goalkeeper: !!selection[candidateKey(p)]?.goalkeeper })),
    }), true);
  }
  return <View style={styles.stack}>
    <Text accessibilityRole="header" style={styles.title}>{editing ? 'Montar times' : 'Times da pelada'}</Text>
    <Text style={styles.heading}>{event.title}</Text>
    <Text style={styles.note}>{eventWhen(event)}</Text>
    <FormError message={error} />
    {loading ? <LoadingState /> : !page ? <Button label="Tentar novamente" onPress={() => void load()} /> : <>
      {page.participants_changed && <Text accessibilityRole="alert" style={styles.note}>A lista de participantes mudou desde o último sorteio.</Text>}
      {editing && page.can_manage ? <>
        <Text accessibilityRole="header" style={styles.heading}>Participantes — {participants.length}</Text>
        <Text style={styles.note}>Retirar alguém aqui não altera sua presença. Goleiro vale somente para esta formação.</Text>
        {page.participants.map(p => {
          const key = candidateKey(p), value = selection[key];
          const name = p.kind === 'guest' ? `Convidado: ${p.name}` : p.name;
          return <View key={key} style={styles.row}>
            <Pressable accessibilityRole="checkbox" accessibilityLabel={`Participa: ${name}`} accessibilityState={{ checked: !!value?.included, disabled: busy || confirm }} aria-checked={!!value?.included}
              disabled={busy || confirm} style={[styles.chip, value?.included && styles.selected]} onPress={() => setSelection(old => ({ ...old, [key]: { included: !value?.included, goalkeeper: value?.goalkeeper ?? false } }))}>
              <Text style={styles.text}>{value?.included ? '✓ ' : ''}{name}</Text>
            </Pressable>
            <Pressable accessibilityRole="checkbox" accessibilityLabel={`Goleiro: ${name}`} accessibilityState={{ checked: !!value?.goalkeeper, disabled: busy || confirm || !value?.included }} aria-checked={!!value?.goalkeeper}
              disabled={busy || confirm || !value?.included} style={[styles.chip, value?.goalkeeper && styles.selected]} onPress={() => setSelection(old => ({ ...old, [key]: { included: true, goalkeeper: !value?.goalkeeper } }))}>
              <Text style={styles.text}>{value?.goalkeeper ? '✓ ' : ''}Goleiro</Text>
            </Pressable>
          </View>;
        })}
        {!page.participants.length && <Text style={styles.note}>Nenhum confirmado ou convidado disponível. Confira as presenças da pelada.</Text>}
        <Text style={styles.heading}>Número de times: {count}</Text>
        <View style={styles.row}>
          <Button label="Menos times" disabled={busy || confirm || count <= 2} onPress={() => setCount(n => n - 1)} />
          <Button label="Mais times" disabled={busy || confirm || count >= Math.min(32, participants.length)} onPress={() => setCount(n => n + 1)} />
        </View>
        {valid ? <>
          {Array.from({ length: count }, (_, i) => <Text key={i} style={styles.note}>Time {i + 1} → {Math.floor(participants.length / count) + (i < participants.length % count ? 1 : 0)} participantes</Text>)}
          {keepers < count && <Text style={styles.note}>{count - keepers} time(s) ficará(ão) sem goleiro fixo. Você pode continuar.</Text>}
        </> : <Text accessibilityRole="alert" style={styles.note}>Selecione pelo menos um participante por time: de 2 a 32 times e até 256 participantes.</Text>}
        {confirm ? <>
          <Text accessibilityRole="alert" style={styles.text}>Já existe uma formação para esta pelada. Deseja substituir o sorteio atual?</Text>
          <Button label="Confirmar novo sorteio" disabled={busy || !valid} onPress={() => draw(true)} />
          <TextAction label="Manter sorteio atual" disabled={busy} onPress={() => { setConfirm(false); setEditing(false); }} />
        </> : <Button label={busy ? 'Sorteando…' : 'Sortear'} disabled={busy || !valid} onPress={() => draw()} />}
        {page.formation && !confirm && <TextAction label="Voltar ao resultado" disabled={busy} onPress={() => setEditing(false)} />}
      </> : page.formation ? <>
        {page.formation.squads.map(squad => <Card key={squad.id}><View style={styles.stack}>
          <Text accessibilityRole="header" style={styles.heading}>{squad.name} — {squad.participants.length}</Text>
          {!squad.participants.some(p => p.goalkeeper) && <Text style={styles.note}>Sem goleiro fixo</Text>}
          {squad.participants.map(p => <View key={p.id} style={styles.stack}>
            <Text style={styles.text}>{p.name}{p.guest_id ? ' • Convidado' : ''}</Text>
            {p.goalkeeper && <Badge label="🧤 Goleiro" />}
            {page.can_manage && <TextAction label={`Mover ${p.name}`} disabled={busy} onPress={() => setMoving(moving === p.id ? null : p.id)} />}
            {page.can_manage && moving === p.id && page.formation && <View style={styles.stack}>
              <Text style={styles.note}>Mover para:</Text>
              {page.formation.squads.map(target => <Button key={target.id} label={`Mover para ${target.name}`} disabled={busy || target.id === squad.id}
                onPress={() => void run(() => moveParticipant(team.id, event.id, page.formation!, p.id, target.id))} />)}
            </View>}
          </View>)}
        </View></Card>)}
        {!!page.formation.excluded.length && <Text style={styles.note}>Fora desta formação: {page.formation.excluded.map(p => p.name).join(', ')}.</Text>}
        {page.can_manage && <Button label="Sortear novamente" disabled={busy} onPress={() => { setEditing(true); setConfirm(false); setMoving(null); onNavigate?.(); }} />}
      </> : <Text style={styles.note}>A gestão ainda não montou os times desta pelada.</Text>}
      <TextAction label="Atualizar participantes" disabled={busy} onPress={() => void load()} />
    </>}
    <TextAction label="Voltar à pelada" disabled={busy} onPress={onBack} />
  </View>;
}
