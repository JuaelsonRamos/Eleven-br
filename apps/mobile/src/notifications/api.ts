import { authenticated } from '../auth/api';

export type Notification = {
  id: string; team_id: string | null; team_name: string | null; type: string;
  title: string; message: string; entity_type: string | null; entity_id: string | null;
  action: 'OPEN_TEAM' | 'OPEN_JOIN_REQUESTS' | 'OPEN_EVENT' | 'OPEN_FINANCE_CHARGE' | null;
  read_at: string | null; created_at: string; available: boolean;
};
export type Page = { items: Notification[]; next_cursor: string | null };
const base = '/v1/me/notifications';
export const list = (cursor?: string) => authenticated<Page>(`${base}?limit=20${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ''}`);
export const unread = () => authenticated<{ count: number }>(`${base}/unread-count`);
export const read = (id: string) => authenticated<Notification>(`${base}/${encodeURIComponent(id)}/read`, {}, 'POST');
export const readAll = () => authenticated<{ count: number }>(`${base}/read-all`, {}, 'POST');
