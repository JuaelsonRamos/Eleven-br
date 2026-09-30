import { Fragment, useCallback, useEffect, useRef, useState } from 'react';
import { Text, View } from 'react-native';
import { FormError, TextAction } from '../components/AuthLayout';
import { Badge, Button, EmptyState, FilterChip, Feedback, ListItem, LoadingState, SectionHeader, TeamBadge } from '../components/ui';
import { styles } from '../events/styles';
import { StateSelector } from '../teams/StateSelector';
import { MunicipalitySelector } from '../teams/MunicipalitySelector';
import type { Municipality } from '../teams/api';
import { useTeams } from '../teams/TeamContext';
import { categories, message, searchOpponents, tiers, type Category, type Central, type Filters, type PublicTeam, type Result, type Results } from './api';
import { ReliabilityInfo, useModalityLabel } from './parts';

const choices: Category[] = ['female', 'male', 'mixed', 'all'];

/** Heading of each result group: compatible teams by proximity, then unknown categories. */
function group(item: Result, filters: Filters) {
  if (!item.category_known && filters.category !== 'all') return 'Categoria não informada';
  if (filters.state) return `Times em ${filters.municipality ? `${filters.municipality.name}/` : ''}${filters.state}`;
  return tiers[item.tier];
}

export function SearchSection({ teamId, central, onOpen }: { teamId: string; central: Central; onOpen: (team: PublicTeam) => void }) {
  const label = useModalityLabel();
  const { options } = useTeams();
  const own = central.team.category;
  // With more than one modality the organizer chooses: no presumed main modality.
  const [modality, setModality] = useState(central.team.modalities.length === 1 ? central.team.modalities[0]! : '');
  const [category, setCategory] = useState<Category | null>(own);
  const [nearby, setNearby] = useState(true);
  const [state, setState] = useState(central.team.state);
  const [place, setPlace] = useState<Municipality | null>(null);
  const [searched, setSearched] = useState<Filters | null>(null);
  const [results, setResults] = useState<Results | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const generation = useRef(0);
  const run = useCallback(async (filters: Filters, offset = 0) => {
    const revision = ++generation.current; setLoading(true); setError(null);
    try {
      const data = await searchOpponents(teamId, filters, offset);
      if (revision !== generation.current) return;
      setSearched(filters);
      setResults(previous => offset && previous ? { ...data, items: [...previous.items, ...data.items] } : data);
    } catch (cause) { if (revision === generation.current) setError(message(cause, 'Não foi possível buscar adversários.')); }
    finally { if (revision === generation.current) setLoading(false); }
  }, [teamId]);
  useEffect(() => { const stale = generation; return () => { stale.current++; }; }, []);
  if (!central.can_manage) return <Text style={styles.note}>Somente o Presidente e administradores com a área Jogos, peladas e escalações buscam e desafiam adversários.</Text>;
  const filters: Filters | null = modality && category ? { modality, category, ...(nearby ? {} : { state, municipality: place }) } : null;
  const credits = central.credits;
  const known = results && searched ? results.items.filter(item => item.category_known || searched.category === 'all') : [];
  return <View style={styles.stack}>
    <SectionHeader title="Buscar adversário" subtitle="Primeiro a compatibilidade (modalidade e categoria), depois a proximidade." />
    <Text style={styles.text}>Buscar adversário para:</Text>
    <View accessibilityRole="radiogroup" accessibilityLabel="Modalidade do confronto" style={styles.row}>
      {central.team.modalities.map(value => <FilterChip key={value} role="radio" label={label(value)} selected={modality === value} disabled={loading} onPress={() => setModality(value)} />)}
    </View>
    <Text style={styles.text}>Categoria</Text>
    <View accessibilityRole="radiogroup" accessibilityLabel="Categoria" style={styles.row}>
      {choices.map(value => <FilterChip key={value} role="radio" label={categories[value]} selected={category === value} disabled={loading} onPress={() => setCategory(value)} />)}
    </View>
    {!own && <Text style={styles.note}>Seu time ainda não tem categoria cadastrada. Escolha a categoria que deseja procurar.</Text>}
    {category && own && category !== own && <Text style={styles.note}>{category === 'all' ? 'Todas as categorias, inclusive times sem categoria informada.' : 'Você escolheu procurar outra categoria.'}</Text>}
    <Text style={styles.text}>Local</Text>
    <View accessibilityRole="radiogroup" accessibilityLabel="Local da busca" style={styles.row}>
      <FilterChip role="radio" label="Perto do meu time" selected={nearby} disabled={loading} onPress={() => setNearby(true)} />
      <FilterChip role="radio" label="Escolher UF/cidade" selected={!nearby} disabled={loading} onPress={() => setNearby(false)} />
    </View>
    {nearby ? <Text style={styles.note}>Mesma cidade primeiro ({central.team.city}/{central.team.state}), depois o estado e outras UFs. Sem endereço nem GPS.</Text> : <>
      <StateSelector value={state} options={options.states} onChange={value => { setState(value); setPlace(null); }} disabled={loading} />
      <MunicipalitySelector label="Cidade (opcional)" state={state} value={place} onChange={setPlace} disabled={loading} />
      {place && <TextAction label="Todas as cidades da UF" disabled={loading} onPress={() => setPlace(null)} />}
    </>}
    <Text style={styles.note}>{credits.limit === null ? 'Buscar é livre. No ELEVEN BR PRO os desafios são ilimitados.' : `Buscar é livre. Plano Free: 1 desafio por mês${credits.remaining === 0 ? ' — o deste mês já foi usado.' : ' — disponível.'}`}</Text>
    <FormError message={error} />
    {!modality && <Text style={styles.note}>Escolha a modalidade do confronto.</Text>}
    <Button label={loading ? 'Buscando…' : 'Buscar adversários'} disabled={loading || !filters} onPress={() => filters && void run(filters)} />
    {results && searched && <>
      {!results.items.length && <EmptyState title="Nenhum adversário encontrado" description="Não há times compatíveis aceitando desafios com esses filtros." icon="shield-half-outline" />}
      {!searched.state && known[0] && known[0].tier !== 'city' && <Feedback tone="info" message="Nenhum adversário compatível na sua cidade. A busca foi ampliada." />}
      {results.items.length > 0 && !known.length && <Feedback tone="info" message="Nenhum time com essa categoria. Abaixo, times sem categoria informada." />}
      {results.items.map((item, index) => {
        const heading = group(item, searched);
        return <Fragment key={item.team.id}>
          {(index === 0 || group(results.items[index - 1]!, searched) !== heading) && <Text accessibilityRole="header" style={styles.heading}>{heading}</Text>}
          <ListItem title={item.team.name} subtitle={`${item.team.city}/${item.team.state} • ${item.team.category ? categories[item.team.category] : 'Categoria não informada'}`}
            leading={<TeamBadge name={item.team.name} crestUrl={item.team.crest_url} size={40} />} accessibilityLabel={`Abrir perfil de ${item.team.name}`} onPress={() => onOpen(item.team)}
            trailing={<><ReliabilityInfo data={item.reliability} compact />{item.pending_challenge && <Badge label="DESAFIO PENDENTE" tone="warning" />}</>} />
        </Fragment>;
      })}
      {results.has_more && <Button variant="secondary" label={loading ? 'Carregando…' : 'Ver mais times'} disabled={loading} onPress={() => void run(searched, results.items.length)} />}
    </>}
    {loading && !results && <LoadingState />}
  </View>;
}
