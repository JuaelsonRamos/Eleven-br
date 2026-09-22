import { Image, StyleSheet, Text, View } from 'react-native';
import { Badge, TeamBadge } from '../components/ui';
import { theme } from '../theme';
import { modalityLabels, roles, type Team } from './api';
import { useTeams } from './TeamContext';

export function TeamSummary({ team, detail = false }: { team: Team; detail?: boolean }) {
  const { options } = useTeams();
  return <View style={styles.summary}>
    {team.crest_url ? <Image source={{ uri: team.crest_url }} accessibilityLabel={`Escudo de ${team.name}`} style={styles.crest} /> : <TeamBadge name={team.name} />}
    <Text accessibilityRole="header" style={styles.title}>{team.name}</Text>
    <Text style={styles.text}>{team.city} · {team.state}</Text>
    <Text style={styles.text}>{modalityLabels(team.modalities, options.modalities)}</Text>
    <View style={styles.badges}><Badge label={roles[team.my_role]} /><Badge label={team.plan === 'free' ? 'Free' : 'Pro'} /></View>
    {detail && <Text selectable style={styles.text}>Código do time: {team.code}</Text>}
  </View>;
}

const styles = StyleSheet.create({
  summary: { gap: 10 }, crest: { width: 64, height: 64, borderRadius: 20 },
  title: { fontFamily: theme.fontFamily, fontSize: 23, fontWeight: '800', color: theme.colors.graphite },
  text: { fontFamily: theme.fontFamily, fontSize: 16, color: theme.colors.muted },
  badges: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
});
