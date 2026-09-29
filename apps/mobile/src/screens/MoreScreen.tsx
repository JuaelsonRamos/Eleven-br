import type { BottomTabScreenProps } from '@react-navigation/bottom-tabs';
import { AuthLayout } from '../components/AuthLayout';
import { Badge, ListItem } from '../components/ui';
import { useFocusEffect } from '@react-navigation/native';
import { useCallback } from 'react';
import { useNotifications } from '../notifications/NotificationContext';
import { useTeams } from '../teams/TeamContext';
import type { TabParams } from '../navigation';

export function MoreScreen({ navigation }: BottomTabScreenProps<TabParams>) {
  const { selected } = useTeams();
  const { count, refresh } = useNotifications();
  useFocusEffect(useCallback(() => { void refresh(); }, [refresh]));
  return <AuthLayout title="Mais" description="Sua conta e seus times.">
    <ListItem title="Meus Times / Trocar time" subtitle="Escolha seu time para jogar e administrar." onPress={() => navigation.navigate('Times', { view: 'list' })} />
    <ListItem title="Notificações" subtitle="Novidades dos seus times." trailing={count ? <Badge label={`${count} não lidas`} /> : undefined} onPress={() => navigation.navigate('Notificações')} />
    {selected && <ListItem title="ELEVEN PRO" subtitle="Plano e assinatura do time selecionado." onPress={() => navigation.navigate('ELEVEN PRO')} />}
    <ListItem title="Perfil" subtitle="Seus dados e sua foto." onPress={() => navigation.navigate('Perfil')} />
    <ListItem title="Aprenda a usar" subtitle="Guias rápidos das principais funções do ELEVEN BR." onPress={() => navigation.navigate('Ajuda')} />
  </AuthLayout>;
}
