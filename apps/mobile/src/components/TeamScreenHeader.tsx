import { useCallback, useState } from 'react';
import { Image, StyleSheet, Text, View } from 'react-native';
import { useFocusEffect } from '@react-navigation/native';
import { AppHeader } from './ui';
import { useTeams } from '../teams/TeamContext';
import { getBilling, type Billing } from '../billing/api';
import { ActivatePro } from '../billing/ActivatePro';
import { planLabel } from '../billing/presentation';
import { theme } from '../theme';

/** Decorative treatment shared only by the main team screens. */
export function TeamScreenHeader({ onProfile }: { onProfile?: () => void }) {
  const { selected } = useTeams();
  const [billing, setBilling] = useState<{ teamId: string; data: Billing } | null>(null);
  useFocusEffect(useCallback(() => {
    let active = true;
    setBilling(null);
    if (selected) void getBilling(selected.id).then(data => {
      if (active) setBilling({ teamId: selected.id, data });
    }).catch(() => { /* Hide the offer when authoritative status is unavailable. */ });
    return () => { active = false; };
  }, [selected]));
  const data = selected && billing?.teamId === selected.id ? billing.data : null;
  const canActivate = data?.plan === 'free' && data.can_manage;
  const accessory = data?.plan === 'pro'
    ? <View style={styles.pill}><Text style={styles.pillText}>{planLabel(data)}</Text></View>
    : canActivate ? <ActivatePro key={selected!.id} data={data!} teamId={selected!.id} /> : null;
  return <View style={styles.header}>
    <View pointerEvents="none" accessible={false} accessibilityElementsHidden importantForAccessibility="no-hide-descendants" style={StyleSheet.absoluteFill}>
      <Image source={require('../../assets/landing/players.webp')} resizeMode="cover" style={styles.art} />
      <View style={styles.overlay} />
    </View>
    <View style={styles.content}><AppHeader onProfile={onProfile} brandAccessory={accessory} /></View>
    <View style={styles.accent} />
  </View>;
}

const styles = StyleSheet.create({
  header: { marginTop: theme.space.md, minHeight: 140, justifyContent: 'flex-end', backgroundColor: theme.colors.lightGreen, borderRadius: theme.radii.lg, overflow: 'hidden', borderWidth: 1, borderColor: theme.colors.surfaceMuted },
  art: { width: '100%', height: '100%', opacity: 0.3 },
  overlay: { ...StyleSheet.absoluteFillObject, backgroundColor: 'rgba(255,255,255,0.62)' },
  content: { paddingHorizontal: theme.space.md },
  pill: { alignSelf: 'flex-start', marginTop: 4, borderRadius: theme.radii.pill, backgroundColor: '#FFF1BC', paddingHorizontal: 10, paddingVertical: 5 },
  pillText: { fontSize: 11, fontWeight: '800', color: theme.colors.green },
  accent: { height: 3, width: 48, marginLeft: theme.space.md, marginBottom: theme.space.md, borderRadius: theme.radii.pill, backgroundColor: theme.colors.gold },
});
