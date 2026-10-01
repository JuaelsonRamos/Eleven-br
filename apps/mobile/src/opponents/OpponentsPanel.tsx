import { useCallback, useEffect, useRef, useState } from 'react';
import { Switch, Text, View } from 'react-native';
import { FormError } from '../components/AuthLayout';
import { Button, Card, Feedback, FilterChip, LoadingState } from '../components/ui';
import { styles } from '../events/styles';
import type { Team } from '../teams/api';
import { getCentral, message, saveSettings, type Central } from './api';
import { ChallengeList } from './ChallengeList';
import { FixtureList } from './FixtureList';
import { FixtureView } from './FixtureView';
import { ProfileView } from './ProfileView';
import { SearchSection } from './SearchSection';

type Tab = 'search' | 'received' | 'sent' | 'fixtures';
type Mode = { kind: 'home' } | { kind: 'profile'; team: string } | { kind: 'fixture'; fixture: string };

export function OpponentsPanel({ team, initialView, initialFixture, onInitialConsumed, onPro, onOpenGame, onNavigate }: {
  team: Team; initialView?: 'received' | 'sent' | 'fixtures'; initialFixture?: string; onInitialConsumed: () => void;
  onPro: () => void; onOpenGame: (event: string) => void; onNavigate: () => void;
}) {
  const [central, setCentral] = useState<Central | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab | null>(null);
  const [mode, setMode] = useState<Mode>({ kind: 'home' });
  const [saving, setSaving] = useState(false);
  const generation = useRef(0);
  const reload = useCallback(async () => {
    const revision = ++generation.current;
    try {
      const data = await getCentral(team.id);
      if (revision !== generation.current) return;
      setCentral(data); setError(null);
      // Chosen once: answering the last pending challenge must not switch the tab.
      setTab(previous => previous ?? (data.pending_received ? 'received' : data.can_manage ? 'search' : 'fixtures'));
    }
    catch (cause) { if (revision === generation.current) setError(message(cause, 'Não foi possível carregar a Central de Adversários.')); }
  }, [team.id]);
  useEffect(() => { const stale = generation; void reload(); return () => { stale.current++; }; }, [reload]);
  // Notification links open the requested list or fixture once.
  useEffect(() => {
    // TeamContext revalidation can remount this panel on focus. Consume the destination
    // only after this mounted instance has loaded its authorized central.
    if (!central || (!initialView && !initialFixture)) return;
    if (initialFixture) setMode({ kind: 'fixture', fixture: initialFixture });
    else if (initialView) { setMode({ kind: 'home' }); setTab(initialView); }
    onInitialConsumed();
  }, [central, initialView, initialFixture, onInitialConsumed]);
  const openTeam = useCallback((other: string) => { setMode({ kind: 'profile', team: other }); onNavigate(); }, [onNavigate]);
  const openFixture = useCallback((fixture: string) => { setMode({ kind: 'fixture', fixture }); onNavigate(); }, [onNavigate]);
  const back = useCallback(() => { setMode({ kind: 'home' }); onNavigate(); void reload(); }, [onNavigate, reload]);
  async function toggle(value: boolean) {
    if (saving) return;
    setSaving(true); setError(null);
    try { setCentral(await saveSettings(team.id, value)); }
    catch (cause) { setError(message(cause, 'Não foi possível salvar a preferência.')); }
    finally { setSaving(false); }
  }
  if (!central) return error ? <View style={styles.stack}><FormError message={error} /><Button label="Tentar novamente" onPress={() => void reload()} /></View> : <LoadingState />;
  if (mode.kind === 'profile') return <ProfileView key={mode.team} teamId={team.id} otherId={mode.team} onBack={back} onOpenFixture={openFixture} onSent={reload} onPro={onPro} />;
  if (mode.kind === 'fixture') return <FixtureView key={mode.fixture} teamId={team.id} fixtureId={mode.fixture} onBack={back} onOpenGame={onOpenGame} onOpenTeam={openTeam} />;
  const pending = central.pending_received;
  const current: Tab = tab ?? 'search';
  const tabs: [Tab, string][] = [['search', 'Buscar'], ['received', pending ? `Recebidos (${pending})` : 'Recebidos'], ['sent', 'Enviados'], ['fixtures', 'Confrontos']];
  return <View style={styles.stack}>
    <Text accessibilityRole="header" style={styles.title}>Adversários</Text>
    <Text style={styles.note}>Encontre times compatíveis, desafie e valide o resultado com o adversário.</Text>
    {pending > 0 && current !== 'received' && <>
      <Feedback tone="warning" message={`${pending} desafio${pending === 1 ? ' recebido aguarda' : 's recebidos aguardam'} resposta.`} />
      <Button variant="secondary" label="Ver desafios recebidos" onPress={() => setTab('received')} />
    </>}
    <View accessibilityRole="tablist" style={styles.row}>
      {tabs.map(([value, label]) => <FilterChip key={value} label={label} selected={current === value} onPress={() => setTab(value)} />)}
    </View>
    {current === 'search' && <SearchSection teamId={team.id} central={central} onOpen={other => openTeam(other.id)} />}
    {(current === 'received' || current === 'sent') && <ChallengeList key={current} teamId={team.id} direction={current} onOpenTeam={openTeam} onOpenFixture={openFixture} onChanged={reload} />}
    {current === 'fixtures' && <FixtureList teamId={team.id} onOpen={openFixture} />}
    {central.can_manage && <Card><View style={styles.stack}>
      <View style={[styles.row, { flexWrap: 'nowrap' }]}>
        <Switch accessibilityLabel="Aceitar desafios" value={central.accepts_challenges} disabled={saving} onValueChange={value => void toggle(value)} />
        <Text style={[styles.text, { flex: 1 }]}>Aceitar desafios</Text>
      </View>
      <Text style={styles.note}>{central.accepts_challenges ? 'Seu time aparece na busca de adversários e pode receber desafios.' : 'Seu time não aparece na busca e não recebe novos desafios. Desafios e confrontos existentes continuam.'}</Text>
    </View></Card>}
    <FormError message={error} />
  </View>;
}
