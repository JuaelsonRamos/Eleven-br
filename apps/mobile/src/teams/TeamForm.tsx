import { useRef, useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { Field, FormError, TextAction } from '../components/AuthLayout';
import { Button, Card, TeamBadge } from '../components/ui';
import { theme } from '../theme';
import { findSimilar, modalityLabels, saveTeam, type PublicTeam, type Team, type TeamInput } from './api';
import { useTeams } from './TeamContext';
import { StateSelector } from './StateSelector';

export function TeamForm({ team, onDone, onCancel }: { team?: Team; onDone: () => void; onCancel: () => void }) {
  const { options, saved, reload } = useTeams();
  const [data, setData] = useState<TeamInput>({ name: team?.name ?? '', city: team?.city ?? '', state: team?.state ?? '', modalities: team?.modalities ?? [] });
  const [similar, setSimilar] = useState<PublicTeam[] | null>(null);
  const [busy, setBusy] = useState(false);
  const locked = useRef(false);
  const [error, setError] = useState<string | null>(null);
  const change = <K extends keyof TeamInput>(field: K, value: TeamInput[K]) => { setData(current => ({ ...current, [field]: value })); setSimilar(null); setError(null); };

  async function submit(confirmed = false) {
    if (locked.current) return;
    const clean = { ...data, name: data.name.trim(), city: data.city.trim(), state: data.state.trim().toUpperCase() };
    if (!clean.name || !clean.city || !options.states.some(item => item.value === clean.state) || !clean.modalities.length || !clean.modalities.every(value => options.modalities.some(item => item.value === value))) {
      setError('Preencha nome, cidade, UF válida e ao menos uma modalidade.'); return;
    }
    locked.current = true; setBusy(true); setError(null);
    try {
      if (!team && !confirmed) {
        const matches = await findSimilar(clean);
        if (matches.length) { setSimilar(matches); return; }
      }
      await saved(await saveTeam(clean, team?.id));
      onDone();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Não foi possível salvar o time.');
      // Revoked permissions are checked by the API, including while a form was open.
      if (cause instanceof Error && 'status' in cause && (cause.status === 403 || cause.status === 404)) void reload();
    } finally { locked.current = false; setBusy(false); }
  }

  return <View style={styles.form}>
    <TeamBadge name={data.name || 'seu time'} />
    <Text style={styles.note}>Escudo opcional. A inclusão de imagens estará disponível em uma próxima etapa.</Text>
    <Field label="Nome do time" value={data.name} onChangeText={value => change('name', value)} maxLength={100} autoCapitalize="words" editable={!busy} />
    <Field label="Cidade" value={data.city} onChangeText={value => change('city', value)} maxLength={100} autoCapitalize="words" editable={!busy} />
    <StateSelector value={data.state} options={options.states} onChange={value => change('state', value)} disabled={busy} />
    <Text style={styles.label}>Modalidades</Text>
    <Text style={styles.note}>Selecione uma ou mais modalidades. Todas estão disponíveis no Free.</Text>
    <View style={styles.choices}>
      {options.modalities.map(item => <Pressable key={item.value} accessibilityRole="checkbox" accessibilityLabel={item.label}
        aria-checked={data.modalities.includes(item.value)}
        accessibilityState={{ checked: data.modalities.includes(item.value), disabled: busy }} disabled={busy}
        onPress={() => change('modalities', data.modalities.includes(item.value) ? data.modalities.filter(value => value !== item.value) : [...data.modalities, item.value])} style={[styles.choice, data.modalities.includes(item.value) && styles.checked]}>
        <Text style={styles.choiceText}>{item.label}{data.modalities.includes(item.value) ? ' ✓' : ''}</Text>
      </Pressable>)}
    </View>
    <FormError message={error} />
    {similar ? <Card><View style={styles.form}>
      <Text accessibilityRole="alert" style={styles.label}>Encontramos um time parecido.</Text>
      {similar.map(item => <Text key={item.code} style={styles.note}>{item.name} · {item.city}/{item.state} · {modalityLabels(item.modalities, options.modalities)} · {item.code}</Text>)}
      <Button label={busy ? 'Salvando…' : 'Criar mesmo assim'} disabled={busy} onPress={() => void submit(true)} />
      <TextAction label="Voltar" disabled={busy} onPress={() => setSimilar(null)} />
    </View></Card> : <Button label={busy ? 'Salvando…' : team ? 'Salvar alterações' : 'Criar time'} disabled={busy} onPress={() => void submit()} />}
    <TextAction label="Cancelar" disabled={busy} onPress={onCancel} />
  </View>;
}

const styles = StyleSheet.create({
  form: { gap: 16 }, note: { fontFamily: theme.fontFamily, fontSize: 14, color: theme.colors.muted, lineHeight: 22 },
  label: { fontFamily: theme.fontFamily, fontSize: 16, fontWeight: '700', color: theme.colors.graphite },
  choices: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  choice: { minHeight: 48, padding: 14, borderRadius: 12, borderWidth: 1, borderColor: theme.colors.border, justifyContent: 'center' },
  checked: { backgroundColor: theme.colors.lightGreen, borderColor: theme.colors.green },
  choiceText: { fontFamily: theme.fontFamily, color: theme.colors.green, fontWeight: '600' },
});
