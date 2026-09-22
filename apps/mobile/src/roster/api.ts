import { authenticated } from '../auth/api';

export type RosterPerson = {
  membership_id: string; player_id: string; name: string; nickname: string | null;
  phone: string | null; email: string | null; photo_url: string | null;
  status: 'active' | 'inactive'; account_linked: boolean; is_president: boolean;
};
export type RosterFilter = 'active' | 'inactive' | 'all';
export type RosterPage = { items: RosterPerson[]; active_count: number; inactive_count: number;
  active_limit: number; can_manage: boolean; plan: string };
export type PlayerInput = { name?: string; nickname?: string | null; phone?: string | null; email?: string | null; confirm_duplicate?: boolean };
export type SimilarPlayer = Pick<RosterPerson, 'membership_id' | 'name' | 'status' | 'account_linked'> & { reasons: string[] };
const base = (teamId: string) => `/v1/teams/${encodeURIComponent(teamId)}/players`;
export const listRoster = (teamId: string, status: RosterFilter = 'active') => authenticated<RosterPage>(`${base(teamId)}?status=${status}`);
export const getPerson = (teamId: string, id: string) => authenticated<RosterPerson>(`${base(teamId)}/${encodeURIComponent(id)}`);
export const similarPlayers = (teamId: string, data: PlayerInput, exclude?: string) => authenticated<SimilarPlayer[]>(
  `${base(teamId)}/similar${exclude ? `?exclude=${encodeURIComponent(exclude)}` : ''}`, data, 'POST',
);
export const savePerson = (teamId: string, data: PlayerInput, id?: string) => authenticated<RosterPerson>(
  id ? `${base(teamId)}/${encodeURIComponent(id)}` : base(teamId), data, id ? 'PUT' : 'POST',
);
export const changeStatus = (teamId: string, id: string, activate: boolean) => authenticated<RosterPerson>(
  `${base(teamId)}/${encodeURIComponent(id)}/${activate ? 'reactivate' : 'deactivate'}`, {}, 'POST',
);
