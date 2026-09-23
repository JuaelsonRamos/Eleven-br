import type { BottomTabScreenProps } from '@react-navigation/bottom-tabs';
import { AuthLayout } from '../components/AuthLayout';
import { Button } from '../components/ui';
import type { TabParams } from '../navigation';

export function MoreScreen({ navigation }: BottomTabScreenProps<TabParams>) {
  return <AuthLayout title="Mais" description="Sua conta e seus times.">
    <Button label="Meus Times / Trocar time" onPress={() => navigation.navigate('Times', { view: 'list' })} />
    <Button label="Notificações" onPress={() => navigation.navigate('Notificações')} />
    <Button label="Perfil" onPress={() => navigation.navigate('Perfil')} />
  </AuthLayout>;
}
