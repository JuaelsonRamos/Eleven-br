import { useState } from 'react';
import { Text, View } from 'react-native';
import { Field, FormError, TextAction } from '../components/AuthLayout';
import { Button, Card, FilterChip, FormSurface } from '../components/ui';
import * as api from './api';
import { s } from './styles';

export function Choices({ options, value, onChange, disabled = false }: { options: Record<string, string>; value: string; onChange: (value: string) => void; disabled?: boolean }) {
  return <View style={s.row}>{Object.entries(options).map(([key, label]) => <FilterChip key={key} role="radio" label={label} disabled={disabled} selected={key === value} onPress={() => onChange(key)} />)}</View>;
}

type Save = (path: string, data: object, method?: 'POST' | 'PUT') => Promise<void>;
export function SettingsForm({ settings, save, busy }: { settings: api.Settings; save: Save; busy: boolean }) {
  const [amount, setAmount] = useState(settings.amount.replace('.', ','));
  const [day, setDay] = useState(String(settings.due_day));
  const [active, setActive] = useState(settings.active ? 'yes' : 'no');
  const [error, setError] = useState<string | null>(null);
  async function submit() {
    try { setError(null); if (!/^\d{1,2}$/.test(day) || Number(day) < 1 || Number(day) > 31) throw new Error('Informe um dia entre 1 e 31.'); await save('/settings', { amount: api.amountInput(amount), due_day: Number(day), active: active === 'yes', expected_version: settings.version }, 'PUT'); }
    catch (cause) { setError(cause instanceof Error ? cause.message : 'Confira os dados.'); }
  }
  return <FormSurface><Text style={s.heading}>Mensalidade padrão</Text>
    <Field label="Valor da mensalidade (R$)" value={amount} onChangeText={setAmount} keyboardType="decimal-pad" editable={!busy} />
    <Field label="Dia de vencimento" value={day} onChangeText={setDay} keyboardType="number-pad" maxLength={2} editable={!busy} />
    <Text style={s.note}>Se o mês não tiver esse dia, vence no último dia do mês. Alterações valem apenas para cobranças futuras.</Text>
    <Choices options={{ yes: 'Ativa', no: 'Inativa' }} value={active} onChange={setActive} disabled={busy} />
    <FormError message={error} /><Button label="Salvar configuração" onPress={() => void submit()} disabled={busy} />
  </FormSurface>;
}

export function EntryForm({ detail, commandId, save, busy }: { detail?: api.Detail; commandId: string; save: Save; busy: boolean }) {
  const [amount, setAmount] = useState(detail?.remaining.replace('.', ',') ?? '');
  const [day, setDay] = useState(api.dateLabel(api.localToday()));
  const [kind, setKind] = useState('INCOME');
  const [method, setMethod] = useState('PIX');
  const [category, setCategory] = useState('');
  const [description, setDescription] = useState('');
  const [note, setNote] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [prepared, setPrepared] = useState<Record<string, unknown> | null>(null);
  function prepare() {
    try {
      setError(null);
      const common = { command_id: commandId, amount: api.amountInput(amount), entry_date: api.dateInput(day), note: note.trim() || null, confirm: true };
      if (!detail && (!category.trim() || !description.trim())) throw new Error('Informe categoria e descrição.');
      setPrepared(detail ? { ...common, expected_version: detail.version, payment_method: method } : { ...common, kind, category: category.trim(), description: description.trim() });
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Confira os dados.'); }
  }
  return <FormSurface><Text style={s.heading}>{detail ? 'Registrar pagamento' : 'Novo lançamento'}</Text>
    <FormError message={error} />
    {prepared ? <Card><View style={s.stack}>
      <Text style={s.heading}>{detail ? 'Confirmar recebimento' : kind === 'INCOME' ? 'Confirmar receita' : 'Confirmar despesa'}</Text>
      <Text style={s.text}>{api.brl(String(prepared.amount))} · {day}</Text>
      <Text style={s.note}>{detail ? `${detail.name} · ${api.monthLabel(detail.competence)} · ${api.labels[method]}` : `${category} · ${description}`}</Text>
      <Button label="Confirmar lançamento" disabled={busy} onPress={() => void save(detail ? `/dues/${detail.id}/payments` : '/cash', prepared)} />
      <TextAction label="Revisar dados" disabled={busy} onPress={() => setPrepared(null)} />
    </View></Card> : <>
      {!detail && <><Choices options={{ INCOME: 'Receita', EXPENSE: 'Despesa' }} value={kind} onChange={setKind} /><Field label="Categoria" value={category} onChangeText={setCategory} maxLength={60} /><Field label="Descrição" value={description} onChangeText={setDescription} maxLength={160} /></>}
      <Field label={detail ? 'Valor recebido (R$)' : 'Valor (R$)'} value={amount} onChangeText={setAmount} keyboardType="decimal-pad" />
      {detail && <Text style={s.note}>Saldo devedor: {api.brl(detail.remaining)}. Pode registrar parte desse valor.</Text>}
      <Field mask="date" label="Data (DD/MM/AAAA)" value={day} onChangeText={setDay} maxLength={10} keyboardType="numbers-and-punctuation" />
      {detail && <Choices options={{ PIX: 'PIX', CASH: 'Dinheiro', CARD: 'Cartão', OTHER: 'Outro' }} value={method} onChange={setMethod} />}
      <Field label="Observação (opcional)" value={note} onChangeText={setNote} maxLength={500} multiline />
      {method === 'CARD' && detail && <Text style={s.note}>Registro manual. Sem integração com operadora ou cálculo de taxas.</Text>}
      <Button label="Conferir lançamento" onPress={prepare} disabled={busy} />
    </>}
  </FormSurface>;
}
