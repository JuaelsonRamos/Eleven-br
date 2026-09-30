import { authenticated } from '../auth/api';

export const categories = { male: 'Masculino', female: 'Feminino', mixed: 'Misto' };
type Category = keyof typeof categories;
/** Registration and similar-team check: UF plus official IBGE municipality, never free text. */
export type TeamInput = { name: string; state: string; municipality_code: number | null; modalities: string[]; category: Category | null };
/** Profile edit: location changes only through the President's location confirmation. */
export type TeamProfileInput = { name: string; modalities: string[]; category: Category | null };
export type PublicTeam = { name: string; code: string; city: string; state: string; modalities: string[]; category: Category | null };
export type Team = PublicTeam & {
  id: string; status: string; plan: 'free' | 'pro'; crest_url: string | null;
  my_role: 'president' | 'admin' | 'member'; can_edit: boolean;
  active_player_count: number; municipality_code: number | null; location_confirmed: boolean;
};
export type Municipality = { code: number; name: string };
export type TeamLocation = {
  city: string; state: string; municipality_code: number | null; confirmed: boolean; confirmed_at: string | null;
  suggestion: (Municipality & { state: string }) | null; can_change: boolean;
};
export type Choice = { value: string; label: string };
export type Options = { modalities: Choice[]; states: Choice[] };
export const modalityLabels = (values: string[], choices: Choice[]) => values
  .map(value => choices.find(item => item.value === value)?.label ?? value).join(' • ');
export const roles = { president: 'Presidente', admin: 'Administrador', member: 'Jogador' };
export const listTeams = () => authenticated<Team[]>('/v1/teams');
export const getTeam = (id: string) => authenticated<Team>(`/v1/teams/${encodeURIComponent(id)}`);
export const getOptions = () => authenticated<Options>('/v1/teams/options');
export const findSimilar = (data: TeamInput) => authenticated<PublicTeam[]>('/v1/teams/similar', data, 'POST');
export const transferPresidency = (teamId: string, membershipId: string) => authenticated<Team>(
  `/v1/teams/${encodeURIComponent(teamId)}/presidency`, { membership_id: membershipId, confirm: true }, 'POST',
);
export const saveTeam = (data: TeamInput | TeamProfileInput, id?: string) => authenticated<Team>(
  id ? `/v1/teams/${encodeURIComponent(id)}` : '/v1/teams', data, id ? 'PUT' : 'POST',
);
// Official IBGE municipalities of one UF, cached for the session (reference data).
const municipalities = new Map<string, Promise<Municipality[]>>();
export function listMunicipalities(state: string) {
  let found = municipalities.get(state);
  if (!found) {
    found = authenticated<{ items: Municipality[] }>(`/v1/locations/states/${encodeURIComponent(state)}/municipalities`).then(page => page.items);
    found.catch(() => municipalities.delete(state));
    municipalities.set(state, found);
  }
  return found;
}
export const getLocation = (teamId: string) => authenticated<TeamLocation>(`/v1/teams/${encodeURIComponent(teamId)}/location`);
export const saveLocation = (teamId: string, data: { state: string; municipality_code: number }) => authenticated<Team>(
  `/v1/teams/${encodeURIComponent(teamId)}/location`, data, 'PUT',
);
