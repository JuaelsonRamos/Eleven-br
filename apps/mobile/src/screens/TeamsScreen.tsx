import { useCallback, useEffect, useState } from 'react';
import type { BottomTabScreenProps } from '@react-navigation/bottom-tabs';
import type { TabParams } from '../navigation';
import { RosterPanel } from '../roster/RosterPanel';
import { useFocusEffect } from '@react-navigation/native';
import { BackHandler, KeyboardAvoidingView, Platform, ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { AppHeader, Badge, Button, Card, EmptyState, ErrorState, LoadingState } from '../components/ui';
import { TextAction } from '../components/AuthLayout';
import { TeamForm } from '../teams/TeamForm';
import { TeamSummary } from '../teams/TeamSummary';
import { useTeams } from '../teams/TeamContext';
import { theme } from '../theme';

export function TeamsScreen({ route, navigation }: BottomTabScreenProps<TabParams>) {
  const { teams, selected, loading, error, warning, reload, select } = useTeams();
  const [mode, setMode] = useState<'list' | 'detail' | 'create' | 'edit' | 'roster'>('list');
  const [rosterTeamId, setRosterTeamId] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  useFocusEffect(useCallback(() => { void reload(); }, [reload]));
  useEffect(() => {
    if (route.params?.rosterFor && selected?.id === route.params.rosterFor) {
      setRosterTeamId(selected.id); setMode('roster'); setSuccess(null);
      navigation.setParams({ rosterFor: undefined });
    }
  }, [navigation, route.params?.rosterFor, selected?.id]);
  useFocusEffect(useCallback(() => {
    const listener = BackHandler.addEventListener('hardwareBackPress', () => {
      if (mode === 'list' || mode === 'roster') return false;
      setMode('list'); return true;
    });
    return () => listener.remove();
  }, [mode]));
  const list = mode === 'list' || ((mode === 'detail' || mode === 'edit' || mode === 'roster') && !selected);
  const roster = mode === 'roster' && selected?.id === rosterTeamId;
  const editing = mode === 'edit' && selected?.id === editingId && selected?.can_edit;
  return <SafeAreaView style={styles.safe} edges={['top', 'left', 'right']}>
    <KeyboardAvoidingView style={styles.safe} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <ScrollView keyboardShouldPersistTaps="handled" contentContainerStyle={styles.scroll}>
        <View style={styles.container}>
          <AppHeader />
          {!roster && <Text accessibilityRole="header" style={styles.title}>{mode === 'create' ? 'Criar time' : editing ? 'Editar time' : list ? 'Meus times' : 'Perfil do time'}</Text>}
          {!loading && mode === 'edit' && !editing && <Text accessibilityRole="alert" style={styles.note}>O acesso ao time mudou. Confira o time selecionado antes de continuar.</Text>}
          {warning && <Text accessibilityRole="alert" style={styles.note}>{warning}</Text>}
          {success && <Text accessibilityLiveRegion="polite" style={styles.success}>{success}</Text>}
          {loading ? <LoadingState /> : error ? <ErrorState onRetry={() => void reload()} /> :
            roster && selected ? <RosterPanel key={selected.id} team={selected} onBack={() => { setMode('detail'); void reload(); }} /> :
            mode === 'create' || editing ? <TeamForm
              key={mode === 'edit' ? selected?.id : 'new'} team={mode === 'edit' ? selected! : undefined}
              onDone={() => { setSuccess(mode === 'edit' ? 'Time atualizado.' : 'Time criado. Você é o Presidente!'); setMode('detail'); }}
              onCancel={() => setMode(mode === 'edit' ? 'detail' : 'list')} /> :
            !list && selected ? <>
              <Card><TeamSummary team={selected} detail /></Card>
              <Badge label="TIME SELECIONADO" />
              <Button label="Elenco" onPress={() => { setSuccess(null); setRosterTeamId(selected.id); setMode('roster'); }} />
              {selected.can_edit && <Button label="Editar time" onPress={() => { setSuccess(null); setEditingId(selected.id); setMode('edit'); }} />}
              <TextAction label="Voltar para meus times" onPress={() => { setSuccess(null); setMode('list'); }} />
            </> : <>
              <Text style={styles.note}>Selecione um time para acompanhar seu contexto no Início.</Text>
              <Button label="Criar time" onPress={() => { setSuccess(null); setMode('create'); }} />
              {!teams.length && <EmptyState title="Seu time começa aqui" description="Crie seu primeiro time e reúna sua identidade dentro de campo." icon="shield-outline" />}
              {teams.map(team => <Card key={team.id}><View style={styles.card}>
                <TeamSummary team={team} />
                {selected?.id === team.id && <Badge label="TIME SELECIONADO" />}
                <Button label={`Abrir ${team.name}`} onPress={() => { setSuccess(null); setMode('detail'); void select(team.id); }} />
              </View></Card>)}
            </>}
        </View>
      </ScrollView>
    </KeyboardAvoidingView>
  </SafeAreaView>;
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: theme.colors.background },
  scroll: { flexGrow: 1, paddingHorizontal: 20, paddingBottom: 24 },
  container: { width: '100%', maxWidth: theme.maxWidth, alignSelf: 'center', gap: 20 },
  title: { fontFamily: theme.fontFamily, fontSize: 30, fontWeight: '800', color: theme.colors.graphite },
  card: { gap: 16 }, note: { color: theme.colors.muted, fontFamily: theme.fontFamily, fontSize: 15, lineHeight: 23 },
  success: { color: theme.colors.green, fontFamily: theme.fontFamily, fontSize: 16 },
});
