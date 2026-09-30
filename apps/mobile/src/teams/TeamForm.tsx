import { useRef, useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { Field, FormError, TextAction } from '../components/AuthLayout';
import { Button, Card } from '../components/ui';
import { ImageSelector } from '../images/ImageSelector';
import { saveCrest, type ImageChoice } from '../images/api';
import { theme } from '../theme';
import { categories, findSimilar, modalityLabels, saveTeam, type Municipality, type PublicTeam, type Team, type TeamInput } from './api';
import { useTeams } from './TeamContext';
import { StateSelector } from './StateSelector';
import { MunicipalitySelector } from './MunicipalitySelector';
import { LocationEditor } from './LocationEditor';

export function TeamForm({ team, onDone, onCancel }: { team?: Team; onDone: () => void; onCancel: () => void }) {
  const { options, saved, reload } = useTeams();
  const [data, setData] = useState<TeamInput>({ name: team?.name ?? '', state: team?.state ?? '', municipality_code: team?.municipality_code ?? null, modalities: team?.modalities ?? [], category: team?.category ?? null });
  // Registration only: an official municipality of the chosen UF, never typed text.
  const [place, setPlace] = useState<Municipality | null>(null);
  const [moving, setMoving] = useState(false);
  const [similar, setSimilar] = useState<PublicTeam[] | null>(null);
  const [busy, setBusy] = useState(false);
  const locked = useRef(false);
  const [error, setError] = useState<string | null>(null);
  const [crest, setCrest] = useState<ImageChoice>(undefined);
  const [persisted, setPersisted] = useState<Team | undefined>(team);
  const change = <K extends keyof TeamInput>(field: K, value: TeamInput[K]) => { setData(current => ({ ...current, [field]: value })); setSimilar(null); setError(null); };

  async function submit(confirmed = false) {
    if (locked.current) return;
    const clean = { ...data, name: data.name.trim(), municipality_code: place?.code ?? null };
    if (!clean.category) { setError('Selecione a categoria do time.'); return; }
    const located = Boolean(persisted) || (options.states.some(item => item.value === clean.state) && clean.municipality_code !== null);
    if (!clean.name || !located || !clean.modalities.length || !clean.modalities.every(value => options.modalities.some(item => item.value === value))) {
      setError('Preencha nome, UF, cidade e ao menos uma modalidade.'); return;
    }
    locked.current = true; setBusy(true); setError(null);
    try {
      if (!persisted && !confirmed) {
        const matches = await findSimilar(clean);
        if (matches.length) { setSimilar(matches); return; }
      }
      // Profile edits never carry the location: only the President changes it.
      let updated = await saveTeam(persisted ? { name: clean.name, modalities: clean.modalities, category: clean.category } : clean, persisted?.id);
      setPersisted(updated);
      if (crest !== undefined) {
        try { updated = await saveCrest(updated.id, crest); }
        catch (cause) {
          setError(`Time salvo. ${cause instanceof Error ? cause.message : 'Não foi possível salvar o escudo.'} Tente novamente ou continue sem alterar o escudo.`);
          return;
        }
      }
      await saved(updated);
      onDone();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Não foi possível salvar o time.');
      // Revoked permissions are checked by the API, including while a form was open.
      if (cause instanceof Error && 'status' in cause && (cause.status === 403 || cause.status === 404)) void reload();
    } finally { locked.current = false; setBusy(false); }
  }

  return <View style={styles.form}>
    <ImageSelector kind="crest" name={data.name || 'seu time'} current={persisted?.crest_url || null} choice={crest}
      disabled={busy} onChange={value => { setCrest(value); setError(null); }} />
    <Field label="Nome do time" value={data.name} onChangeText={value => change('name', value)} maxLength={100} autoCapitalize="words" editable={!busy} />
    {persisted ? <View style={styles.form}>
      <Text style={styles.label}>Localização</Text>
      <Text style={styles.note}>{persisted.city}/{persisted.state}{persisted.location_confirmed ? '' : ' — aguardando confirmação do Presidente'}</Text>
      {persisted.my_role !== 'president' ? <Text style={styles.note}>Somente o Presidente confirma ou altera a localização.</Text>
        : moving ? <LocationEditor team={persisted} onDone={updated => { setPersisted(updated); setMoving(false); }} onCancel={() => setMoving(false)} />
        : <TextAction label={persisted.location_confirmed ? 'Alterar localização' : 'Confirmar localização'} disabled={busy} onPress={() => setMoving(true)} />}
    </View> : <>
      <StateSelector value={data.state} options={options.states} onChange={value => { change('state', value); setPlace(null); }} disabled={busy} />
      <MunicipalitySelector state={data.state} value={place} onChange={value => { setPlace(value); setSimilar(null); setError(null); }} disabled={busy} />
    </>}
    <Text style={styles.label}>Categoria</Text>
    <View style={styles.choices}>{(Object.keys(categories) as (keyof typeof categories)[]).map(value => <Pressable key={value} accessibilityRole="radio" accessibilityLabel={categories[value]} accessibilityState={{ selected: data.category === value }} disabled={busy} onPress={() => change('category', value)} style={[styles.choice, data.category === value && styles.checked]}><Text style={styles.choiceText}>{categories[value]}{data.category === value ? ' ✓' : ''}</Text></Pressable>)}</View>
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
    </View></Card> : <Button label={busy ? 'Salvando…' : persisted ? 'Salvar alterações' : 'Criar time'} disabled={busy} onPress={() => void submit()} />}
    <TextAction label={persisted && !team ? 'Continuar sem alterar o escudo' : 'Cancelar'} disabled={busy} onPress={() => {
      if (persisted) { void saved(persisted).then(() => { if (!team) onDone(); else onCancel(); }); }
      else onCancel();
    }} />
  </View>;
}

const styles = StyleSheet.create({
  form: { gap: theme.space.lg, width: '100%', maxWidth: theme.formWidth, alignSelf: 'center' }, note: { fontFamily: theme.fontFamily, fontSize: 14, color: theme.colors.muted, lineHeight: 22 },
  label: { fontFamily: theme.fontFamily, fontSize: 16, fontWeight: '700', color: theme.colors.graphite },
  choices: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  choice: { minHeight: 48, padding: 14, borderRadius: 12, borderWidth: 1, borderColor: theme.colors.border, justifyContent: 'center' },
  checked: { backgroundColor: theme.colors.lightGreen, borderColor: theme.colors.green },
  choiceText: { fontFamily: theme.fontFamily, color: theme.colors.green, fontWeight: '600' },
});
