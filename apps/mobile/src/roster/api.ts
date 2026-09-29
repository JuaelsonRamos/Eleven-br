import { authenticated } from '../auth/api';

export type TeamRole = 'president' | 'admin' | 'member';
export type RosterPerson = {
  membership_id: string; player_id: string; name: string; nickname: string | null;
  phone: string | null; email: string | null; photo_url: string | null;
  status: 'active' | 'inactive' | 'removed'; account_linked: boolean; is_president: boolean;
  positions: string[]; primary_position: string | null; roster_version: number;
  role: TeamRole; permissions: string[];
};
export type RosterFilter = 'active' | 'inactive' | 'all';
export type RosterPage = { items: RosterPerson[]; active_count: number; inactive_count: number;
  active_limit: number; can_manage: boolean; plan: string;
  can_manage_admins: boolean; admin_limit: number; admin_count: number };
/** Areas of the existing granular permissions, in the order shown to the President. */
export const permissionAreas = [
  { value: 'manage_members', label: 'Elenco e solicitações' },
  { value: 'manage_events', label: 'Jogos, peladas e escalações' },
  { value: 'manage_finance', label: 'Financeiro' },
  { value: 'manage_team', label: 'Perfil do time' },
] as const;
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
export const positionOptions = async (team: string) => Object.entries(await authenticated<Record<string, string>>(`${base(team)}/positions/options`)).map(([value, label]) => ({ value, label }));
export const savePositions = (team: string, person: RosterPerson, positions: string[], primary: string | null) => authenticated<RosterPerson>(`${base(team)}/${person.membership_id}/positions`, { positions, primary_position: primary, expected_version: person.roster_version }, 'PUT');
export const removePerson = (team: string, person: RosterPerson) => authenticated<RosterPerson>(`${base(team)}/${person.membership_id}/remove`, { confirm: true, expected_version: person.roster_version }, 'POST');
export const saveRole = (team: string, person: RosterPerson, role: 'admin' | 'member', permissions: string[]) => authenticated<RosterPerson>(`${base(team)}/${person.membership_id}/role`, { role, permissions, expected_version: person.roster_version }, 'PUT');
