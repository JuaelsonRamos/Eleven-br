import { useState } from 'react';
import { Text, View } from 'react-native';
import * as Clipboard from 'expo-clipboard';
import { TextAction } from '../components/AuthLayout';
import { styles as s } from '../join/styles';

export function TeamPublicId({ code }: { code: string }) {
  const [message, setMessage] = useState('');
  async function copy() {
    try { setMessage(await Clipboard.setStringAsync(code) ? 'ID copiado' : 'Selecione o ID para copiar.'); }
    catch { setMessage('Não foi possível copiar. Selecione o ID.'); }
  }
  return <View style={s.stack}>
    <Text selectable style={s.note}>ID do time: {code}</Text>
    <TextAction label="Copiar ID" onPress={() => void copy()} />
    {!!message && <Text accessibilityLiveRegion="polite" style={s.note}>{message}</Text>}
  </View>;
}
