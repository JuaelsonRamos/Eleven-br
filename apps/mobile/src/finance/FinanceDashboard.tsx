import { useEffect, useState } from 'react';
import { Platform, Share, Text, View } from 'react-native';
import * as Clipboard from 'expo-clipboard';
import { Badge, Button, Card, LoadingState, StatCard } from '../components/ui';
import { FormError, TextAction } from '../components/AuthLayout';
import { MonthSelector } from './MonthSelector';
import * as api from './api';
import { s } from './styles';
import { theme } from '../theme';

export function FinanceDashboard({ teamId, month, onMonth, manage, onDues, onCash, onEntry, onSettings, onPreferences, onDetail }: {
  teamId: string; month: string; onMonth: (value: string) => void; manage: boolean;
  onDues: () => void; onCash: () => void; onEntry: (kind: 'INCOME' | 'EXPENSE') => void; onSettings: () => void; onPreferences: () => void; onDetail: (id: string) => void;
}) {
  const [data, setData] = useState<api.Dashboard | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [retry, setRetry] = useState(0);
  const [notice, setNotice] = useState('');
  useEffect(() => {
    let active = true; setData(null); setError(null);
    if (!/^(0[1-9]|1[0-2])\/(20\d{2}|2100)$/.test(month)) { setError('Informe a competência como MM/AAAA.'); return; }
    void api.call<api.Dashboard>(teamId, `/dashboard?month=${api.monthInput(month)}`).then(value => { if (active) setData(value); }).catch(cause => { if (active) setError(cause instanceof Error ? cause.message : 'Não foi possível carregar o resumo.'); });
    return () => { active = false; };
  }, [teamId, month, retry]);
  async function share() {
    if (!data) return;
    const text = `ELEVEN BR · Resumo ${month}\nSaldo anterior: ${api.brl(data.previous_balance)}\nReceitas: ${api.brl(data.income)}\nDespesas: ${api.brl(data.expense)}\nSaldo do período: ${api.brl(data.period_balance)}${manage && data.receivable !== undefined ? `\nA receber: ${api.brl(data.receivable)}` : ''}`;
    try {
      if (Platform.OS === 'web') { await Clipboard.setStringAsync(text); setNotice('Resumo copiado para compartilhar.'); }
      else await Share.share({ message: text });
    } catch { setError('Não foi possível compartilhar o resumo.'); }
  }
  return <View style={s.stack}>
    <MonthSelector value={month} onChange={onMonth} onSelect={onMonth} disabled={false} />
    <FormError message={error} />
    {error ? <Button label="Tentar novamente" onPress={() => setRetry(v => v + 1)} /> : !data ? <LoadingState /> : <>
      {data.visible && <>
        <View style={s.summary}><Text style={s.summaryLabel}>Saldo atual</Text><Text style={s.balance}>{api.brl(data.balance)}</Text></View>
        <View style={s.row}><StatCard label="Receitas" value={api.brl(data.income)} /><StatCard label="Despesas" value={api.brl(data.expense)} tone="danger" />{data.receivable !== undefined && <StatCard label="A receber" value={api.brl(data.receivable)} tone="warning" />}</View>
      </>}
      {manage && <View style={s.row}><Button label="+ Receita" onPress={() => onEntry('INCOME')} /><Button label="+ Despesa" variant="secondary" onPress={() => onEntry('EXPENSE')} /></View>}
      <Card><Text style={s.heading}>{manage ? 'Mensalidades' : 'Minhas mensalidades'}</Text>
        {data.counts && <View style={s.row}><Badge label={`${data.counts.PAID} pagas`} /><Badge label={`${data.counts.PENDING} pendentes`} tone="warning" /><Badge label={`${data.counts.OVERDUE} atrasadas`} tone="danger" /><Badge label={`${data.counts.EXEMPT} isentas`} tone="exempt" /></View>}
        <TextAction label="Ver todas" onPress={onDues} />
        {manage && <TextAction label="Configurar mensalidade" onPress={onSettings} />}
      </Card>
      {manage && <Card><Text style={s.heading}>Últimas movimentações</Text>
        {data.recent?.length ? data.recent.map(item => <View key={item.id} style={s.divider}><Badge label={item.category} tone={item.kind === 'INCOME' ? 'success' : 'danger'} /><Text style={s.text}>{item.kind === 'INCOME' ? '+' : '−'} {api.brl(item.amount)} · {api.dateLabel(item.entry_date)}</Text><TextAction label={item.description} onPress={() => onDetail(item.id)} /></View>) : <Text style={s.note}>Nenhuma movimentação neste período.</Text>}
        <TextAction label="Ver todas as movimentações" onPress={onCash} />
      </Card>}
      {data.visible && <Card><Text style={s.heading}>Resumo do mês</Text>
        <Text style={s.text}>Saldo anterior: {api.brl(data.previous_balance)}</Text><Text style={s.text}>Saldo do período: {api.brl(data.period_balance)}</Text>
        {data.debtors !== undefined && <Text style={s.note}>{data.debtors} jogadores com mensalidade atrasada no período</Text>}
        {(['INCOME', 'EXPENSE'] as const).map(kind => <View key={kind} style={s.stack}><Text style={s.heading}>{kind === 'INCOME' ? 'Receitas' : 'Despesas'} por categoria</Text>
          {data.categories[kind].map(item => <View key={item.name} style={{ gap: 6 }}><Text style={s.note}>{item.name} · {api.brl(item.amount)} · {item.percent.replace('.', ',')}%</Text><View style={{ height: 6, borderRadius: 3, backgroundColor: theme.colors.surfaceMuted }}><View style={{ height: 6, borderRadius: 3, width: `${Math.min(100, Number(item.percent))}%`, backgroundColor: kind === 'INCOME' ? theme.colors.green : theme.colors.danger }} /></View></View>)}
          {!data.categories[kind].length && <Text style={s.note}>Sem movimentações.</Text>}
        </View>)}
        <TextAction label="Compartilhar resumo" onPress={() => void share()} />{notice && <Text style={s.note}>{notice}</Text>}
      </Card>}
      {manage && <TextAction label="Configurações financeiras" onPress={onPreferences} />}
    </>}
  </View>;
}
