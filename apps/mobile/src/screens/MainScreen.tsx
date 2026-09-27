import type { BottomTabScreenProps } from '@react-navigation/bottom-tabs';
import { ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { AppHeader, Badge, Button, Card, EmptyState, LoadingState, ErrorState } from '../components/ui';
import { useCallback } from 'react';
import { useFocusEffect } from '@react-navigation/native';
import { useTeams } from '../teams/TeamContext';
import { TeamDashboard } from '../teams/TeamDashboard';
import { theme } from '../theme';
import type { TabParams } from '../navigation';

export function MainScreen({ route, navigation }: BottomTabScreenProps<TabParams>) {
  const name = route.name;
  const { selected, loading, error, reload } = useTeams();
  useFocusEffect(useCallback(() => { if (name === 'Início') void reload(); }, [name, reload]));
  return <SafeAreaView style={styles.safe} edges={['top', 'left', 'right']}>
    <ScrollView contentContainerStyle={styles.scroll}>
      <View style={styles.container}>
        <AppHeader onProfile={() => navigation.navigate('Perfil')} />
        <View style={styles.heading}>
          <Text accessibilityRole="header" style={styles.pageTitle}>{name === 'Início' && selected ? 'Início do time' : name}</Text>
          <Text style={styles.pageDescription}>{name === 'Início' ? 'Mais futebol. Menos burocracia.' : 'Seu futebol, mais organizado.'}</Text>
        </View>
        {name === 'Início' ? <>
          {!selected && !loading && !error && <View style={styles.hero}>
            <Text style={styles.eyebrow}>DENTRO E FORA DE CAMPO</Text>
            <Text accessibilityRole="header" style={styles.heroTitle}>Seu time.{ '\n' }Seu jogo.</Text>
            <View style={styles.accent} />
            <Text style={styles.heroDescription}>Um lugar para reunir a turma e cuidar do que faz o futebol acontecer.</Text>
          </View>}
          {loading ? <LoadingState /> : error ? <ErrorState onRetry={() => void reload()} /> : selected ? <TeamDashboard key={selected.id} team={selected} navigation={navigation} /> : <Card>
            <Badge label="BEM-VINDO AO ELEVEN BR" />
            <EmptyState title="Seu futebol começa aqui." description="Crie seu time ou entre usando o código compartilhado pelo responsável." icon="people-outline">
              <Button label="Conhecer a área de times" onPress={() => navigation.navigate('Times')} />
              <Button label="Entrar em um time" onPress={() => navigation.navigate('Times', { view: 'join' })} />
            </EmptyState>
          </Card>}
        </> : <Card><EmptyState title="Tudo em dia por aqui" description="Quando as notificações estiverem disponíveis, você encontrará os avisos dos seus times neste espaço." icon="notifications-outline" /></Card>}
        <Text style={styles.footer}>ELEVEN BR · Feito para o nosso futebol</Text>
      </View>
    </ScrollView>
  </SafeAreaView>;
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: theme.colors.background },
  scroll: { flexGrow: 1, paddingHorizontal: theme.space.lg, paddingBottom: 24 },
  container: { width: '100%', maxWidth: theme.maxWidth, alignSelf: 'center', gap: theme.space.lg },
  heading: { gap: 6 },
  pageTitle: { fontFamily: theme.fontFamily, fontSize: theme.type.title, fontWeight: '800', color: theme.colors.graphite },
  pageDescription: { fontFamily: theme.fontFamily, fontSize: 15, color: theme.colors.muted },
  hero: { backgroundColor: theme.colors.green, padding: 28, borderRadius: theme.radius, gap: 18 },
  eyebrow: { fontFamily: theme.fontFamily, fontSize: 11, letterSpacing: 1.5, fontWeight: '700', color: theme.colors.white },
  heroTitle: { fontFamily: theme.fontFamily, fontSize: 46, lineHeight: 51, fontWeight: '900', color: theme.colors.white },
  accent: { backgroundColor: theme.colors.gold, width: 44, height: 4, borderRadius: 2 },
  heroDescription: { fontFamily: theme.fontFamily, fontSize: 16, lineHeight: 25, color: theme.colors.white, maxWidth: 400 },
  footer: { color: theme.colors.muted, textAlign: 'center', fontFamily: theme.fontFamily, fontSize: 12, paddingVertical: 12 },
});
