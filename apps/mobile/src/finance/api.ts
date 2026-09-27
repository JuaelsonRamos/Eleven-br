import { authenticated } from '../auth/api';

export type Totals = { income: string; expense: string; balance: string };
export type Settings = { amount: string; due_day: number; active: boolean; version: number };
export type Context = { can_manage: boolean; currency: 'BRL'; settings?: Settings; totals?: Totals; command_id?: string };
export type Dues = { id: string; membership_id: string; name: string; competence: string; due_date: string; amount: string; received: string; remaining: string; status: 'PENDING' | 'PAID' | 'EXEMPT' | 'CANCELLED'; overdue: boolean; version: number };
export type Entry = { id: string; dues_id: string | null; kind: 'INCOME' | 'EXPENSE'; category: string; description: string; amount: string; entry_date: string; payment_method: string | null; note: string | null; cancelled_at: string | null; cancellation_reason: string | null; created_at: string; source: string; created_by_name: string; cancelled_by_name: string | null };
export type Detail = Dues & { command_id?: string; payments: Entry[]; audit: { action: string; actor_name: string; reason: string | null; created_at: string }[] };
export type DuesPage = { items: Dues[]; counts: Record<string, number>; has_more: boolean };
export type CashPage = { items: Entry[]; totals: Totals; categories: string[]; has_more: boolean };
export type Preview = { count: number; ignored: number; total: string; amount: string; due_date: string; preview_token: string };
export const call = <T>(team: string, path = '', data?: unknown, method: 'GET' | 'POST' | 'PUT' = 'GET') => authenticated<T>(`/v1/teams/${encodeURIComponent(team)}/finance${path}`, data, method);
export const labels: Record<string, string> = { PENDING: 'PENDENTE', PAID: 'PAGA', EXEMPT: 'ISENTA', CANCELLED: 'CANCELADA', OVERDUE: 'ATRASADA', PIX: 'PIX', CASH: 'Dinheiro', CARD: 'Cartão', OTHER: 'Outro', PAYMENT: 'Pagamento registrado', GENERATED: 'Cobrança gerada', EXEMPT_ACTION: 'Isenção', UNDO_EXEMPTION: 'Isenção desfeita', CANCEL: 'Cobrança cancelada', REVERSAL: 'Pagamento estornado' };
export const status = (dues: Dues) => dues.overdue ? 'ATRASADA' : labels[dues.status] ?? dues.status;
export function brl(value: string) {
  const [whole = '0', cents = '00'] = value.split('.');
  return `R$ ${whole.replace(/\B(?=(\d{3})+(?!\d))/g, '.')},${cents.padEnd(2, '0')}`;
}
export const dateLabel = (value: string) => value.slice(0, 10).split('-').reverse().join('/');
export const monthLabel = (value: string) => `${value.slice(5, 7)}/${value.slice(0, 4)}`;
export function localToday() { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`; }
export function amountInput(value: string) {
  const normalized = value.trim().replace(',', '.');
  if (!/^\d{1,8}(\.\d{1,2})?$/.test(normalized) || /^0+(\.0+)?$/.test(normalized)) throw new Error('Informe um valor positivo com até dois centavos.');
  return normalized;
}
export function dateInput(value: string) {
  if (!/^\d{2}\/\d{2}\/\d{4}$/.test(value)) throw new Error('Informe a data como DD/MM/AAAA.');
  return value.split('/').reverse().join('-');
}
export function monthInput(value: string) {
  if (!/^(0[1-9]|1[0-2])\/(20\d{2}|2100)$/.test(value)) throw new Error('Informe a competência como MM/AAAA.');
  return `${value.slice(3)}-${value.slice(0, 2)}-01`;
}
