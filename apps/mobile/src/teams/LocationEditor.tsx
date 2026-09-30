import { useEffect, useRef, useState } from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { FormError, TextAction } from '../components/AuthLayout';
import { Button, Card } from '../components/ui';
import { theme } from '../theme';
import { getLocation, saveLocation, type Municipality, type Team } from './api';
import { MunicipalitySelector } from './MunicipalitySelector';
import { StateSelector } from './StateSelector';
import { useTeams } from './TeamContext';

/**
 * President only: confirms a legacy typed location or changes the official one, always from
 * the official lists. An obvious match may be preselected, but only the button confirms it.
 */
export function LocationEditor({ team, onDone, onCancel }: { team: Team; onDone?: (team: Team) => void; onCancel?: () => void }) {
  const { options, saved } = useTeams();
  const confirming = !team.location_confirmed;
  const [state, setState] = useState(team.state);
  const [place, setPlace] = useState<Municipality | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const sending = useRef(false);
  useEffect(() => {
    let active = true;
    void getLocation(team.id).then(found => {
      if (!active) return;
      const current = found.municipality_code ? { code: found.municipality_code, name: found.city } : found.suggestion;
      setPlace(current ? { code: current.code, name: current.name } : null);
    }, cause => { if (active) setError(cause instanceof Error ? cause.message : 'Não foi possível carregar a localização.'); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [team.id]);
  async function save() {
    if (sending.current) return;
    if (!place) { setError('Selecione a cidade do time.'); return; }
    sending.current = true; setBusy(true); setError(null);
    try { const updated = await saveLocation(team.id, { state, municipality_code: place.code }); await saved(updated); onDone?.(updated); }
    catch (cause) { setError(cause instanceof Error ? cause.message : 'Não foi possível salvar a localização.'); }
    finally { sending.current = false; setBusy(false); }
  }
  return <Card><View style={s.stack}>
    <Text accessibilityRole="header" style={s.heading}>{confirming ? 'Confirme a localização do seu time' : 'Alterar localização do time'}</Text>
    <Text style={s.text}>Localização atual: {team.city} / {team.state}</Text>
    {confirming && <Text style={s.note}>Escolha a UF e a cidade na lista oficial. Se a localização atual estiver certa, é só confirmar.</Text>}
    <StateSelector value={state} options={options.states} onChange={value => { setState(value); setPlace(null); setError(null); }} disabled={busy || loading} />
    <MunicipalitySelector state={state} value={place} onChange={value => { setPlace(value); setError(null); }} disabled={busy || loading} />
    <FormError message={error} />
    <Button label={busy ? 'Salvando…' : confirming ? 'CONFIRMAR LOCALIZAÇÃO' : 'Salvar localização'} disabled={busy || loading || !place} onPress={() => void save()} />
    {onCancel && <TextAction label="Cancelar" disabled={busy} onPress={onCancel} />}
  </View></Card>;
}

const s = StyleSheet.create({
  stack: { gap: theme.space.md },
  heading: { fontFamily: theme.fontFamily, fontSize: theme.type.heading, fontWeight: '800', color: theme.colors.graphite },
  text: { fontFamily: theme.fontFamily, fontSize: theme.type.body, color: theme.colors.graphite },
  note: { fontFamily: theme.fontFamily, fontSize: theme.type.small, lineHeight: 21, color: theme.colors.muted },
});
