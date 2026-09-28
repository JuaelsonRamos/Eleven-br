import { useEffect, useState } from 'react';
import { Text } from 'react-native';
import { platformStats } from '../auth/api';
import { authStyles } from './AuthLayout';

export function PlatformStats() {
  const [counts, setCounts] = useState<{ teams: number; players: number } | null>(null);
  useEffect(() => { let active = true; void platformStats().then(value => { if (active) setCounts(value); }).catch(() => {}); return () => { active = false; }; }, []);
  return counts ? <Text style={authStyles.note}>{counts.teams.toLocaleString('pt-BR')} times · {counts.players.toLocaleString('pt-BR')} jogadores no ELEVEN BR</Text> : null;
}
