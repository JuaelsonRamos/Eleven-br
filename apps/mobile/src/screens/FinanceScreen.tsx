import { useCallback, useRef } from 'react';
import { KeyboardAvoidingView, Platform, ScrollView, StyleSheet, View } from 'react-native';
import { useFocusEffect } from '@react-navigation/native';
import type { BottomTabScreenProps } from '@react-navigation/bottom-tabs';
import { SafeAreaView } from 'react-native-safe-area-context';
import type { TabParams } from '../navigation';
import { AppHeader, Button, EmptyState, ErrorState, LoadingState } from '../components/ui';
import { TeamHeading } from '../teams/TeamHeading';
import { HelpShortcut } from '../help/HelpShortcut';
import { FinancePanel } from '../finance/FinancePanel';
import { useTeams } from '../teams/TeamContext';
import { theme } from '../theme';

export function FinanceScreen({ navigation, route }: BottomTabScreenProps<TabParams, 'Financeiro'>) {
  const scroll = useRef<ScrollView>(null);
  const { selected, loading, error, reload } = useTeams();
  useFocusEffect(useCallback(() => { void reload(); }, [reload]));
  const onNavigate = useCallback(() => scroll.current?.scrollTo({ y: 0, animated: false }), []);
  const consume = useCallback(() => navigation.setParams({ teamId: undefined, duesId: undefined }), [navigation]);
  return <SafeAreaView style={styles.safe} edges={['top', 'left', 'right']}>
    <KeyboardAvoidingView style={styles.safe} behavior={Platform.OS === 'ios' ? 'padding' : undefined}><ScrollView keyboardShouldPersistTaps="handled" ref={scroll} contentContainerStyle={styles.scroll}><View style={styles.container}>
      <AppHeader />
      {loading ? <LoadingState /> : error ? <ErrorState onRetry={() => void reload()} /> : selected ? <View key={selected.id} style={{ gap: 16 }}><TeamHeading team={selected} /><HelpShortcut topic="finance-overview" label="Como funciona o Financeiro?" /><FinancePanel teamId={selected.id} initialDuesId={route.params?.teamId === selected.id ? route.params.duesId : undefined} onInitialConsumed={consume} onBack={() => navigation.navigate('Início')} onNavigate={onNavigate} /></View> : <>
        <EmptyState title="Selecione seu time" description="Abra um time para consultar seu financeiro." />
        <Button label="Meus times" onPress={() => navigation.navigate('Times')} />
      </>}
    </View></ScrollView></KeyboardAvoidingView>
  </SafeAreaView>;
}
const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: theme.colors.background },
  scroll: { flexGrow: 1, paddingHorizontal: theme.space.lg, paddingBottom: 24 },
  container: { width: '100%', maxWidth: theme.maxWidth, alignSelf: 'center', gap: theme.space.lg },
});
