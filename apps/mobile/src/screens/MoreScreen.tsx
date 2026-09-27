import type { BottomTabScreenProps } from '@react-navigation/bottom-tabs';
import { AuthLayout } from '../components/AuthLayout';
import { ListItem } from '../components/ui';
import type { TabParams } from '../navigation';

export function MoreScreen({ navigation }: BottomTabScreenProps<TabParams>) {
  return <AuthLayout title="Mais" description="Sua conta e seus times.">
    <ListItem title="Meus Times / Trocar time" subtitle="Escolha seu time para jogar e administrar." onPress={() => navigation.navigate('Times', { view: 'list' })} />
    <ListItem title="Notificações" subtitle="Avisos da sua conta." onPress={() => navigation.navigate('Notificações')} />
    <ListItem title="Perfil" subtitle="Seus dados e sua foto." onPress={() => navigation.navigate('Perfil')} />
  </AuthLayout>;
}
