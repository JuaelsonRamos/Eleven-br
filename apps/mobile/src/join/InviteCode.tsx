import { useState } from 'react';
import { Platform, Share, Text, View } from 'react-native';
import { Button } from '../components/ui';
import { FormError } from '../components/AuthLayout';
import { styles as s } from './styles';

export function InviteCode({ code }: { code: string }) {
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  async function share() {
    setMessage(null); setError(null);
    try {
      if (Platform.OS === 'web') {
        if (!navigator.clipboard?.writeText) { setMessage('Selecione o código acima para copiar.'); return; }
        await navigator.clipboard.writeText(code); setMessage('Código copiado.');
      } else await Share.share({ message: `Entre no meu time no ELEVEN BR. Código: ${code}` });
    } catch { setError('Não foi possível compartilhar. Selecione o código para copiar.'); }
  }
  return <View style={s.stack}>
    <Text style={s.heading}>Convidar jogadores</Text><Text selectable style={s.code}>{code}</Text>
    <Text style={s.note}>Compartilhe este código com quem deseja entrar no time. A entrada depende de aprovação.</Text>
    <Button label={Platform.OS === 'web' ? 'Copiar código' : 'Compartilhar código'} onPress={() => void share()} />
    {message && <Text accessibilityLiveRegion="polite" style={s.success}>{message}</Text>}
    <FormError message={error} />
  </View>;
}
