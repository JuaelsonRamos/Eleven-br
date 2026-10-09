import { useState } from 'react';
import { Modal, Platform, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useNavigation } from '@react-navigation/native';
import type { BottomTabNavigationProp } from '@react-navigation/bottom-tabs';
import type { TabParams } from '../navigation';
import { useTeams } from '../teams/TeamContext';
import { Button } from '../components/ui';
import { theme } from '../theme';
import type { Billing } from './api';

export function ActivatePro({ data, teamId }: { data: Billing; teamId: string }) {
  const { selected } = useTeams();
  const navigation = useNavigation<BottomTabNavigationProp<TabParams>>();
  const [confirmTeam, setConfirmTeam] = useState<string | null>(null);
  const canActivate = Platform.OS === 'web' && selected?.id === teamId && data.plan === 'free' && data.can_manage;
  if (!canActivate) return null;
  return <>
    <Pressable accessibilityRole="button" onPress={() => setConfirmTeam(teamId)} style={({ pressed }) => [styles.cta, pressed && { opacity: 0.7 }]}><View style={styles.pill}><Text style={styles.pillText}>Ativar Pro</Text></View></Pressable>
    <Modal transparent visible={!!selected && confirmTeam === selected.id && !!canActivate} animationType="fade" onRequestClose={() => setConfirmTeam(null)}>
      <View style={styles.backdrop}><ScrollView contentContainerStyle={styles.modalScroll}><View accessibilityViewIsModal style={styles.dialog}>
        <Text accessibilityRole="header" style={styles.dialogTitle}>Ativar ELEVEN BR Pro</Text>
        <Text style={styles.body}>Você está ativando o Pro para:</Text>
        <Text style={styles.dialogTitle}>{selected?.name}</Text>
        <Text style={styles.dialogTitle}>{data ? Number(data.price).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' }) : ''}/mês</Text>
        <Text style={styles.body}>O plano será aplicado exclusivamente a este time.</Text>
        <Button label="Cancelar" variant="secondary" onPress={() => setConfirmTeam(null)} />
        <Button label="Continuar" onPress={() => {
          if (!selected || selected.id !== confirmTeam || !canActivate) return;
          setConfirmTeam(null);
          navigation.navigate('ELEVEN PRO');
        }} />
      </View></ScrollView></View>
    </Modal>
  </>;
}
const styles = StyleSheet.create({
  cta: { alignSelf: 'flex-start', minHeight: 44, justifyContent: 'center' },
  pill: { alignSelf: 'flex-start', marginTop: 4, borderRadius: theme.radii.pill, backgroundColor: '#FFF1BC', borderWidth: 1, borderColor: theme.colors.gold, paddingHorizontal: 10, paddingVertical: 5 },
  pillText: { fontSize: 11, fontWeight: '800', color: theme.colors.green },
  backdrop: { flex: 1, backgroundColor: 'rgba(0,0,0,0.4)' },
  modalScroll: { flexGrow: 1, justifyContent: 'center', padding: 20 },
  dialog: { width: '100%', maxWidth: 420, alignSelf: 'center', padding: 20, gap: 16, backgroundColor: theme.colors.white, borderRadius: theme.radii.lg },
  dialogTitle: { fontSize: 19, fontWeight: '800', color: theme.colors.green },
  body: { fontSize: 15, color: theme.colors.muted },
});
