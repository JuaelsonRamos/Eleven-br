import { useCallback, useEffect, useState } from 'react';
import type { BottomTabScreenProps } from '@react-navigation/bottom-tabs';
import type { TabParams } from '../navigation';
import { useFocusEffect } from '@react-navigation/native';
import { BackHandler, KeyboardAvoidingView, Platform, ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { AppHeader, Badge, Button, Card, EmptyState, ErrorState, LoadingState, ListItem, TeamBadge } from '../components/ui';
import { TextAction } from '../components/AuthLayout';
import { TeamForm } from '../teams/TeamForm';
import { TeamSummary } from '../teams/TeamSummary';
import { useTeams } from '../teams/TeamContext';
import { theme } from '../theme';
import { JoinPanel } from '../join/JoinPanel';
import { InviteCode } from '../join/InviteCode';
import { HelpShortcut } from '../help/HelpShortcut';

export function TeamsScreen({ route, navigation }: BottomTabScreenProps<TabParams, 'Times'>) {
  const { teams, selected, loading, error, warning, reload, select } = useTeams();
  const [mode, setMode] = useState<'list' | 'detail' | 'create' | 'edit' | 'join'>('list');
  const [editingId, setEditingId] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  useFocusEffect(useCallback(() => { void reload(); }, [reload]));
  useEffect(() => {
    if (route.params?.view) {
      setMode(route.params.view); setSuccess(null);
      navigation.setParams({ view: undefined });
    }
  }, [navigation, route.params?.view]);
  useFocusEffect(useCallback(() => {
    const listener = BackHandler.addEventListener('hardwareBackPress', () => {
      if (mode === 'list') return false;
      setMode('list'); return true;
    });
    return () => listener.remove();
  }, [mode]));
  const list = mode === 'list' || ((mode === 'detail' || mode === 'edit') && !selected);
  const editing = mode === 'edit' && selected?.id === editingId && selected?.can_edit;
  return <SafeAreaView style={styles.safe} edges={['top', 'left', 'right']}>
    <KeyboardAvoidingView style={styles.safe} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <ScrollView keyboardShouldPersistTaps="handled" contentContainerStyle={styles.scroll}>
        <View style={styles.container}>
          <AppHeader />
          <Text accessibilityRole="header" style={styles.title}>{mode === 'join' ? 'Entrar em um time' : mode === 'create' ? 'Criar time' : editing ? 'Editar time' : list ? 'Meus times' : 'Perfil do time'}</Text>
          {mode === 'join' && <HelpShortcut topic="join-team" label="Como entrar em um time?" />}
          {mode === 'create' && <HelpShortcut topic="create-team" label="Como criar um time?" />}
          {!loading && mode === 'edit' && !editing && <Text accessibilityRole="alert" style={styles.note}>O acesso ao time mudou. Confira o time selecionado antes de continuar.</Text>}
          {warning && <Text accessibilityRole="alert" style={styles.note}>{warning}</Text>}
          {success && <Text accessibilityLiveRegion="polite" style={styles.success}>{success}</Text>}
          {loading ? <LoadingState /> : error ? <ErrorState onRetry={() => void reload()} /> :
            mode === 'join' ? <JoinPanel onBack={() => setMode('list')} onTeams={() => { setMode('list'); void reload(); }} /> :
            mode === 'create' || editing ? <TeamForm
              key={mode === 'edit' ? selected?.id : 'new'} team={mode === 'edit' ? selected! : undefined}
              onDone={() => { setSuccess(mode === 'edit' ? 'Time atualizado.' : 'Time criado. Você é o Presidente!'); setMode('detail'); }}
              onCancel={() => setMode(mode === 'edit' ? 'detail' : 'list')} /> :
            !list && selected ? <>
              <Card><TeamSummary team={selected} detail /></Card>
              <Card>
                <Text style={styles.note}>Plano atual</Text>
                <Badge label={selected.plan === 'pro' ? 'ELEVEN BR PRO' : 'FREE'} />
                <Text style={styles.note}>{selected.plan === 'pro' ? 'Consulte os benefícios e o estado da assinatura do seu time.' : 'Desbloqueie todos os recursos do seu time com o ELEVEN BR PRO.'}</Text>
                <Button label={selected.plan === 'pro' ? selected.my_role === 'president' ? 'Gerenciar assinatura' : 'Ver plano PRO' : 'Conhecer o PRO'} onPress={() => navigation.navigate('ELEVEN PRO')} />
              </Card>
              <InviteCode key={selected.id} code={selected.code} name={selected.name} />
              <Badge label="TIME SELECIONADO" />
              <Button label="Início do time" onPress={() => navigation.navigate('Início')} />
              <Button label="Elenco" onPress={() => navigation.navigate('Elenco')} />
              {selected.can_edit && <Button label="Editar time" onPress={() => { setSuccess(null); setEditingId(selected.id); setMode('edit'); }} />}
              <TextAction label="Voltar para meus times" onPress={() => { setSuccess(null); setMode('list'); }} />
            </> : <>
              <Text style={styles.note}>Abra um time para acessar seu Início, Jogos e Elenco.</Text>
              <Button label="Criar time" onPress={() => { setSuccess(null); setMode('create'); }} />
              <Button variant="secondary" label="Entrar em um time" onPress={() => { setSuccess(null); setMode('join'); }} />
              {!teams.length && <EmptyState title="Seu futebol começa aqui." description="Crie um time ou entre usando o código compartilhado pelo responsável." icon="shield-outline" />}
              {teams.map(team => <ListItem key={team.id} title={team.name} subtitle={`${team.city} · ${team.state}`} leading={<TeamBadge name={team.name} crestUrl={team.crest_url} size={48} />}
                accessibilityLabel={`Abrir ${team.name}`} onPress={() => { setSuccess(null); void select(team.id).then(() => navigation.navigate('Início')); }}
                trailing={<><Badge label={team.plan === 'free' ? 'Free' : 'Pro'} tone="neutral" />{selected?.id === team.id && <Badge label="TIME SELECIONADO" />}</>} />)}
            </>}
        </View>
      </ScrollView>
    </KeyboardAvoidingView>
  </SafeAreaView>;
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: theme.colors.background },
  scroll: { flexGrow: 1, paddingHorizontal: theme.space.lg, paddingBottom: 24 },
  container: { width: '100%', maxWidth: theme.maxWidth, alignSelf: 'center', gap: theme.space.lg },
  title: { fontFamily: theme.fontFamily, fontSize: theme.type.title, fontWeight: '800', color: theme.colors.graphite },
  card: { gap: 16 }, note: { color: theme.colors.muted, fontFamily: theme.fontFamily, fontSize: 15, lineHeight: 23 },
  success: { color: theme.colors.green, fontFamily: theme.fontFamily, fontSize: 16 },
});
