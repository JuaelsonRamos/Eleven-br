import { useEffect, useState } from 'react';
import { Text, View } from 'react-native';
import { Avatar, Badge, EmptyState, FilterChip, ListItem, LoadingState, StatCard } from '../components/ui';
import { FormError, TextAction } from '../components/AuthLayout';
import type { Tone } from '../components/design';
import * as api from './api';
import { s } from './styles';

const filters = { ALL: 'Todas', PAID: 'Pagas', PENDING: 'Pendentes', OVERDUE: 'Atrasadas', EXEMPT: 'Isentas', CANCELLED: 'Canceladas' };
const tones: Record<string, Tone> = { PAID: 'success', PENDING: 'warning', OVERDUE: 'danger', EXEMPT: 'exempt', CANCELLED: 'neutral' };
export const duesTone = (item: api.Dues): Tone => tones[item.overdue ? 'OVERDUE' : item.status] ?? 'neutral';

export function DuesList({ teamId, page, month, offset, busy, open, paginate }: { teamId: string; page: api.DuesPage; month?: string; offset: number; busy: boolean; open: (id: string) => void; paginate: (offset: number) => void }) {
  const [filter, setFilter] = useState('ALL');
  const [items, setItems] = useState(page.items);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    let active = true;
    setError(null);
    if (filter === 'ALL') { setItems(page.items); setLoading(false); return; }
    setLoading(true); setItems([]);
    void (async () => {
      // The API paginates by 50. Filter the complete authorized period, never just a page.
      const all: api.Dues[] = [];
      let more = true;
      while (more && active) {
        const params = new URLSearchParams({ offset: String(all.length) });
        if (month) params.set('competence', api.monthInput(month));
        const next = await api.call<api.DuesPage>(teamId, `/dues?${params}`);
        all.push(...next.items); more = next.has_more && next.items.length > 0;
      }
      if (active) setItems(all.filter(item => (item.overdue ? 'OVERDUE' : item.status) === filter));
    })().catch(cause => { if (active) setError(cause instanceof Error ? cause.message : 'Não foi possível consultar as cobranças.'); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [filter, month, page, retry, teamId]);
  return <View style={s.stack}>
    <Text style={s.note}>{month ? `Competência consultada: ${month}` : 'Todas as competências'}</Text>
    <View style={s.row}>{Object.entries(filters).map(([key, label]) => <FilterChip key={key} label={label} selected={filter === key} disabled={busy} onPress={() => setFilter(key)} />)}</View>
    <View style={s.row}>{Object.entries(page.counts).map(([key, count]) => <StatCard key={key} label={api.labels[key] ?? key} value={count} tone={tones[key]} />)}</View>
    <FormError message={error} />
    {error ? <TextAction label="Tentar novamente" onPress={() => setRetry(value => value + 1)} /> : loading ? <LoadingState /> : <>
      {!items.length && <EmptyState title="Nenhuma mensalidade encontrada" description="Confira a competência e o filtro selecionados. As cobranças aparecem após a geração pelo responsável." />}
      {items.map(item => <ListItem key={item.id} title={item.name} subtitle={`${api.monthLabel(item.competence)} · Venc. ${api.dateLabel(item.due_date)}`} leading={<Avatar name={item.name} size={40} />}
        accessibilityLabel={`Abrir cobrança de ${item.name}`} onPress={() => open(item.id)} disabled={busy}
        trailing={<><Text style={s.heading}>{api.brl(item.amount)}</Text><Badge label={api.status(item)} tone={duesTone(item)} /></>}>
        <Text style={s.note}>Recebido {api.brl(item.received)} · A pagar {api.brl(item.remaining)}</Text>
      </ListItem>)}
      {filter === 'ALL' && <View style={s.row}>{offset > 0 && <TextAction label="Anteriores" disabled={busy} onPress={() => paginate(Math.max(0, offset - 50))} />}{page.has_more && <TextAction label="Próximas" disabled={busy} onPress={() => paginate(offset + 50)} />}</View>}
    </>}
  </View>;
}
