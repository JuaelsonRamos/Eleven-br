import { StyleSheet, Text, View } from 'react-native';
import { TeamBadge } from '../components/ui';
import { theme } from '../theme';
import type { Team } from './api';

export function TeamHeading({ team }: { team: Team }) {
  return <View style={styles.row}>
    <TeamBadge name={team.name} crestUrl={team.crest_url} size={40} />
    <Text accessibilityRole="header" style={styles.name}>{team.name}</Text>
  </View>;
}
const styles = StyleSheet.create({
  row: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  name: { flex: 1, fontFamily: theme.fontFamily, fontWeight: '700', fontSize: 18, color: theme.colors.green },
});
