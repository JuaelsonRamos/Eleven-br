import { Text, View } from 'react-native';
import { Field } from '../components/AuthLayout';
import { IconButton } from '../components/ui';
import { s } from './styles';

export function MonthSelector({ value, onChange, onSelect, disabled }: { value: string; onChange: (value: string) => void; onSelect: (value: string) => void; disabled: boolean }) {
  const valid = /^(0[1-9]|1[0-2])\/(20\d{2}|2100)$/.test(value);
  const date = valid ? new Date(Number(value.slice(3)), Number(value.slice(0, 2)) - 1, 1) : null;
  function move(step: number) {
    if (!date) return;
    const next = new Date(date.getFullYear(), date.getMonth() + step, 1);
    onSelect(`${String(next.getMonth() + 1).padStart(2, '0')}/${next.getFullYear()}`);
  }
  return <View style={s.stack}>
    <View style={s.monthRow}><IconButton label="Competência anterior" icon="chevron-back" disabled={disabled || !valid || value === '01/2000'} onPress={() => move(-1)} />
      <Text style={s.month}>{date ? date.toLocaleDateString('pt-BR', { month: 'long', year: 'numeric' }) : 'Competência'}</Text>
      <IconButton label="Próxima competência" icon="chevron-forward" disabled={disabled || !valid || value === '12/2100'} onPress={() => move(1)} /></View>
    <Field label="Competência (MM/AAAA)" value={value} onChangeText={onChange} maxLength={7} keyboardType="numbers-and-punctuation" editable={!disabled} />
  </View>;
}
