import { useCallback, useEffect, useRef, useState } from 'react';
import { BackHandler, Text, View } from 'react-native';
import { useFocusEffect } from '@react-navigation/native';
import { Avatar, Badge, Button, Card, EmptyState, LoadingState, FilterChip, StatCard, Feedback } from '../components/ui';
import { Field, FormError, TextAction } from '../components/AuthLayout';
import { ApiError } from '../auth/api';
import { Choices, EntryForm, SettingsForm } from './FinanceForms';
import * as api from './api';
import { DuesList, duesTone } from './DuesList';
import { MonthSelector } from './MonthSelector';
import { s } from './styles';

type Mode = 'dues' | 'cash' | 'settings' | 'entry' | 'detail' | 'payment';
type Action = { path: string; payload: object; title: string; reasonRequired: boolean };
export function FinancePanel({ teamId, onBack, onNavigate, onPro, initialDuesId, onInitialConsumed }: { teamId: string; onBack: () => void; onNavigate: () => void; onPro: () => void; initialDuesId?: string; onInitialConsumed?: () => void }) {
  const initial = useRef(initialDuesId), consumed = useRef(onInitialConsumed);
  const [context, setContext] = useState<api.Context | null>(null);
  const [mode, setMode] = useState<Mode>('dues');
  const [dues, setDues] = useState<api.DuesPage | null>(null);
  const [cash, setCash] = useState<api.CashPage | null>(null);
  const [detail, setDetail] = useState<api.Detail | null>(null);
  const [month, setMonth] = useState(api.monthLabel(api.localToday()));
  const [preview, setPreview] = useState<(api.Preview & { competence: string }) | null>(null);
  const [offset, setOffset] = useState(0);
  const [appliedMonth, setAppliedMonth] = useState<string | undefined>();
  const [filters, setFilters] = useState({ start: '', end: '', kind: '', category: '' });
  const [action, setAction] = useState<Action | null>(null);
  const [reason, setReason] = useState('');
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const generation = useRef(0);
  const sending = useRef(false);
  const load = useCallback(async (target: Mode = 'dues', page = 0, id?: string, selectedMonth?: string, query?: typeof filters) => {
    const current = ++generation.current;
    setLoading(true); setError(null); setPreview(null); setAction(null); setMode(target); setOffset(page);
    try {
      const ctx = await api.call<api.Context>(teamId);
      if (current !== generation.current) return;
      setContext(ctx);
      if (!ctx.enabled) return; // Free: ELEVEN BR PRO presentation only; the backend refuses operations.
      if (!ctx.can_manage && !['dues', 'detail'].includes(target)) throw new Error('Sem permissão para administrar o financeiro.');
      if (target === 'dues') {
        setAppliedMonth(selectedMonth);
        const params = new URLSearchParams({ offset: String(page) });
        if (selectedMonth) params.set('competence', api.monthInput(selectedMonth));
        const value = await api.call<api.DuesPage>(teamId, `/dues?${params}`);
        if (current === generation.current) setDues(value);
      } else if (target === 'cash') {
        const params = new URLSearchParams({ offset: String(page) });
        if (query?.start) params.set('start', api.dateInput(query.start));
        if (query?.end) params.set('end', api.dateInput(query.end));
        if (query?.kind) params.set('kind', query.kind);
        if (query?.category) params.set('category', query.category);
        const value = await api.call<api.CashPage>(teamId, `/cash?${params}`);
        if (current === generation.current) setCash(value);
      } else if (id) {
        const value = await api.call<api.Detail>(teamId, `/dues/${id}`);
        if (current === generation.current) setDetail(value);
      }
    } catch (cause) {
      if (current === generation.current) { setError(cause instanceof Error ? cause.message : 'Não foi possível carregar.'); setDues(null); setCash(null); setDetail(null); setContext(null); }
    } finally { if (current === generation.current) setLoading(false); }
  }, [teamId]);
  useEffect(() => {
    const counter = generation, id = initial.current;
    initial.current = undefined;
    const request = load(id ? 'detail' : 'dues', 0, id);
    const current = counter.current;
    void request.then(() => { if (id && counter.current === current) consumed.current?.(); });
    return () => { counter.current++; };
  }, [load]);
  function navigate(target: Mode, id?: string) { setSuccess(null); onNavigate(); void load(target, 0, id, target === 'dues' ? month : undefined, filters); }
  async function save(path: string, payload: object, method: 'POST' | 'PUT' = 'POST') {
    if (sending.current) return;
    const current = generation.current; sending.current = true; setBusy(true); setError(null);
    try {
      await api.call(teamId, path, payload, method);
      if (current !== generation.current) return;
      setSuccess('Registro salvo.'); setBusy(false); setAction(null); setReason('');
      if (mode === 'payment' || mode === 'detail') await load('detail', 0, detail?.id);
      else if (mode === 'cash' || mode === 'entry') await load('cash', 0, undefined, undefined, filters);
      else await load('dues', 0, undefined, month);
      onNavigate();
    } catch (cause) {
      if (current === generation.current) {
        setError(cause instanceof Error ? cause.message : 'Não foi possível salvar.');
        if (cause instanceof ApiError && [403, 404].includes(cause.status)) { setContext(null); setDetail(null); setDues(null); setCash(null); }
      }
    } finally { sending.current = false; if (current === generation.current) setBusy(false); }
  }
  function back() {
    if (sending.current) return;
    if (action || preview) { setAction(null); setPreview(null); }
    else if (mode === 'payment' && detail) navigate('detail', detail.id);
    else if (mode !== 'dues') navigate('dues');
    else onBack();
  }
  useFocusEffect(useCallback(() => {
    const handler = BackHandler.addEventListener('hardwareBackPress', () => {
      if (!sending.current) {
        if (mode !== 'dues') void load('dues'); else onBack();
      }
      return true;
    });
    return () => handler.remove();
  }, [mode, load, onBack]));
  async function prepareGeneration() {
    if (sending.current) return;
    const current = generation.current; sending.current = true; setBusy(true); setError(null);
    try { const competence = api.monthInput(month); const value = await api.call<api.Preview>(teamId, '/dues/preview', { competence }, 'POST'); if (current === generation.current) setPreview({ ...value, competence }); }
    catch (cause) { if (current === generation.current) setError(cause instanceof Error ? cause.message : 'Não foi possível gerar a previsão.'); }
    finally { sending.current = false; if (current === generation.current) setBusy(false); }
  }
  function ask(value: Action) { setAction(value); setReason(''); setError(null); onNavigate(); }
  const manage = context?.can_manage;
  const summary = context?.totals;
  const row = (entry: api.Entry) => <View key={entry.id} style={s.divider}>
    <Badge label={entry.cancelled_at ? 'ESTORNADO' : entry.kind === 'INCOME' ? 'RECEITA' : 'DESPESA'} tone={entry.cancelled_at ? 'neutral' : entry.kind === 'INCOME' ? 'success' : 'danger'} />
    <Text style={s.heading}>{entry.kind === 'INCOME' ? '+ ' : '− '}{api.brl(entry.amount)}{entry.cancelled_at ? ' · ESTORNADO' : ''}</Text>
    <Text style={s.text}>{entry.description}</Text><Text style={s.note}>{api.dateLabel(entry.entry_date)} · {entry.category}{entry.payment_method ? ` · ${api.labels[entry.payment_method]}` : ''}</Text>
    <Text style={s.note}>Registrado por {entry.created_by_name} em {api.dateLabel(entry.created_at)}</Text>
    {entry.note && <Text style={s.note}>{entry.note}</Text>}
    {entry.cancelled_at && <Text style={s.note}>Estorno por {entry.cancelled_by_name} em {api.dateLabel(entry.cancelled_at)}: {entry.cancellation_reason}</Text>}
    {manage && !entry.cancelled_at && (entry.dues_id && mode === 'cash' ? <TextAction label="Abrir cobrança" disabled={busy} onPress={() => navigate('detail', entry.dues_id!)} /> : <TextAction label="Estornar lançamento" disabled={busy} onPress={() => ask({ title: `Estornar ${api.brl(entry.amount)}?`, path: `/cash/${entry.id}/reverse`, payload: { expected_dues_version: entry.dues_id ? detail?.version : null, confirm: true }, reasonRequired: true })} />)}
  </View>;
  return <View style={s.stack}>
    <Text accessibilityRole="header" style={s.title}>Financeiro</Text>
    <FormError message={error} /><Feedback message={success} />
    {loading ? <LoadingState /> : !context ? <Button label="Tentar novamente" onPress={() => void load()} /> : !context.enabled ? <Card><View style={s.stack}>
      <Badge label="ELEVEN BR PRO" /><Text style={s.heading}>Financeiro é um recurso ELEVEN BR PRO.</Text>
      <Text style={s.text}>Tenha o controle financeiro do seu time em um só lugar.</Text>
      {['Mensalidades do elenco', 'Registro e acompanhamento de pagamentos', 'Receitas e despesas do caixa', 'Saldo e histórico financeiro do time'].map(item => <Text key={item} style={s.text}>• {item}</Text>)}
      <Text style={s.heading}>ELEVEN BR PRO</Text><Text style={s.text}>{context.pro_price ? api.brl(context.pro_price) : ''}/mês por time</Text>
      <Button label="CONHECER O ELEVEN BR PRO" onPress={onPro} />
    </View></Card> : action ? <Card><View style={s.stack}>
      <Text style={s.heading}>{action.title}</Text><Field label={action.reasonRequired ? 'Motivo' : 'Motivo (opcional)'} value={reason} onChangeText={setReason} maxLength={500} editable={!busy} />
      <Button label="Confirmar ação" disabled={busy || (action.reasonRequired && !reason.trim())} onPress={() => void save(action.path, { ...action.payload, reason: reason.trim() || null })} />
      <TextAction label="Voltar sem alterar" disabled={busy} onPress={() => setAction(null)} />
    </View></Card> : <>
      {manage && summary && <View style={s.summary}><Text style={s.summaryLabel}>Saldo atual</Text><Text accessibilityLabel={`Saldo atual: ${api.brl(summary.balance)}`} style={s.balance}>{api.brl(summary.balance)}</Text><View style={s.row}><View style={s.summaryItem}><Text style={s.summaryLabel}>↗ Receitas</Text><Text style={s.summaryValue}>{api.brl(summary.income)}</Text></View><View style={s.summaryItem}><Text style={s.summaryLabel}>↘ Despesas</Text><Text style={s.summaryValue}>{api.brl(summary.expense)}</Text></View></View></View>}
      {manage && <View style={s.row}><FilterChip selected={mode !== 'cash' && mode !== 'entry'} label="Mensalidades" disabled={busy} onPress={() => navigate('dues')} /><FilterChip selected={mode === 'cash' || mode === 'entry'} label="Caixa" disabled={busy} onPress={() => navigate('cash')} /></View>}
      {mode === 'settings' && context.settings && <SettingsForm settings={context.settings} save={save} busy={busy} />}
      {mode === 'entry' && context.command_id && <EntryForm commandId={context.command_id} save={save} busy={busy} />}
      {mode === 'payment' && detail?.command_id && <EntryForm detail={detail} commandId={detail.command_id} save={save} busy={busy} />}
      {mode === 'dues' && <>
        <Text style={s.heading}>{manage ? 'Mensalidades' : 'Minhas mensalidades'}</Text>
        <MonthSelector value={month} onChange={value => { setMonth(value); setPreview(null); }} onSelect={value => { setMonth(value); void load('dues', 0, undefined, value); }} disabled={busy} />
        <View style={s.row}><TextAction label="Consultar competência" disabled={busy} onPress={() => void load('dues', 0, undefined, month)} /><TextAction label="Ver todas" disabled={busy} onPress={() => void load()} /></View>
        {manage && <><TextAction label="Configurar mensalidade" disabled={busy} onPress={() => navigate('settings')} /><Button label="Gerar mensalidades" disabled={busy || !context.settings?.active} onPress={() => void prepareGeneration()} />{!context.settings?.active && <Text style={s.note}>Ative a mensalidade padrão para gerar cobranças.</Text>}</>}
        {preview && <Card><View style={s.stack}><Text style={s.heading}>Conferir geração · {api.monthLabel(preview.competence)}</Text><Text style={s.text}>{preview.count} cobranças · {api.brl(preview.total)}</Text><Text style={s.note}>Vencimento {api.dateLabel(preview.due_date)}. {preview.ignored} jogadores já cobrados serão ignorados.</Text><Button label="Confirmar geração" disabled={busy || !preview.count} onPress={() => void save('/dues/generate', { competence: preview.competence, preview_token: preview.preview_token, confirm: true })} /><TextAction label="Voltar sem gerar" disabled={busy} onPress={() => setPreview(null)} /></View></Card>}
        {dues && <DuesList teamId={teamId} page={dues} month={appliedMonth} offset={offset} busy={busy} open={id => navigate('detail', id)} paginate={page => void load('dues', page, undefined, appliedMonth)} />}
      </>}
      {mode === 'detail' && detail && <>
        <Card><View style={s.row}><Avatar name={detail.name} /><View style={s.identity}><Text style={s.heading}>{detail.name}</Text><Text style={s.note}>Jogador · {api.monthLabel(detail.competence)}</Text></View></View><Badge label={api.status(detail)} tone={duesTone(detail)} /><Text style={s.note}>Vencimento {api.dateLabel(detail.due_date)}</Text></Card>
        <View style={s.row}><StatCard label="Valor da cobrança" value={api.brl(detail.amount)} tone="info" /><StatCard label="Valor pago" value={api.brl(detail.received)} /><StatCard label="Saldo devedor" value={api.brl(detail.remaining)} tone={duesTone(detail)} /></View>
        {manage && <>
          {detail.status === 'PENDING' && <Button label="Registrar pagamento" disabled={busy} onPress={() => navigate('payment', detail.id)} />}
          {detail.status === 'PENDING' && detail.received === '0.00' && <TextAction label="Isentar mensalidade" disabled={busy} onPress={() => ask({ title: 'Isentar esta mensalidade?', path: `/dues/${detail.id}/actions`, payload: { action: 'exempt', expected_version: detail.version, confirm: true }, reasonRequired: false })} />}
          {detail.status === 'EXEMPT' && <TextAction label="Desfazer isenção" disabled={busy} onPress={() => ask({ title: 'Desfazer a isenção?', path: `/dues/${detail.id}/actions`, payload: { action: 'undo_exemption', expected_version: detail.version, confirm: true }, reasonRequired: false })} />}
          {detail.status !== 'CANCELLED' && detail.received === '0.00' && <TextAction label="Cancelar cobrança" disabled={busy} onPress={() => ask({ title: 'Cancelar esta cobrança?', path: `/dues/${detail.id}/actions`, payload: { action: 'cancel', expected_version: detail.version, confirm: true }, reasonRequired: true })} />}
        </>}
        <Text style={s.heading}>Pagamentos</Text>{detail.payments.length ? detail.payments.map(row) : <Text style={s.note}>Nenhum pagamento registrado.</Text>}
        <Text style={s.heading}>Histórico da cobrança</Text>{detail.audit.map((item, index) => <Text key={index} style={s.note}>{api.dateLabel(item.created_at)} · {item.actor_name} · {item.action === 'EXEMPT' ? 'Isenção' : api.labels[item.action] ?? item.action}{item.reason ? ` · ${item.reason}` : ''}</Text>)}
        <TextAction label="Atualizar cobrança" disabled={busy} onPress={() => navigate('detail', detail.id)} />
      </>}
      {mode === 'cash' && cash && <>
        <Text style={s.heading}>Caixa do time</Text><Text style={s.note}>Saldo atual considera todos os lançamentos válidos. Os filtros abaixo alteram somente o histórico.</Text>
        <Button label="Novo lançamento" disabled={busy} onPress={() => navigate('entry')} />
        <Field mask="date" label="De (DD/MM/AAAA)" value={filters.start} onChangeText={start => setFilters({ ...filters, start })} maxLength={10} />
        <Field mask="date" label="Até (DD/MM/AAAA)" value={filters.end} onChangeText={end => setFilters({ ...filters, end })} maxLength={10} />
        <Choices options={{ '': 'Todos', INCOME: 'Receitas', EXPENSE: 'Despesas' }} value={filters.kind} onChange={kind => setFilters({ ...filters, kind })} disabled={busy} />
        <Field label="Categoria (opcional)" value={filters.category} onChangeText={category => setFilters({ ...filters, category })} maxLength={60} />
        <Button label="Filtrar movimentações" disabled={busy} onPress={() => void load('cash', 0, undefined, undefined, filters)} />
        {!cash.items.length && <EmptyState title="Nenhuma movimentação encontrada" description="Registre pagamentos, receitas ou despesas para acompanhar o caixa." />}
        {cash.items.map(row)}<View style={s.row}>{offset > 0 && <TextAction label="Anteriores" disabled={busy} onPress={() => void load('cash', Math.max(0, offset - 50), undefined, undefined, filters)} />}{cash.has_more && <TextAction label="Próximas" disabled={busy} onPress={() => void load('cash', offset + 50, undefined, undefined, filters)} />}</View>
      </>}
    </>}
    <TextAction label={mode === 'dues' ? 'Voltar ao início' : 'Voltar'} disabled={busy} onPress={back} />
  </View>;
}
