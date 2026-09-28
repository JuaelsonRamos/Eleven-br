import { useState } from 'react';
import { Platform, Share, Text, View } from 'react-native';
import * as Clipboard from 'expo-clipboard';
import { Button } from '../components/ui';
import { FormError } from '../components/AuthLayout';
import { styles as s } from './styles';

export function InviteCode({ code, name = 'meu time' }: { code: string; name?: string }) {
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  async function share(copyCode = false) {
    setMessage(null); setError(null);
    try {
      const origin = Platform.OS === 'web' ? window.location.origin : process.env.EXPO_PUBLIC_APP_URL;
      const link = origin ? `\n${origin.replace(/\/$/, '')}/?team_code=${encodeURIComponent(code)}` : '';
      const text = `Entre no ${name} no ELEVEN BR. Código: ${code}.${link}\nSolicite entrada e aguarde a aprovação do responsável.`;
      if (copyCode || Platform.OS === 'web') {
        if (!await Clipboard.setStringAsync(copyCode ? code : text)) throw new Error();
        setMessage(copyCode ? 'Código copiado.' : 'Convite copiado. Compartilhe com o jogador.');
      } else await Share.share({ message: text });
    } catch { setError('Não foi possível compartilhar. Selecione o código para copiar.'); }
  }
  return <View style={s.stack}>
    <Text style={s.heading}>Convidar jogadores</Text><Text selectable style={s.code}>{code}</Text>
    <Text style={s.note}>Compartilhe este código com quem deseja entrar no time. A entrada depende de aprovação.</Text>
    <Button label="Copiar código" onPress={() => void share(true)} />
    <Button variant="secondary" label="Compartilhar convite" onPress={() => void share()} />
    {message && <Text accessibilityLiveRegion="polite" style={s.success}>{message}</Text>}
    <FormError message={error} />
  </View>;
}
