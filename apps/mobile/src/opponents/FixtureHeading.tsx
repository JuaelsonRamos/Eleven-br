import { Text, View } from 'react-native';
import { TeamBadge } from '../components/ui';
import { styles } from '../events/styles';
import type { Fixture } from './api';

export function FixtureHeading({ item }: { item: Fixture }) {
  return <View style={styles.row}>
    {[item.home_team, item.away_team].map((team, index) => <View key={team.id} style={{ flex: 1, minWidth: 0, alignItems: 'center', gap: 8 }}>
      <TeamBadge name={team.name} crestUrl={team.crest_url} size={44} />
      <Text style={[styles.heading, { textAlign: 'center' }]}>{index === 1 ? '× ' : ''}{team.name}</Text>
    </View>)}
  </View>;
}
