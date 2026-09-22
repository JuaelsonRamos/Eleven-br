import { useState } from 'react';
import { Text, View } from 'react-native';
import { useAuth } from '../auth/AuthContext';
import { AuthLayout, FormError, authStyles } from '../components/AuthLayout';
import { Avatar, Badge, Button } from '../components/ui';

export function ProfileScreen() {
  const { profile, signOut } = useAuth();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function exit() {
    setBusy(true); setError(null);
    try { await signOut(); }
    catch { setError('Não foi possível encerrar sua sessão. Confira a conexão e tente novamente.'); }
    finally { setBusy(false); }
  }
  return <AuthLayout title="Perfil" description="Sua identidade dentro de campo.">
    <View style={authStyles.center}>
      <Avatar name={profile?.display_name || 'Jogador'} />
      <Text accessibilityRole="header" style={authStyles.note}>{profile?.display_name}</Text>
      <Text style={authStyles.note}>{profile?.email || profile?.phone}</Text>
      <Badge label="CONTATO VERIFICADO" />
      <Text style={authStyles.note}>Foto opcional. Você poderá adicioná-la em uma próxima etapa.</Text>
    </View>
    <FormError message={error} />
    <Button label={busy ? 'Saindo…' : 'Sair da conta'} disabled={busy} onPress={() => void exit()} />
  </AuthLayout>;
}
