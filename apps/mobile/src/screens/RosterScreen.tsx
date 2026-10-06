import { TeamScreenHeader } from '../components/TeamScreenHeader';
import { useCallback } from 'react';
import { KeyboardAvoidingView, Platform, ScrollView, StyleSheet, View } from 'react-native';
import { useFocusEffect } from '@react-navigation/native';
import type { BottomTabScreenProps } from '@react-navigation/bottom-tabs';
import { SafeAreaView } from 'react-native-safe-area-context';
import type { TabParams } from '../navigation';
import { Button, EmptyState, ErrorState, LoadingState } from '../components/ui';
import { TeamHeading } from '../teams/TeamHeading';
import { HelpShortcut } from '../help/HelpShortcut';
import { RosterPanel } from '../roster/RosterPanel';
import { useTeams } from '../teams/TeamContext';
import { theme } from '../theme';

export function RosterScreen({ navigation, route }: BottomTabScreenProps<TabParams, 'Elenco'>) {
  const { selected, loading, error, reload } = useTeams();
  useFocusEffect(useCallback(() => { void reload(); }, [reload]));
  const consume = useCallback(() => navigation.setParams({ teamId: undefined, view: undefined }), [navigation]);
  return <SafeAreaView style={styles.safe} edges={['top', 'left', 'right']}>
    <KeyboardAvoidingView style={styles.safe} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <ScrollView keyboardShouldPersistTaps="handled" contentContainerStyle={styles.scroll}><View style={styles.container}>
        <TeamScreenHeader />
        {loading ? <LoadingState /> : error ? <ErrorState onRetry={() => void reload()} /> : selected ? <View key={selected.id} style={{ gap: 16 }}><TeamHeading team={selected} /><HelpShortcut topic="add-players" label="Como cadastrar jogadores?" /><RosterPanel team={selected} initialRequests={route.params?.teamId === selected.id && route.params.view === 'requests'} onInitialConsumed={consume} onBack={() => navigation.navigate('Início')} /></View> : <>
          <EmptyState title="Selecione seu time" description="Abra um time para acompanhar o elenco." icon="people-outline" />
          <Button label="Meus times" onPress={() => navigation.navigate('Times')} />
        </>}
      </View></ScrollView>
    </KeyboardAvoidingView>
  </SafeAreaView>;
}
const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: theme.colors.background },
  scroll: { flexGrow: 1, paddingHorizontal: theme.space.lg, paddingBottom: 24 },
  container: { width: '100%', maxWidth: theme.maxWidth, alignSelf: 'center', gap: theme.space.lg },
});
