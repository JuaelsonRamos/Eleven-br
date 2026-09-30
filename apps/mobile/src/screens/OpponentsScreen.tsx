import { useCallback, useRef } from 'react';
import { KeyboardAvoidingView, Platform, ScrollView, StyleSheet, View } from 'react-native';
import { useFocusEffect } from '@react-navigation/native';
import type { BottomTabScreenProps } from '@react-navigation/bottom-tabs';
import { SafeAreaView } from 'react-native-safe-area-context';
import type { TabParams } from '../navigation';
import { AppHeader, Button, EmptyState, ErrorState, LoadingState } from '../components/ui';
import { TeamHeading } from '../teams/TeamHeading';
import { HelpShortcut } from '../help/HelpShortcut';
import { OpponentsPanel } from '../opponents/OpponentsPanel';
import { useTeams } from '../teams/TeamContext';
import { theme } from '../theme';

export function OpponentsScreen({ navigation, route }: BottomTabScreenProps<TabParams, 'Adversários'>) {
  const scroll = useRef<ScrollView>(null);
  const { selected, loading, error, reload } = useTeams();
  useFocusEffect(useCallback(() => { void reload(); }, [reload]));
  const onNavigate = useCallback(() => scroll.current?.scrollTo({ y: 0, animated: false }), []);
  const consume = useCallback(() => navigation.setParams({ teamId: undefined, view: undefined, fixtureId: undefined }), [navigation]);
  const params = route.params?.teamId === selected?.id ? route.params : undefined;
  return <SafeAreaView style={styles.safe} edges={['top', 'left', 'right']}>
    <KeyboardAvoidingView style={styles.safe} behavior={Platform.OS === 'ios' ? 'padding' : undefined}><ScrollView keyboardShouldPersistTaps="handled" ref={scroll} contentContainerStyle={styles.scroll}><View style={styles.container}>
      <AppHeader />
      {loading ? <LoadingState /> : error ? <ErrorState onRetry={() => void reload()} /> : selected ? <View key={selected.id} style={{ gap: 16 }}><TeamHeading team={selected} /><HelpShortcut topic="opponents-overview" label="Como funciona a Central de Adversários?" />
        <OpponentsPanel team={selected} initialView={params?.view} initialFixture={params?.fixtureId} onInitialConsumed={consume} onNavigate={onNavigate}
          onPro={() => navigation.navigate('ELEVEN PRO')} onOpenGame={eventId => navigation.navigate('Jogos', { teamId: selected.id, eventId })} /></View> : <>
        <EmptyState title="Selecione seu time" description="Abra um time para buscar adversários e acompanhar desafios." icon="shield-half-outline" />
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
