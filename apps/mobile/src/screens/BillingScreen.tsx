import { useCallback, useRef } from 'react';
import { ScrollView, StyleSheet, View } from 'react-native';
import { useFocusEffect } from '@react-navigation/native';
import type { BottomTabScreenProps } from '@react-navigation/bottom-tabs';
import { SafeAreaView } from 'react-native-safe-area-context';
import type { TabParams } from '../navigation';
import { AppHeader, Button, EmptyState, ErrorState, LoadingState } from '../components/ui';
import { TeamHeading } from '../teams/TeamHeading';
import { HelpShortcut } from '../help/HelpShortcut';
import { BillingPanel } from '../billing/BillingPanel';
import { useTeams } from '../teams/TeamContext';
import { theme } from '../theme';

export function BillingScreen({ navigation }: BottomTabScreenProps<TabParams>) {
  const scroll = useRef<ScrollView>(null);
  const { selected, loading, error, reload } = useTeams();
  useFocusEffect(useCallback(() => { void reload(); }, [reload]));
  return <SafeAreaView style={styles.safe} edges={['top', 'left', 'right']}>
    <ScrollView ref={scroll} keyboardShouldPersistTaps="handled" contentContainerStyle={styles.scroll}><View style={styles.container}>
      <AppHeader />
      {loading ? <LoadingState /> : error ? <ErrorState onRetry={() => void reload()} /> : selected ? <View key={selected.id} style={{ gap: 16 }}><TeamHeading team={selected} /><HelpShortcut topic="pro-overview" label="Como funciona o ELEVEN PRO?" /><BillingPanel teamId={selected.id} /></View> : <>
        <EmptyState title="Selecione seu time" description="Abra um time para consultar o plano e a assinatura ELEVEN PRO." />
        <Button label="Meus times" onPress={() => navigation.navigate('Times')} />
      </>}
    </View></ScrollView>
  </SafeAreaView>;
}
const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: theme.colors.background },
  scroll: { flexGrow: 1, paddingHorizontal: theme.space.lg, paddingBottom: 24 },
  container: { width: '100%', maxWidth: theme.maxWidth, alignSelf: 'center', gap: theme.space.lg },
});
