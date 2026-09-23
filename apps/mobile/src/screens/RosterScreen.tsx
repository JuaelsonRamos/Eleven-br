import { useCallback } from 'react';
import { KeyboardAvoidingView, Platform, ScrollView, StyleSheet, View } from 'react-native';
import { useFocusEffect } from '@react-navigation/native';
import type { BottomTabScreenProps } from '@react-navigation/bottom-tabs';
import { SafeAreaView } from 'react-native-safe-area-context';
import type { TabParams } from '../navigation';
import { AppHeader, Button, EmptyState, ErrorState, LoadingState } from '../components/ui';
import { TeamHeading } from '../teams/TeamHeading';
import { RosterPanel } from '../roster/RosterPanel';
import { useTeams } from '../teams/TeamContext';
import { theme } from '../theme';

export function RosterScreen({ navigation }: BottomTabScreenProps<TabParams>) {
  const { selected, loading, error, reload } = useTeams();
  useFocusEffect(useCallback(() => { void reload(); }, [reload]));
  return <SafeAreaView style={styles.safe} edges={['top', 'left', 'right']}>
    <KeyboardAvoidingView style={styles.safe} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <ScrollView keyboardShouldPersistTaps="handled" contentContainerStyle={styles.scroll}><View style={styles.container}>
        <AppHeader />
        {loading ? <LoadingState /> : error ? <ErrorState onRetry={() => void reload()} /> : selected ? <View key={selected.id} style={{ gap: 16 }}><TeamHeading team={selected} /><RosterPanel team={selected} onBack={() => navigation.navigate('Início')} /></View> : <>
          <EmptyState title="Selecione seu time" description="Abra um time para acompanhar o elenco." icon="people-outline" />
          <Button label="Meus times" onPress={() => navigation.navigate('Times')} />
        </>}
      </View></ScrollView>
    </KeyboardAvoidingView>
  </SafeAreaView>;
}
const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: theme.colors.background },
  scroll: { flexGrow: 1, paddingHorizontal: 20, paddingBottom: 24 },
  container: { width: '100%', maxWidth: theme.maxWidth, alignSelf: 'center', gap: 20 },
});
