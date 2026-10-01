import { TeamBadge , Button, EmptyState, ListItem, LoadingState, StatusBadge } from '../components/ui';
import { fixtureStatus } from './api';
import { useCallback, useEffect, useRef, useState } from 'react';
import { View } from 'react-native';
import { FormError } from '../components/AuthLayout';

import { styles } from '../events/styles';
import { listFixtures, message, resultLabels, when, type Fixture } from './api';

export const resultTones = { NONE: 'neutral', PENDING: 'warning', VALIDATED: 'success', DISPUTED: 'danger' } as const;
export const fixtureTitle = (item: Fixture) => item.result_status === 'VALIDATED'
  ? `${item.home_team.name} ${item.home_score} x ${item.away_score} ${item.away_team.name}`
  : `${item.home_team.name} x ${item.away_team.name}`;

export function FixtureList({ teamId, onOpen }: { teamId: string; onOpen: (fixture: string) => void }) {
  const [items, setItems] = useState<Fixture[] | null>(null);
  const [more, setMore] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const generation = useRef(0);
  const load = useCallback(async (offset = 0) => {
    const revision = ++generation.current; setLoading(true); setError(null);
    try {
      const page = await listFixtures(teamId, offset);
      if (revision !== generation.current) return;
      setItems(previous => offset && previous ? [...previous, ...page.items] : page.items); setMore(page.has_more);
    } catch (cause) { if (revision === generation.current) setError(message(cause, 'Não foi possível carregar os confrontos.')); }
    finally { if (revision === generation.current) setLoading(false); }
  }, [teamId]);
  useEffect(() => { const stale = generation; void load(); return () => { stale.current++; }; }, [load]);
  if (loading && !items) return <LoadingState />;
  return <View style={styles.stack}>
    <FormError message={error} />
    {items && !items.length && <EmptyState title="Nenhum confronto ainda" description="Desafios aceitos viram confrontos entre os dois times e aparecem aqui e em Jogos." icon="shield-half-outline" />}
    {items?.map(item => <ListItem key={item.id} leading={<TeamBadge name={item.opponent.name} crestUrl={item.opponent.crest_url} size={40} />} title={fixtureTitle(item)} subtitle={`${when(item.date, item.time)} • ${item.location}`} onPress={() => onOpen(item.id)}
      accessibilityLabel={`Abrir confronto ${item.home_team.name} x ${item.away_team.name}`} trailing={<StatusBadge label={item.status === 'SCHEDULED' ? resultLabels[item.result_status] : fixtureStatus[item.status]} tone={resultTones[item.result_status]} />} />)}
    {more && <Button variant="secondary" label={loading ? 'Carregando…' : 'Carregar mais'} disabled={loading} onPress={() => void load(items?.length ?? 0)} />}
  </View>;
}
