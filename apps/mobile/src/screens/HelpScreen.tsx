import { useCallback, useEffect, useRef, useState } from 'react';
import { ScrollView, StyleSheet, View } from 'react-native';
import type { BottomTabScreenProps } from '@react-navigation/bottom-tabs';
import { SafeAreaView } from 'react-native-safe-area-context';
import type { TabParams } from '../navigation';
import { AppHeader } from '../components/ui';
import { HelpCenter } from '../help/HelpCenter';
import { theme } from '../theme';

export function HelpScreen({ navigation, route }: BottomTabScreenProps<TabParams, 'Ajuda'>) {
  const scroll = useRef<ScrollView>(null);
  const [topic, setTopic] = useState<string | null>(route.params?.topic ?? null);
  const open = useCallback((id: string | null) => {
    setTopic(id);
    scroll.current?.scrollTo({ y: 0, animated: false });
  }, []);
  // A contextual shortcut delivers its topic once; later visits keep the reader's place.
  useEffect(() => {
    if (!route.params?.topic) return;
    open(route.params.topic);
    navigation.setParams({ topic: undefined });
  }, [navigation, open, route.params?.topic]);
  return <SafeAreaView style={styles.safe} edges={['top', 'left', 'right']}>
    <ScrollView ref={scroll} keyboardShouldPersistTaps="handled" contentContainerStyle={styles.scroll}><View style={styles.container}>
      <AppHeader />
      <HelpCenter topicId={topic} onTopic={open} />
    </View></ScrollView>
  </SafeAreaView>;
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: theme.colors.background },
  scroll: { flexGrow: 1, paddingHorizontal: theme.space.lg, paddingBottom: 24 },
  container: { width: '100%', maxWidth: theme.maxWidth, alignSelf: 'center', gap: theme.space.lg },
});
