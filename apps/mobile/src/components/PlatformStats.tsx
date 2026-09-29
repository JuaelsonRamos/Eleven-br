import { useEffect, useState } from 'react';
import { StyleSheet, Text, useWindowDimensions, View } from 'react-native';
import Ionicons from '@expo/vector-icons/Ionicons';
import { platformStats } from '../auth/api';
import type { IconName } from './design';
import { theme } from '../theme';

const count = (value: number) => value.toLocaleString('pt-BR');

/** Real platform totals from the public API; the row is omitted if they cannot be loaded. */
export function PlatformStats() {
  const [counts, setCounts] = useState<{ teams: number; players: number } | null>(null);
  const [failed, setFailed] = useState(false);
  const compact = useWindowDimensions().width < 360;
  useEffect(() => {
    let active = true;
    void platformStats().then(value => { if (active) setCounts(value); }).catch(() => { if (active) setFailed(true); });
    return () => { active = false; };
  }, []);
  if (failed) return null;
  if (!counts) return <View style={s.row} />;
  return <View style={s.row}>
    <Stat compact={compact} icon="people" value={count(counts.teams)} label={counts.teams === 1 ? 'time' : 'times'} />
    <View style={s.divider} />
    <Stat compact={compact} icon="person" value={count(counts.players)} label={counts.players === 1 ? 'jogador' : 'jogadores'} />
    <View style={s.divider} />
    <View style={s.item}>
      <Ionicons accessible={false} aria-hidden name="football-outline" size={compact ? 20 : 24} color={theme.colors.green} />
      <Text style={[s.label, compact && s.labelCompact]}>já estão{'\n'}em campo</Text>
    </View>
  </View>;
}

function Stat({ icon, value, label, compact }: { icon: IconName; value: string; label: string; compact: boolean }) {
  return <View style={s.item}>
    <Ionicons accessible={false} aria-hidden name={icon} size={compact ? 20 : 24} color={theme.colors.green} />
    <Text style={[s.label, compact && s.labelCompact]}><Text style={[s.value, compact && s.valueCompact]}>{value}</Text>{'\n'}{label}</Text>
  </View>;
}

const s = StyleSheet.create({
  row: { flexDirection: 'row', alignItems: 'center', minHeight: 44 },
  item: { flex: 1, minWidth: 0, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: theme.space.sm },
  divider: { width: 1, alignSelf: 'stretch', marginVertical: theme.space.xs, backgroundColor: theme.colors.border },
  label: { flexShrink: 1, fontFamily: theme.fontFamily, fontSize: 13, lineHeight: 17, color: theme.colors.muted },
  labelCompact: { fontSize: 12, lineHeight: 16 },
  value: { fontSize: 17, lineHeight: 21, fontWeight: '800', color: theme.colors.green },
  valueCompact: { fontSize: 16, lineHeight: 20 },
});
