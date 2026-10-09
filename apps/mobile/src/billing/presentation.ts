import type { Billing } from './api';

export const planLabel = (data: Billing) => data.plan !== 'pro' ? 'FREE'
  : data.entitlement_origin === 'COURTESY' ? 'PRO CORTESIA' : 'PRO ATIVO';
