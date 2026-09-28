import { useCallback, useRef } from 'react';
import { ScrollView, StyleSheet, View } from 'react-native';
import { useFocusEffect } from '@react-navigation/native';
import type { BottomTabScreenProps } from '@react-navigation/bottom-tabs';
import { SafeAreaView } from 'react-native-safe-area-context';
import type { TabParams } from '../navigation';
import { AppHeader, Button, EmptyState, ErrorState, LoadingState } from '../components/ui';
import { TeamHeading } from '../teams/TeamHeading';
import { LineupsPanel } from '../lineups/LineupsPanel';
import { useTeams } from '../teams/TeamContext';
import { theme } from '../theme';

export function LineupsScreen({ navigation }: BottomTabScreenProps<TabParams>) {
  const scroll = useRef<ScrollView>(null);
  const { selected, loading, error, reload } = useTeams();
  useFocusEffect(useCallback(() => { void reload(); }, [reload]));
  return <SafeAreaView style={styles.safe} edges={['top', 'left', 'right']}>
    <ScrollView ref={scroll} contentContainerStyle={styles.scroll}><View style={styles.container}>
      <AppHeader />
      {loading ? <LoadingState /> : error ? <ErrorState onRetry={() => void reload()} /> : selected ? <View key={selected.id} style={{ gap: 16 }}><TeamHeading team={selected} /><LineupsPanel teamId={selected.id} /></View> : <>
        <EmptyState title="Selecione seu time" description="Abra um time para consultar suas escalações." />
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
