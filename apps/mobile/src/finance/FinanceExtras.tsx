import { useEffect, useState } from 'react';
import { Text, View } from 'react-native';
import { Button, Card, LoadingState } from '../components/ui';
import { Field, FormError, TextAction } from '../components/AuthLayout';
import { Choices } from './FinanceForms';
import * as api from './api';
import { s } from './styles';

type Save = (path: string, data: object, method?: 'POST' | 'PUT') => Promise<void>;

export function FinancialPreferences({ teamId, save, busy }: { teamId: string; save: Save; busy: boolean }) {
  const [settings, setSettings] = useState<api.Preferences | null>(null);
  const [amount, setAmount] = useState('0,00'), [day, setDay] = useState(api.dateLabel(api.localToday())), [share, setShare] = useState('no');
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let active = true;
    void api.call<api.Dashboard>(teamId, `/dashboard?month=${api.localToday().slice(0, 7)}-01`).then(data => { if (active && data.preferences) { setSettings(data.preferences); setAmount(data.preferences.opening_balance.replace('.', ',')); setDay(api.dateLabel(data.preferences.opening_date || api.localToday())); setShare(data.preferences.share_summary ? 'yes' : 'no'); } }).catch(cause => { if (active) setError(cause instanceof Error ? cause.message : 'Falha ao carregar.'); });
    return () => { active = false; };
  }, [teamId]);
  async function submit() {
    try {
      const value = amount.trim().replace(',', '.');
      if (!/^-?\d{1,8}(\.\d{1,2})?$/.test(value)) throw new Error('Informe o saldo com até duas casas decimais.');
      await save('/preferences', { opening_balance: value, opening_date: api.dateInput(day), share_summary: share === 'yes', expected_version: settings!.version, confirm: true }, 'PUT');
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Confira os dados.'); }
  }
  return <Card><Text style={s.heading}>Configurações financeiras</Text><FormError message={error} />{!settings ? (!error && <LoadingState />) : <>
    <Field label="Saldo inicial (R$)" value={amount} onChangeText={setAmount} keyboardType="numbers-and-punctuation" editable={!busy} />
    <Field mask="date" label="Data do saldo inicial" value={day} onChangeText={setDay} editable={!busy} />
    <Text style={s.note}>Valor anterior aos lançamentos que você registra no app. Ele é somado ao caixa; não substitui nem apaga movimentações existentes.</Text>
    <Text style={s.heading}>Transparência para jogadores</Text>
    <Choices options={{ no: 'Somente próprias mensalidades', yes: 'Também resumo agregado do time' }} value={share} onChange={setShare} disabled={busy} />
    <Text style={s.note}>Valores individuais, movimentações e histórico de outros jogadores permanecem privados.</Text>
    <Button label="Salvar configurações" disabled={busy} onPress={() => void submit()} />
  </>}</Card>;
}

export function CashDetail({ teamId, id, save, busy, openDues }: { teamId: string; id: string; save: Save; busy: boolean; openDues: (id: string) => void }) {
  const [data, setData] = useState<api.EntryDetail | null>(null), [error, setError] = useState<string | null>(null);
  const [edit, setEdit] = useState(false), [remove, setRemove] = useState(false);
  const [amount, setAmount] = useState(''), [day, setDay] = useState(''), [category, setCategory] = useState(''), [description, setDescription] = useState(''), [reason, setReason] = useState('');
  useEffect(() => {
    let active = true;
    void api.call<api.EntryDetail>(teamId, `/cash/${id}`).then(value => { if (active) { setData(value); setAmount(value.amount.replace('.', ',')); setDay(api.dateLabel(value.entry_date)); setCategory(value.category); setDescription(value.description); } }).catch(cause => { if (active) setError(cause instanceof Error ? cause.message : 'Falha ao carregar.'); });
    return () => { active = false; };
  }, [teamId, id]);
  async function submit() {
    try { await save(`/cash/${id}`, { amount: api.amountInput(amount), entry_date: api.dateInput(day), category, description, expected_version: data!.version, confirm: true }, 'PUT'); }
    catch (cause) { setError(cause instanceof Error ? cause.message : 'Confira os dados.'); }
  }
  return <Card><FormError message={error} />{!data ? (!error && <LoadingState />) : <>
    <Text style={s.heading}>{data.category} · {api.brl(data.amount)}</Text><Text style={s.text}>{data.description}</Text><Text style={s.note}>{api.dateLabel(data.entry_date)} · {data.cancelled_at ? 'Excluído / estornado' : data.kind === 'INCOME' ? 'Receita' : 'Despesa'}</Text>
    {!data.cancelled_at && (data.dues_id ? <TextAction label="Abrir mensalidade para corrigir pagamento" onPress={() => openDues(data.dues_id!)} /> : <><TextAction label="Editar movimentação" disabled={busy} onPress={() => { setEdit(true); setRemove(false); }} /><TextAction label="Excluir movimentação" disabled={busy} onPress={() => { setRemove(true); setEdit(false); }} /></>)}
    {edit && <><Field label="Categoria" value={category} onChangeText={setCategory} maxLength={60} /><Field label="Descrição (opcional)" value={description} onChangeText={setDescription} maxLength={160} /><Field label="Valor (R$)" value={amount} onChangeText={setAmount} keyboardType="decimal-pad" /><Field mask="date" label="Data" value={day} onChangeText={setDay} /><Button label="Confirmar edição" disabled={busy} onPress={() => void submit()} /></>}
    {remove && <><Text style={s.note}>A exclusão retira o valor do saldo e preserva o histórico.</Text><Field label="Motivo" value={reason} onChangeText={setReason} maxLength={500} /><Button label="Confirmar exclusão" variant="danger" disabled={busy || !reason.trim()} onPress={() => void save(`/cash/${id}/reverse`, { reason, confirm: true })} /></>}
    <Text style={s.heading}>Histórico de alteração</Text>
    {data.audit.map((a, i) => <Text key={i} style={s.note}>{api.dateLabel(a.created_at)} · {a.actor_name} · {api.labels[a.action] || a.action}{a.reason ? ` · ${a.reason}` : ''}</Text>)}
  </>}</Card>;
}

export function EditDues({ detail, save, busy }: { detail: api.Detail; save: Save; busy: boolean }) {
  const [amount, setAmount] = useState(detail.amount.replace('.', ',')), [error, setError] = useState<string | null>(null);
  async function submit() {
    try { await save(`/dues/${detail.id}`, { amount: api.amountInput(amount), expected_version: detail.version, confirm: true }, 'PUT'); }
    catch (cause) { setError(cause instanceof Error ? cause.message : 'Confira o valor.'); }
  }
  return <View style={s.stack}><Text style={s.heading}>Alterar somente esta cobrança</Text><Field label="Novo valor (R$)" value={amount} onChangeText={setAmount} keyboardType="decimal-pad" /><Text style={s.note}>Não altera outras cobranças nem a configuração mensal futura.</Text><FormError message={error} /><Button label="Confirmar novo valor" disabled={busy} onPress={() => void submit()} /></View>;
}
