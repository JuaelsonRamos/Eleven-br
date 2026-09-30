import { Text, View } from 'react-native';
import { Badge, FilterChip, TeamBadge } from '../components/ui';
import { useTeams } from '../teams/TeamContext';
import { styles } from '../events/styles';
import { categories, type PublicTeam, type Reliability } from './api';

export function useModalityLabel() {
  const { options } = useTeams();
  return (value: string) => options.modalities.find(item => item.value === value)?.label ?? value;
}

/** Public identity only: crest, name, city/UF, modalities and category. */
export function TeamLine({ team }: { team: PublicTeam }) {
  const label = useModalityLabel();
  return <View style={[styles.row, { flexWrap: 'nowrap' }]}>
    <TeamBadge name={team.name} crestUrl={team.crest_url} size={48} />
    <View style={{ flex: 1, minWidth: 0 }}>
      <Text style={styles.heading}>{team.name}</Text>
      <Text style={styles.note}>{team.city}/{team.state} • {team.modalities.map(label).join(', ')} • {team.category ? categories[team.category] : 'Categoria não informada'}</Text>
    </View>
  </View>;
}

/** Raw, verifiable indicators; never a score, stars or ranking. */
export function ReliabilityInfo({ data, compact = false }: { data: Reliability; compact?: boolean }) {
  const plural = (count: number, one: string, many: string) => `${count} ${count === 1 ? one : many}`;
  const answers = [['Compareceu', data.attended], ['Cumpriu o horário', data.punctual], ['Cumpriu o combinado', data.kept_agreement]] as const;
  if (compact) return <Text style={styles.note}>{data.label ?? `${plural(data.validated_fixtures, 'confronto validado', 'confrontos validados')} • ${plural(data.reviews, 'avaliação', 'avaliações')}`}</Text>;
  return <View style={{ gap: 6 }}>
    <Text style={styles.text}>{plural(data.validated_fixtures, 'confronto validado', 'confrontos validados')} • {plural(data.reviews, 'avaliação recebida', 'avaliações recebidas')}</Text>
    {data.label ? <Badge label={data.label} tone="info" /> : answers.map(([label, value]) => <Text key={label} style={styles.note}>{label}: {value} de {data.reviews}</Text>)}
  </View>;
}

export function YesNo({ label, value, onChange, disabled }: { label: string; value: boolean | null; onChange: (value: boolean) => void; disabled?: boolean }) {
  return <View style={{ gap: 6 }}>
    <Text style={styles.text}>{label}</Text>
    <View accessibilityRole="radiogroup" accessibilityLabel={label} style={styles.row}>
      {([true, false] as const).map(option => <FilterChip key={String(option)} role="radio" label={option ? 'Sim' : 'Não'} accessibilityLabel={`${label} ${option ? 'Sim' : 'Não'}`} selected={value === option} disabled={disabled} onPress={() => onChange(option)} />)}
    </View>
  </View>;
}
