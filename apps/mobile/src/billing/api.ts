import { authenticated } from '../auth/api';

export type Billing = {
  entitlement_origin: 'COURTESY' | 'LEGACY' | 'PAID' | 'NONE';
  has_recurring_subscription: boolean; renewal_date: string | null;
  command_id: string;
  available_payment_methods: ('PIX' | 'CREDIT_CARD')[];
  plan: 'free' | 'pro'; plan_code: string; status: string; price: string;
  expires_at: string | null; started_at: string | null; can_manage: boolean;
  can_cancel: boolean; cancel_requested: boolean; method: string | null;
  operation_status: string | null; warning: string | null; notice?: string;
  next_due_date?: string | null; checkout_url?: string;
  server_time: string; signup_expires_at: string | null;
  signup_expired: boolean; can_retry_pix: boolean;
  pix?: { image: string | null; payload: string | null; expires_at: string | null; amount: string };
};
const path = (teamId: string) => `/v1/teams/${teamId}/billing`;
export const getBilling = (teamId: string) => authenticated<Billing>(path(teamId));
export const refreshBilling = (teamId: string) => authenticated<Billing>(`${path(teamId)}/refresh`, {}, 'POST');
export const cancelBilling = (teamId: string) => authenticated<Billing>(`${path(teamId)}/cancel`, { confirm: true }, 'POST');
export const checkout = (teamId: string, data: { command_id: string; method: 'PIX' | 'CREDIT_CARD'; name: string; email: string; cpf_cnpj: string }) => authenticated<Billing>(`${path(teamId)}/checkout`, { ...data, confirm: true }, 'POST');
